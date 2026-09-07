"""Component 4's surface: alerts, the watch list, and the audit trail."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Alert, AuditLog, BlacklistEntry
from ..schemas import AcknowledgeIn, AlertOut, BlacklistIn, BlacklistOut
from .deps import time_window

router = APIRouter(prefix="/api", tags=["security"])


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    status: str | None = Query(None, description="open | acknowledged | dismissed"),
    alert_type: str | None = Query(None),
    severity: str | None = Query(None),
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
):
    stmt = select(Alert)
    if status:
        stmt = stmt.where(Alert.status == status)
    if alert_type:
        stmt = stmt.where(Alert.alert_type == alert_type)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    return db.execute(stmt.order_by(Alert.created_at.desc()).limit(limit)).scalars().all()


@router.get("/alerts/stats/summary")
def alert_stats(db: Session = Depends(get_db)) -> dict:
    """Alert mix and the false-positive rate operators are actually seeing."""
    rows = db.execute(select(Alert)).scalars().all()
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    dismissed = acknowledged = 0
    for a in rows:
        by_type[a.alert_type] = by_type.get(a.alert_type, 0) + 1
        by_severity[a.severity] = by_severity.get(a.severity, 0) + 1
        if a.status == "dismissed":
            dismissed += 1
        elif a.status == "acknowledged":
            acknowledged += 1
    reviewed = dismissed + acknowledged
    return {
        "total": len(rows),
        "open": len(rows) - reviewed,
        "by_type": by_type,
        "by_severity": by_severity,
        "reviewed": reviewed,
        "false_positive_rate": round(dismissed / reviewed, 4) if reviewed else None,
    }


@router.get("/alerts/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    return alert


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge(alert_id: int, payload: AcknowledgeIn, db: Session = Depends(get_db)):
    """Close the loop on an alert.

    Recording the disposition — confirmed, false positive, escalated — is not
    bookkeeping: it is the feedback signal for tuning thresholds. A rule whose
    alerts are consistently dismissed is a rule that needs changing, and
    without this you never find that out.
    """
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.status = "acknowledged" if payload.disposition != "false_positive" else "dismissed"
    alert.acknowledged_by = payload.actor
    alert.acknowledged_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        actor=payload.actor, action="alert_acknowledged", subject=alert.plate_norm,
        detail={"alert_id": alert.id, "alert_type": alert.alert_type,
                "disposition": payload.disposition, "note": payload.note},
    ))
    db.commit()
    return alert


@router.get("/blacklist", response_model=list[BlacklistOut])
def list_blacklist(active_only: bool = Query(True), db: Session = Depends(get_db)):
    stmt = select(BlacklistEntry)
    if active_only:
        stmt = stmt.where(BlacklistEntry.active.is_(True))
    return db.execute(stmt.order_by(BlacklistEntry.added_at.desc())).scalars().all()


@router.post("/blacklist", response_model=BlacklistOut, status_code=201)
def add_blacklist(payload: BlacklistIn, db: Session = Depends(get_db)):
    existing = db.execute(
        select(BlacklistEntry).where(BlacklistEntry.plate_norm == payload.plate_text)
    ).scalars().first()
    if existing:
        existing.active = True
        existing.reason = payload.reason
        existing.severity = payload.severity
        entry = existing
    else:
        entry = BlacklistEntry(
            plate_norm=payload.plate_text, reason=payload.reason,
            severity=payload.severity, added_by=payload.added_by,
        )
        db.add(entry)
    db.add(AuditLog(actor=payload.added_by, action="blacklist_add",
                    subject=payload.plate_text, detail={"reason": payload.reason}))
    db.commit()
    # The alert engine is constructed per request and reads the watch list on
    # first use, so a new entry is live for the very next observation.
    return entry


@router.delete("/blacklist/{plate}")
def remove_blacklist(plate: str, actor: str = Query("operator"), db: Session = Depends(get_db)):
    entry = db.execute(
        select(BlacklistEntry).where(BlacklistEntry.plate_norm == plate.upper())
    ).scalars().first()
    if not entry:
        raise HTTPException(404, "Not on the watch list")
    entry.active = False
    db.add(AuditLog(actor=actor, action="blacklist_remove", subject=entry.plate_norm, detail={}))
    db.commit()
    return {"plate_norm": entry.plate_norm, "active": False}


@router.get("/audit")
def audit_trail(
    actor: str | None = Query(None),
    action: str | None = Query(None),
    subject: str | None = Query(None),
    limit: int = Query(200, le=2000),
    window: tuple[datetime, datetime] = Depends(time_window),
    db: Session = Depends(get_db),
) -> dict:
    """Who looked up whom, and which alerts fired.

    A city-wide plate reader is a surveillance capability. The audit trail is
    what makes its use reviewable rather than merely trusted.
    """
    start, end = window
    stmt = select(AuditLog).where(and_(AuditLog.ts >= start, AuditLog.ts <= end))
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if subject:
        stmt = stmt.where(AuditLog.subject == subject.upper())
    rows = db.execute(stmt.order_by(AuditLog.ts.desc()).limit(limit)).scalars().all()
    return {
        "entries": [
            {"id": r.id, "ts": r.ts.isoformat(), "actor": r.actor,
             "action": r.action, "subject": r.subject, "detail": r.detail}
            for r in rows
        ],
        "count": len(rows),
    }
