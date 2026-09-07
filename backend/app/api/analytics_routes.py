"""Component 3's read models: heatmap, bottlenecks, OD matrix, trends."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..engines.analytics import AnalyticsEngine
from ..engines.camera_graph import CameraGraph
from .deps import get_graph, time_window

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _engine(db: Session, graph: CameraGraph) -> AnalyticsEngine:
    return AnalyticsEngine(db, graph)


@router.get("/heatmap")
def heatmap(
    window_minutes: int = Query(15, ge=5, le=240),
    at: datetime | None = Query(None),
    db: Session = Depends(get_db),
    graph: CameraGraph = Depends(get_graph),
) -> dict:
    """Live congestion overlay as GeoJSON, keyed by congestion score."""
    return _engine(db, graph).heatmap(at, window_minutes)


@router.get("/bottlenecks")
def bottlenecks(
    limit: int = Query(10, le=50),
    window: tuple[datetime, datetime] = Depends(time_window),
    db: Session = Depends(get_db),
    graph: CameraGraph = Depends(get_graph),
) -> dict:
    """Segments spending the most time above their own historical baseline."""
    start, end = window
    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "bottlenecks": _engine(db, graph).bottlenecks(start, end, limit),
    }


@router.get("/od")
def od_matrix(
    window: tuple[datetime, datetime] = Depends(time_window),
    db: Session = Depends(get_db),
    graph: CameraGraph = Depends(get_graph),
) -> dict:
    """Zone-to-zone trip counts. Aggregated and identity-free by construction."""
    start, end = window
    return _engine(db, graph).od_matrix(start, end)


@router.get("/segment/{segment}")
def segment_series(
    segment: str,
    window: tuple[datetime, datetime] = Depends(time_window),
    db: Session = Depends(get_db),
    graph: CameraGraph = Depends(get_graph),
) -> dict:
    """Time series for one road segment — the 'when does this road congest'
    question the problem statement names directly."""
    start, end = window
    return {
        "road_segment": segment,
        "series": _engine(db, graph).segment_timeseries(segment, start, end),
    }


@router.post("/recompute")
def recompute(
    window: tuple[datetime, datetime] = Depends(time_window),
    db: Session = Depends(get_db),
    graph: CameraGraph = Depends(get_graph),
) -> dict:
    """Re-run aggregation over a window (normally a scheduled job)."""
    start, end = window
    engine = _engine(db, graph)
    buckets = engine.aggregate(start, end)
    od = engine.compute_od(start, end)
    db.commit()
    return {"buckets_written": buckets, "od_cells_written": od}


@router.get("/summary")
def summary(
    db: Session = Depends(get_db),
    graph: CameraGraph = Depends(get_graph),
) -> dict:
    """Everything the dashboard's header tiles need, in one call."""
    now = datetime.now(timezone.utc)
    engine = _engine(db, graph)
    day_start = now - timedelta(hours=24)
    hm = engine.heatmap(now, 30)
    congested = [f for f in hm["features"] if f["properties"]["is_congested"]]
    total = sum(f["properties"]["vehicle_count"] for f in hm["features"])
    speeds = [f["properties"]["avg_speed_kmph"] for f in hm["features"]
              if f["properties"]["avg_speed_kmph"]]
    return {
        "generated_at": now.isoformat(),
        "live_window_minutes": 30,
        "cameras_reporting": len(hm["features"]),
        "vehicles_in_window": total,
        "congested_cameras": [f["properties"]["camera_id"] for f in congested],
        "mean_speed_kmph": round(sum(speeds) / len(speeds), 2) if speeds else None,
        "top_bottlenecks": engine.bottlenecks(day_start, now, 5),
    }
