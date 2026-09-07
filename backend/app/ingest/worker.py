"""The consumer that turns a plate event into stored state and live alerts.

This is the single write path into the system. Every observation — whether it
came from a real camera, a replayed file, or the simulator — lands here and is
processed identically:

    PlateEvent -> persist Observation -> update plate profile
               -> run alert rules -> broadcast anything raised
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..anpr.pipeline import PlateEvent
from ..config import settings
from ..engines.alerts import AlertEngine
from ..engines.camera_graph import CameraGraph
from ..models import Alert, Observation


def store_event(db: Session, event: PlateEvent) -> Observation:
    """Persist one plate event. Raw frames get an explicit expiry stamp so the
    retention job can drop imagery while keeping the structured record."""
    ts = event.timestamp if event.timestamp.tzinfo else event.timestamp.replace(tzinfo=timezone.utc)
    obs = Observation(
        camera_id=event.camera_id, ts=ts,
        plate_text=event.plate_text, plate_norm=event.plate_norm,
        plate_confidence=event.plate_confidence,
        vehicle_type=event.vehicle_type, direction=event.direction,
        lane=event.lane, speed_estimate_kmph=event.speed_estimate_kmph,
        frames_fused=event.frames_fused, format_valid=event.format_valid,
        repairs=event.repairs, condition=event.condition,
        frame_ref=event.frame_ref,
        frame_expires_at=ts + timedelta(seconds=settings.frame_retention_seconds),
    )
    db.add(obs)
    db.flush()
    return obs


def process_event(db: Session, graph: CameraGraph, event: PlateEvent,
                  alert_engine: AlertEngine | None = None) -> tuple[Observation, list[Alert]]:
    """Full write path for a single observation."""
    engine = alert_engine or AlertEngine(db, graph)
    obs = store_event(db, event)
    # Order matters. The rules must see the plate's history as it stood
    # *before* this sighting — folding the observation into the baseline first
    # lets it mask its own anomaly (a 03:00 sighting makes 03:00 look normal).
    # Vehicles with too little history are excluded by the rules themselves.
    alerts = engine.evaluate(obs)
    engine.update_profile(obs)
    return obs, alerts


def expire_frames(db: Session, now: datetime | None = None) -> int:
    """Privacy retention job: drop references to raw imagery past its window.

    The structured observation survives; the picture of the vehicle does not.
    """
    now = now or datetime.now(timezone.utc)
    rows = db.query(Observation).filter(
        Observation.frame_expires_at.isnot(None),
        Observation.frame_expires_at < now,
        Observation.frame_ref.isnot(None),
    ).all()
    for r in rows:
        r.frame_ref = None
        r.frame_expires_at = None
    db.flush()
    return len(rows)
