"""Component 3 — macro traffic-flow analytics.

Turns the raw observation stream into city-wide understanding that does not
depend on any individual plate. Two properties matter:

  * It degrades gracefully. Counting and classifying a vehicle is a far lower
    bar than reading its plate, so density and speed stay accurate at cameras
    where OCR confidence is poor. Analytics never gates on plate quality.

  * Congestion is relative, not absolute. A segment is congested when it is
    busy *compared to its own history for this weekday and hour*. A fixed
    global threshold would flag every arterial at 9am and miss a 2am jam that
    actually signals an incident.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, delete, func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Camera, ODFlow, Observation, TrafficAggregate
from .camera_graph import CameraGraph


def floor_bucket(ts: datetime, seconds: int) -> datetime:
    """Snap a timestamp down to its aggregation bucket."""
    ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    epoch = int(ts.timestamp()) // seconds * seconds
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


@dataclass
class BucketStats:
    count: int
    avg_speed: float | None
    directions: dict
    classes: dict


class AnalyticsEngine:
    def __init__(self, db: Session, graph: CameraGraph):
        self.db = db
        self.graph = graph
        self.cfg = settings.analytics

    # ---- congestion scoring ---------------------------------------------
    def congestion_score(self, count: int, avg_speed: float | None, lanes: int) -> float:
        """Blend of how many vehicles and how slowly they are moving.

        Either alone is misleading: a busy free-flowing expressway is not
        congested, and an empty road with one slow truck is not either. It is
        the combination — high demand *and* depressed speed — that defines it.
        """
        per_lane_capacity = self.cfg.saturation_count * max(1, lanes) / 2.0
        density_term = min(1.0, count / per_lane_capacity) if per_lane_capacity else 0.0
        if avg_speed is None:
            speed_term = 0.0
        else:
            speed_term = min(1.0, max(0.0, 1.0 - (avg_speed / self.cfg.free_flow_kmph)))
        return round(0.5 * density_term + 0.5 * speed_term, 4)

    # ---- aggregation -----------------------------------------------------
    def aggregate(self, start: datetime, end: datetime) -> int:
        """Roll raw observations into per-camera, per-bucket statistics."""
        bucket_s = self.cfg.bucket_seconds
        rows = self.db.execute(
            select(Observation).where(and_(Observation.ts >= start, Observation.ts <= end))
        ).scalars().all()
        if not rows:
            return 0

        cameras = {c.camera_id: c for c in self.db.execute(select(Camera)).scalars().all()}
        buckets: dict[tuple[datetime, str], list[Observation]] = defaultdict(list)
        for r in rows:
            buckets[(floor_bucket(r.ts, bucket_s), r.camera_id)].append(r)

        # Recompute cleanly for the window rather than merging partial state.
        self.db.execute(
            delete(TrafficAggregate).where(
                and_(TrafficAggregate.bucket_start >= floor_bucket(start, bucket_s),
                     TrafficAggregate.bucket_start <= end)
            )
        )

        written: list[TrafficAggregate] = []
        for (bucket, cam_id), obs in buckets.items():
            cam = cameras.get(cam_id)
            if cam is None:
                continue
            speeds = [o.speed_estimate_kmph for o in obs if o.speed_estimate_kmph]
            avg_speed = round(statistics.mean(speeds), 2) if speeds else None
            score = self.congestion_score(len(obs), avg_speed, cam.lanes)
            written.append(TrafficAggregate(
                bucket_start=bucket, bucket_seconds=bucket_s, camera_id=cam_id,
                road_segment=cam.road_segment, zone=cam.zone,
                vehicle_count=len(obs), avg_speed_kmph=avg_speed,
                density_per_lane=round(len(obs) / max(1, cam.lanes), 3),
                direction_distribution=dict(Counter(o.direction for o in obs)),
                class_distribution=dict(Counter(o.vehicle_type for o in obs)),
                congestion_score=score,
            ))
        self.db.add_all(written)
        self.db.flush()
        self._score_against_baselines(written)
        return len(written)

    def _score_against_baselines(self, rows: list[TrafficAggregate]) -> None:
        """Compare each bucket to its segment's own weekday+hour history."""
        history = self._baselines()
        for row in rows:
            key = (row.road_segment, row.bucket_start.weekday(), row.bucket_start.hour)
            samples = history.get(key, [])
            if len(samples) < self.cfg.min_baseline_samples:
                # Not enough history to judge relatively — fall back to an
                # absolute reading and say so via a null z-score.
                row.is_congested = row.congestion_score >= 0.75
                continue
            mean = statistics.mean(samples)
            std = statistics.pstdev(samples) or 0.05
            row.baseline_mean = round(mean, 4)
            row.baseline_std = round(std, 4)
            row.z_score = round((row.congestion_score - mean) / std, 3)
            row.is_congested = row.z_score >= self.cfg.congestion_z_threshold

    def _baselines(self) -> dict[tuple[str, int, int], list[float]]:
        """Historical congestion scores keyed by (segment, weekday, hour)."""
        out: dict[tuple[str, int, int], list[float]] = defaultdict(list)
        for r in self.db.execute(select(TrafficAggregate)).scalars().all():
            b = r.bucket_start if r.bucket_start.tzinfo else r.bucket_start.replace(tzinfo=timezone.utc)
            out[(r.road_segment, b.weekday(), b.hour)].append(r.congestion_score)
        return out

    # ---- origin-destination ---------------------------------------------
    def compute_od(self, start: datetime, end: datetime) -> int:
        """Zone-to-zone trip counts.

        Built from plates in aggregate, then discarded: an OD cell records that
        N vehicles went from one zone to another, never which ones. This is the
        aggregated, identity-free half of the privacy split.
        """
        rows = self.db.execute(
            select(Observation).where(and_(Observation.ts >= start, Observation.ts <= end))
            .order_by(Observation.ts)
        ).scalars().all()

        by_plate: dict[str, list[Observation]] = defaultdict(list)
        for r in rows:
            by_plate[r.plate_norm].append(r)

        trips: dict[tuple[datetime, str, str], list[float]] = defaultdict(list)
        for _plate, obs in by_plate.items():
            if len(obs) < 2:
                continue
            origin = self.graph.zone_of(obs[0].camera_id)
            dest = self.graph.zone_of(obs[-1].camera_id)
            if not origin or not dest or origin == dest:
                continue
            first = obs[0].ts if obs[0].ts.tzinfo else obs[0].ts.replace(tzinfo=timezone.utc)
            last = obs[-1].ts if obs[-1].ts.tzinfo else obs[-1].ts.replace(tzinfo=timezone.utc)
            bucket = floor_bucket(first, 3600)
            trips[(bucket, origin, dest)].append((last - first).total_seconds())

        self.db.execute(
            delete(ODFlow).where(and_(ODFlow.bucket_start >= floor_bucket(start, 3600),
                                      ODFlow.bucket_start <= end))
        )
        self.db.add_all([
            ODFlow(bucket_start=b, origin_zone=o, dest_zone=d,
                   trip_count=len(durations),
                   avg_duration_s=round(statistics.mean(durations), 1))
            for (b, o, d), durations in trips.items()
        ])
        self.db.flush()
        return len(trips)

    # ---- read models for the dashboard ----------------------------------
    def heatmap(self, at: datetime | None = None, window_minutes: int = 15) -> dict:
        """GeoJSON congestion overlay for the map layer."""
        end = at or datetime.now(timezone.utc)
        start = end - timedelta(minutes=window_minutes)
        rows = self.db.execute(
            select(TrafficAggregate).where(
                and_(TrafficAggregate.bucket_start >= start,
                     TrafficAggregate.bucket_start <= end)
            )
        ).scalars().all()

        latest: dict[str, TrafficAggregate] = {}
        for r in rows:
            cur = latest.get(r.camera_id)
            if cur is None or r.bucket_start > cur.bucket_start:
                latest[r.camera_id] = r

        features = []
        for cam_id, agg in latest.items():
            node = self.graph.nodes.get(cam_id)
            if not node:
                continue
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [node.lon, node.lat]},
                "properties": {
                    "camera_id": cam_id, "camera_name": node.name,
                    "road_segment": agg.road_segment, "zone": agg.zone,
                    "vehicle_count": agg.vehicle_count,
                    "avg_speed_kmph": agg.avg_speed_kmph,
                    "density_per_lane": agg.density_per_lane,
                    "congestion_score": agg.congestion_score,
                    "z_score": agg.z_score,
                    "is_congested": agg.is_congested,
                    "bucket_start": agg.bucket_start.isoformat(),
                },
            })
        return {"type": "FeatureCollection", "features": features,
                "window": {"start": start.isoformat(), "end": end.isoformat()}}

    def bottlenecks(self, start: datetime, end: datetime, limit: int = 10) -> list[dict]:
        """Segments that spend the most time above their own baseline."""
        rows = self.db.execute(
            select(
                TrafficAggregate.road_segment,
                func.count().label("buckets"),
                func.sum(case((TrafficAggregate.is_congested.is_(True), 1), else_=0)).label("congested"),
                func.avg(TrafficAggregate.congestion_score).label("avg_score"),
                func.avg(TrafficAggregate.avg_speed_kmph).label("avg_speed"),
                func.sum(TrafficAggregate.vehicle_count).label("volume"),
            ).where(and_(TrafficAggregate.bucket_start >= start,
                         TrafficAggregate.bucket_start <= end))
            .group_by(TrafficAggregate.road_segment)
        ).all()

        out = []
        for seg, buckets, congested, avg_score, avg_speed, volume in rows:
            congested = int(congested or 0)
            out.append({
                "road_segment": seg,
                "buckets_observed": buckets,
                "buckets_congested": congested,
                "congested_share": round(congested / buckets, 3) if buckets else 0.0,
                "avg_congestion_score": round(float(avg_score or 0), 4),
                "avg_speed_kmph": round(float(avg_speed), 2) if avg_speed else None,
                "total_vehicles": int(volume or 0),
            })
        out.sort(key=lambda r: (r["congested_share"], r["avg_congestion_score"]), reverse=True)
        return out[:limit]

    def segment_timeseries(self, segment: str, start: datetime, end: datetime) -> list[dict]:
        rows = self.db.execute(
            select(TrafficAggregate).where(
                and_(TrafficAggregate.road_segment == segment,
                     TrafficAggregate.bucket_start >= start,
                     TrafficAggregate.bucket_start <= end)
            ).order_by(TrafficAggregate.bucket_start)
        ).scalars().all()
        merged: dict[datetime, dict] = {}
        for r in rows:
            slot = merged.setdefault(r.bucket_start, {
                "bucket_start": r.bucket_start.isoformat(), "vehicle_count": 0,
                "speeds": [], "congestion_score": 0.0, "cameras": 0,
            })
            slot["vehicle_count"] += r.vehicle_count
            slot["cameras"] += 1
            slot["congestion_score"] += r.congestion_score
            if r.avg_speed_kmph:
                slot["speeds"].append(r.avg_speed_kmph)
        out = []
        for slot in merged.values():
            n = max(1, slot["cameras"])
            out.append({
                "bucket_start": slot["bucket_start"],
                "vehicle_count": slot["vehicle_count"],
                "avg_speed_kmph": round(statistics.mean(slot["speeds"]), 2) if slot["speeds"] else None,
                "congestion_score": round(slot["congestion_score"] / n, 4),
            })
        return sorted(out, key=lambda r: r["bucket_start"])

    def od_matrix(self, start: datetime, end: datetime) -> dict:
        rows = self.db.execute(
            select(ODFlow).where(and_(ODFlow.bucket_start >= start, ODFlow.bucket_start <= end))
        ).scalars().all()
        cells: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        durations: dict[str, list[float]] = defaultdict(list)
        for r in rows:
            cells[r.origin_zone][r.dest_zone] += r.trip_count
            if r.avg_duration_s:
                durations[f"{r.origin_zone}->{r.dest_zone}"].append(r.avg_duration_s)
        zones = sorted({z for z in cells} | {d for row in cells.values() for d in row})
        return {
            "zones": zones,
            "matrix": {o: {d: cells[o].get(d, 0) for d in zones} for o in zones},
            "avg_duration_s": {k: round(statistics.mean(v), 1) for k, v in durations.items()},
            "window": {"start": start.isoformat(), "end": end.isoformat()},
        }
