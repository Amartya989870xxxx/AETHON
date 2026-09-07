"""Shared FastAPI dependencies."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..engines.camera_graph import CameraGraph

_graph: CameraGraph | None = None


def get_graph(db: Session = Depends(get_db)) -> CameraGraph:
    """The road graph is small and changes only when cameras are
    added/moved, so it is built once and held resident."""
    global _graph
    if _graph is None:
        _graph = CameraGraph.from_db(db)
    return _graph


def reset_graph() -> None:
    global _graph
    _graph = None


def time_window(
    start: datetime | None = Query(None, description="ISO8601; defaults to 24h ago"),
    end: datetime | None = Query(None, description="ISO8601; defaults to now"),
) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    end = end or now
    start = start or (end - timedelta(hours=24))
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start, end
