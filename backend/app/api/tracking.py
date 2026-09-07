"""Observation ingestion and Component 2's trajectory query."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..anpr.pipeline import PlateEvent
from ..anpr.plate_format import normalize, validate
from ..db import get_db
from ..engines.camera_graph import CameraGraph
from ..engines.trajectory import TrajectoryEngine
from ..ingest.worker import process_event
from ..models import AuditLog, Camera, Observation
from ..schemas import ObservationOut, PlateEventIn
from .deps import get_graph, time_window

router = APIRouter(prefix="/api", tags=["tracking"])


@router.post("/observations", status_code=201)
def ingest_observation(
    payload: PlateEventIn,
    db: Session = Depends(get_db),
    graph: CameraGraph = Depends(get_graph),
) -> dict:
    """Production ingestion endpoint — one camera event in, alerts out.

    Edge nodes post here (or publish to the broker that feeds here). The same
    write path the simulator uses, so nothing about the demo is a special case.
    """
    if not db.get(Camera, payload.camera_id):
        raise HTTPException(404, f"Unknown camera {payload.camera_id}")

    fmt = validate(payload.plate_text)
    event = PlateEvent(
        camera_id=payload.camera_id, timestamp=payload.timestamp,
        plate_text=fmt.plate if fmt.valid else payload.plate_text,
        plate_norm=normalize(fmt.plate if fmt.valid else payload.plate_text),
        plate_confidence=payload.plate_confidence,
        vehicle_type=payload.vehicle_type, direction=payload.direction,
        lane=payload.lane, speed_estimate_kmph=payload.speed_estimate_kmph,
        condition=payload.condition, frames_fused=payload.frames_fused,
        format_valid=fmt.valid, format_name=fmt.format_name, repairs=fmt.repairs,
        frame_ref=payload.frame_ref,
    )
    obs, alerts = process_event(db, graph, event)
    db.commit()
    return {
        "observation_id": obs.id,
        "plate_norm": obs.plate_norm,
        "format_valid": fmt.valid,
        "repairs": fmt.repairs,
        "alerts_raised": [
            {"id": a.id, "type": a.alert_type, "severity": a.severity, "title": a.title}
            for a in alerts
        ],
    }


@router.get("/observations", response_model=list[ObservationOut])
def list_observations(
    plate: str | None = Query(None),
    camera_id: str | None = Query(None),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(200, le=2000),
    window: tuple[datetime, datetime] = Depends(time_window),
    db: Session = Depends(get_db),
):
    start, end = window
    stmt = select(Observation).where(and_(Observation.ts >= start, Observation.ts <= end))
    if plate:
        stmt = stmt.where(Observation.plate_norm == normalize(plate))
    if camera_id:
        stmt = stmt.where(Observation.camera_id == camera_id)
    if min_confidence:
        stmt = stmt.where(Observation.plate_confidence >= min_confidence)
    rows = db.execute(stmt.order_by(Observation.ts.desc()).limit(limit)).scalars().all()
    return rows


@router.get("/trajectory/{plate}")
def get_trajectory(
    plate: str,
    actor: str = Query("operator", description="who is running this query"),
    persist: bool = Query(False),
    window: tuple[datetime, datetime] = Depends(time_window),
    db: Session = Depends(get_db),
    graph: CameraGraph = Depends(get_graph),
) -> dict:
    """Reconstruct one vehicle's route across the camera network.

    This is an identity-sensitive query — it reveals an individual's movement —
    so every call is written to the audit log with the caller and the window
    requested, before the result is returned.
    """
    start, end = window
    plate_norm = normalize(plate)

    db.add(AuditLog(
        actor=actor, action="trajectory_query", subject=plate_norm,
        detail={"window_start": start.isoformat(), "window_end": end.isoformat()},
    ))
    db.commit()

    engine = TrajectoryEngine(db, graph)
    result = engine.reconstruct(plate_norm, start, end)
    if persist and result.found:
        engine.persist(result)
        db.commit()
    return result.to_dict()


@router.get("/plates/search")
def search_plates(
    partial: str = Query(..., min_length=2,
                         description="partial plate, e.g. 'DL4C' or '3125'"),
    vehicle_type: str | None = Query(None),
    limit: int = Query(50, le=500),
    window: tuple[datetime, datetime] = Depends(time_window),
    db: Session = Depends(get_db),
) -> dict:
    """Fuzzy lookup for when an operator has only part of a plate.

    A witness rarely reports a full registration. Matching on any substring,
    optionally narrowed by vehicle type, is what makes the system usable from
    a real report rather than only from a perfect one.
    """
    start, end = window
    frag = normalize(partial)
    stmt = select(Observation).where(
        and_(Observation.ts >= start, Observation.ts <= end,
             Observation.plate_norm.like(f"%{frag}%"))
    )
    if vehicle_type:
        stmt = stmt.where(Observation.vehicle_type == vehicle_type)
    rows = db.execute(stmt.order_by(Observation.ts.desc()).limit(limit * 4)).scalars().all()

    grouped: dict[str, dict] = {}
    for r in rows:
        g = grouped.setdefault(r.plate_norm, {
            "plate": r.plate_norm, "sightings": 0, "cameras": set(),
            "vehicle_types": set(), "first_seen": r.ts, "last_seen": r.ts,
            "best_confidence": 0.0,
        })
        g["sightings"] += 1
        g["cameras"].add(r.camera_id)
        g["vehicle_types"].add(r.vehicle_type)
        g["first_seen"] = min(g["first_seen"], r.ts)
        g["last_seen"] = max(g["last_seen"], r.ts)
        g["best_confidence"] = max(g["best_confidence"], r.plate_confidence)

    out = [
        {**g, "cameras": sorted(g["cameras"]), "vehicle_types": sorted(g["vehicle_types"]),
         "first_seen": g["first_seen"].isoformat(), "last_seen": g["last_seen"].isoformat(),
         "best_confidence": round(g["best_confidence"], 4)}
        for g in grouped.values()
    ]
    out.sort(key=lambda r: r["sightings"], reverse=True)
    return {"query": frag, "matches": out[:limit], "total_matches": len(out)}
