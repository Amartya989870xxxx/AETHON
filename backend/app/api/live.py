"""Live alert feed and the demo traffic driver."""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..engines.alerts import AlertEngine
from ..engines.camera_graph import CameraGraph
from ..ingest.worker import process_event
from ..sim.simulator import TrafficSimulator
from .deps import get_graph

router = APIRouter(tags=["live"])


class AlertHub:
    """Fan-out of newly raised alerts to every connected dashboard."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in self._clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)


hub = AlertHub()


@router.websocket("/ws/alerts")
async def alert_stream(ws: WebSocket) -> None:
    """Push channel for the operator dashboard's alert panel."""
    await hub.connect(ws)
    try:
        await ws.send_json({"type": "connected",
                            "at": datetime.now(timezone.utc).isoformat()})
        while True:
            # Keeps the connection open; the client is not expected to speak.
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)
    except Exception:
        hub.disconnect(ws)


class DemoDriver:
    """Feeds simulated traffic through the real write path in wall-clock time.

    Used to show the system running live during a demo. It is a traffic source,
    not a shortcut: every event it produces goes through the same ANPR
    pipeline, alert rules and persistence as a real camera's would.
    """

    def __init__(self) -> None:
        self.task: asyncio.Task | None = None
        self.events_sent = 0
        self.alerts_raised = 0
        self.running = False

    async def _run(self, graph: CameraGraph, speed: float, duration_s: int) -> None:
        sim = TrafficSimulator(graph, seed=int(datetime.now().timestamp()) % 10_000)
        started = datetime.now(timezone.utc)
        self.running = True
        try:
            while (datetime.now(timezone.utc) - started).total_seconds() < duration_s:
                now = datetime.now(timezone.utc)
                passes = sim.journey(now)
                db: Session = SessionLocal()
                try:
                    engine = AlertEngine(db, graph)
                    for vp in passes:
                        event = sim.recognise(vp)
                        if event is None:
                            continue
                        # Compress the journey into the live window so a route
                        # unfolds on the map during the demo rather than over
                        # the twenty real minutes it would actually take.
                        event.timestamp = now + timedelta(
                            seconds=(vp.timestamp - passes[0].timestamp).total_seconds() / speed
                        )
                        obs, alerts = process_event(db, graph, event, engine)
                        self.events_sent += 1
                        for a in alerts:
                            self.alerts_raised += 1
                            await hub.broadcast({
                                "type": "alert", "id": a.id,
                                "alert_type": a.alert_type, "severity": a.severity,
                                "plate": a.plate_norm, "camera_id": a.camera_id,
                                "title": a.title, "confidence": a.confidence,
                                "evidence": a.evidence,
                                "created_at": a.created_at.isoformat(),
                            })
                    db.commit()
                finally:
                    db.close()
                await asyncio.sleep(1.0)
        finally:
            self.running = False


driver = DemoDriver()


@router.post("/api/demo/start")
async def start_demo(
    duration_s: int = Query(120, ge=10, le=1800),
    speed: float = Query(60.0, ge=1.0, le=600.0,
                         description="how much faster than real time journeys unfold"),
    graph: CameraGraph = Depends(get_graph),
) -> dict:
    if driver.running:
        return {"status": "already_running", "events_sent": driver.events_sent}
    driver.task = asyncio.create_task(driver._run(graph, speed, duration_s))
    return {"status": "started", "duration_s": duration_s, "speed": speed,
            "websocket": "/ws/alerts"}


@router.post("/api/demo/stop")
async def stop_demo() -> dict:
    if driver.task:
        driver.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await driver.task
        driver.task = None
    driver.running = False
    return {"status": "stopped", "events_sent": driver.events_sent,
            "alerts_raised": driver.alerts_raised}


@router.get("/api/demo/status")
async def demo_status() -> dict:
    return {"running": driver.running, "events_sent": driver.events_sent,
            "alerts_raised": driver.alerts_raised,
            "dashboard_clients": hub.client_count}
