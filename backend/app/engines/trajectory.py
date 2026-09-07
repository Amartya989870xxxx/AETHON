"""Component 2 — single-plate trajectory reconstruction.

Given a plate and a time window, rebuild the vehicle's chronological path
across every camera that saw it.

This is deliberately *not* "select where plate = X order by time". That naive
query breaks on the three things that actually happen in a city:

  * a misread character means the right vehicle is filed under a wrong plate,
  * a missed detection leaves a hole where a camera should have reported,
  * two vehicles genuinely share a plate string (clone, or a shared misread),
    and concatenating their sightings invents a journey nobody made.

Instead we treat it as a best-path search over a DAG of sightings, where an
edge exists only if the road network says that hop was physically possible,
and is scored on travel-time plausibility, direction consistency, and
recognition confidence. Rejected edges are retained with their reason, because
"why did you not include that sighting" is the first thing an operator asks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Observation, Trajectory
from .camera_graph import CameraGraph

# Typical urban cruising speed, used as the centre of the plausibility bell.
TYPICAL_URBAN_KMPH = 28.0


def levenshtein(a: str, b: str, cap: int = 2) -> int:
    """Edit distance with early exit — we only ever care about 0, 1 or 2."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def _aware(dt: datetime) -> datetime:
    """SQLite hands back naive datetimes; normalise to UTC-aware."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class Sighting:
    """One candidate observation, with how much we trust it as *this* plate."""

    observation_id: int
    camera_id: str
    ts: datetime
    plate_norm: str
    confidence: float
    direction: str
    vehicle_type: str
    speed_kmph: float | None
    condition: str
    edit_distance: int = 0       # 0 = exact plate match

    @property
    def match_weight(self) -> float:
        """Confidence in this sighting belonging to the queried plate."""
        if self.edit_distance == 0:
            return self.confidence
        return self.confidence * (settings.trajectory.fuzzy_weight ** self.edit_distance)


@dataclass
class Hop:
    from_index: int
    to_index: int
    seconds: float
    distance_km: float
    implied_speed_kmph: float
    hops_on_graph: int
    time_score: float
    direction_score: float
    ocr_score: float
    total: float
    intermediate_cameras: list[str] = field(default_factory=list)


@dataclass
class RejectedHop:
    from_camera: str
    to_camera: str
    from_ts: str
    to_ts: str
    reason: str
    detail: dict = field(default_factory=dict)


@dataclass
class TrajectoryResult:
    plate: str
    found: bool
    path: list[dict] = field(default_factory=list)
    hops: list[Hop] = field(default_factory=list)
    rejected: list[RejectedHop] = field(default_factory=list)
    score: float = 0.0
    total_distance_km: float = 0.0
    duration_seconds: float = 0.0
    candidates_considered: int = 0
    fuzzy_used: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "plate": self.plate,
            "found": self.found,
            "score": round(self.score, 4),
            "path": self.path,
            "hops": [h.__dict__ for h in self.hops],
            "rejected": [r.__dict__ for r in self.rejected],
            "total_distance_km": round(self.total_distance_km, 3),
            "duration_seconds": round(self.duration_seconds, 1),
            "candidates_considered": self.candidates_considered,
            "fuzzy_used": self.fuzzy_used,
            "note": self.note,
        }


class TrajectoryEngine:
    def __init__(self, db: Session, graph: CameraGraph):
        self.db = db
        self.graph = graph
        self.cfg = settings.trajectory

    # ---- candidate retrieval --------------------------------------------
    def _candidates(self, plate: str, start: datetime, end: datetime) -> list[Sighting]:
        """Exact matches, plus near-misses when the exact set is thin.

        The fuzzy pass is what recovers a vehicle whose plate was misread at
        one camera. It is only opened when evidence is sparse, and every fuzzy
        sighting is down-weighted so it can never outvote a clean read.
        """
        rows = self.db.execute(
            select(Observation).where(
                and_(Observation.plate_norm == plate,
                     Observation.ts >= start, Observation.ts <= end)
            ).order_by(Observation.ts)
        ).scalars().all()

        sightings = [self._to_sighting(r, 0) for r in rows]

        if len(sightings) < 2 and self.cfg.fuzzy_edit_distance > 0:
            near = self.db.execute(
                select(Observation).where(
                    and_(Observation.ts >= start, Observation.ts <= end,
                         Observation.plate_norm != plate)
                )
            ).scalars().all()
            for r in near:
                d = levenshtein(plate, r.plate_norm, self.cfg.fuzzy_edit_distance)
                if 0 < d <= self.cfg.fuzzy_edit_distance:
                    sightings.append(self._to_sighting(r, d))

        sightings.sort(key=lambda s: s.ts)
        return self._collapse_same_pass(sightings)

    def _to_sighting(self, r: Observation, edit_distance: int) -> Sighting:
        return Sighting(
            observation_id=r.id, camera_id=r.camera_id, ts=_aware(r.ts),
            plate_norm=r.plate_norm, confidence=r.plate_confidence,
            direction=r.direction, vehicle_type=r.vehicle_type,
            speed_kmph=r.speed_estimate_kmph, condition=r.condition,
            edit_distance=edit_distance,
        )

    def _collapse_same_pass(self, sightings: list[Sighting]) -> list[Sighting]:
        """Two reads from one camera seconds apart are one pass, not a hop."""
        out: list[Sighting] = []
        for s in sightings:
            if out and out[-1].camera_id == s.camera_id and \
                    (s.ts - out[-1].ts).total_seconds() < self.cfg.min_hop_seconds:
                if s.match_weight > out[-1].match_weight:
                    out[-1] = s          # keep the better read of the same pass
                continue
            out.append(s)
        return out

    # ---- hop scoring -----------------------------------------------------
    def _time_score(self, seconds: float, distance_km: float,
                    window: tuple[float, float]) -> float:
        """How natural is this travel time for this distance?

        Peaks at typical urban speed and decays toward the edges of the
        physically possible window. A hop at the very edge is accepted but
        scored low, so a better-explained alternative wins if one exists.
        """
        fastest, slowest = window
        if not (fastest <= seconds <= slowest):
            return 0.0
        expected = (distance_km / TYPICAL_URBAN_KMPH) * 3600.0
        if expected <= 0:
            return 0.0
        ratio = seconds / expected
        # Symmetric in log space: twice as slow is penalised like twice as fast.
        import math
        return round(max(0.0, 1.0 - abs(math.log(ratio)) / math.log(6.0)), 4)

    def _build_hop(self, i: int, j: int, a: Sighting, b: Sighting):
        """Score a candidate hop, or explain why it is impossible."""
        seconds = (b.ts - a.ts).total_seconds()
        if seconds < self.cfg.min_hop_seconds:
            return None, RejectedHop(a.camera_id, b.camera_id, a.ts.isoformat(),
                                     b.ts.isoformat(), "same_pass",
                                     {"seconds": round(seconds, 1)})

        if a.camera_id == b.camera_id:
            # The vehicle came back to a camera it already passed. That is a
            # real event (a loop, a U-turn), but it is not a direct hop — the
            # DP reaches it through the intermediate cameras instead.
            return None, RejectedHop(a.camera_id, b.camera_id, a.ts.isoformat(),
                                     b.ts.isoformat(), "returned_to_same_camera",
                                     {"seconds": round(seconds, 1)})

        dist = self.graph.road_distance_km(a.camera_id, b.camera_id)
        if dist is None:
            return None, RejectedHop(a.camera_id, b.camera_id, a.ts.isoformat(),
                                     b.ts.isoformat(), "unreachable",
                                     {"note": "no drivable path in road graph"})

        window = self.graph.travel_window_seconds(a.camera_id, b.camera_id)
        implied = (dist / seconds) * 3600.0 if seconds > 0 else 0.0

        # Physics is checked before bookkeeping. A hop that would require an
        # impossible speed is the cloned-plate signature, and saying so is far
        # more useful to an operator than "too many missed cameras".
        if window and seconds < window[0]:
            return None, RejectedHop(a.camera_id, b.camera_id, a.ts.isoformat(),
                                     b.ts.isoformat(), "physically_impossible",
                                     {"implied_speed_kmph": round(implied, 1),
                                      "distance_km": round(dist, 2),
                                      "seconds": round(seconds, 1),
                                      "max_speed_kmph": self.cfg.max_speed_kmph})
        if window and seconds > window[1]:
            return None, RejectedHop(a.camera_id, b.camera_id, a.ts.isoformat(),
                                     b.ts.isoformat(), "gap_too_long",
                                     {"seconds": round(seconds, 1),
                                      "max_plausible_s": round(window[1], 1)})

        hops = self.graph.hop_count(a.camera_id, b.camera_id) or 1
        if hops - 1 > self.cfg.max_skipped_hops:
            return None, RejectedHop(a.camera_id, b.camera_id, a.ts.isoformat(),
                                     b.ts.isoformat(), "too_many_missed_cameras",
                                     {"cameras_skipped": hops - 1})

        t_score = self._time_score(seconds, dist, window)
        d_score = self.graph.direction_score(a.direction, a.camera_id, b.camera_id)
        o_score = (a.match_weight + b.match_weight) / 2.0

        total = (self.cfg.w_time * t_score
                 + self.cfg.w_direction * d_score
                 + self.cfg.w_ocr * o_score
                 - self.cfg.skip_penalty * (hops - 1))

        path = self.graph.path_between(a.camera_id, b.camera_id) or []
        return Hop(i, j, round(seconds, 1), round(dist, 3), round(implied, 1),
                   hops, t_score, d_score, round(o_score, 4), round(total, 4),
                   path[1:-1]), None

    # ---- main entry ------------------------------------------------------
    def reconstruct(self, plate: str, start: datetime, end: datetime) -> TrajectoryResult:
        plate = plate.upper().strip()
        sightings = self._candidates(plate, start, end)
        result = TrajectoryResult(plate=plate, found=False,
                                  candidates_considered=len(sightings))
        result.fuzzy_used = any(s.edit_distance > 0 for s in sightings)

        if not sightings:
            result.note = "No sightings of this plate in the requested window."
            return result

        if len(sightings) == 1:
            s = sightings[0]
            result.found = True
            result.path = [self._path_node(s)]
            result.score = s.match_weight
            result.note = "Single sighting — no route to reconstruct."
            return result

        # Build the DAG of physically possible hops.
        n = len(sightings)
        edges: dict[int, list[Hop]] = {i: [] for i in range(n)}
        for i in range(n):
            for j in range(i + 1, n):
                hop, rejected = self._build_hop(i, j, sightings[i], sightings[j])
                if hop:
                    edges[i].append(hop)
                elif rejected and rejected.reason != "same_pass":
                    result.rejected.append(rejected)

        # Best-path DP. Sightings are time-ordered, so every edge points
        # forward and the graph is acyclic — one linear pass suffices.
        best = [s.match_weight for s in sightings]
        prev: list[int | None] = [None] * n
        best_hop: list[Hop | None] = [None] * n
        for i in range(n):
            for hop in edges[i]:
                cand = best[i] + hop.total + sightings[hop.to_index].match_weight
                if cand > best[hop.to_index]:
                    best[hop.to_index] = cand
                    prev[hop.to_index] = i
                    best_hop[hop.to_index] = hop

        end_idx = max(range(n), key=lambda k: best[k])
        chain: list[int] = []
        cur: int | None = end_idx
        while cur is not None:
            chain.append(cur)
            cur = prev[cur]
        chain.reverse()

        if len(chain) == 1:
            # Nothing linked — the sightings exist but no pair is a plausible
            # hop. Reporting that honestly beats inventing a route.
            result.found = True
            result.path = [self._path_node(sightings[chain[0]])]
            result.score = sightings[chain[0]].match_weight
            result.note = ("Sightings found but none form a physically plausible "
                           "route — possible cloned plate or shared misread.")
            return result

        result.found = True
        result.path = [self._path_node(sightings[k]) for k in chain]
        result.hops = [best_hop[k] for k in chain[1:] if best_hop[k]]
        result.total_distance_km = sum(h.distance_km for h in result.hops)
        result.duration_seconds = (sightings[chain[-1]].ts - sightings[chain[0]].ts).total_seconds()
        # Report mean score per hop so a long trajectory is not flattered by
        # simply having more of them.
        result.score = round(sum(h.total for h in result.hops) / len(result.hops), 4)
        skipped = sum(h.hops_on_graph - 1 for h in result.hops)
        if skipped:
            result.note = (f"Route reconstructed across {skipped} camera(s) that did not "
                           f"report this plate — bridged using road-graph travel times.")
        return result

    def _path_node(self, s: Sighting) -> dict:
        node = self.graph.nodes.get(s.camera_id)
        return {
            "observation_id": s.observation_id,
            "camera_id": s.camera_id,
            "camera_name": node.name if node else s.camera_id,
            "lat": node.lat if node else None,
            "lon": node.lon if node else None,
            "zone": node.zone if node else None,
            "road_segment": node.road_segment if node else None,
            "timestamp": s.ts.isoformat(),
            "direction": s.direction,
            "confidence": round(s.confidence, 4),
            "vehicle_type": s.vehicle_type,
            "condition": s.condition,
            "plate_read": s.plate_norm,
            "edit_distance": s.edit_distance,
            "match": "exact" if s.edit_distance == 0 else f"fuzzy(d={s.edit_distance})",
        }

    def persist(self, result: TrajectoryResult) -> Trajectory | None:
        if not result.found or len(result.path) < 2:
            return None
        row = Trajectory(
            plate_norm=result.plate,
            from_ts=datetime.fromisoformat(result.path[0]["timestamp"]),
            to_ts=datetime.fromisoformat(result.path[-1]["timestamp"]),
            hop_count=len(result.hops),
            score=result.score,
            total_distance_km=result.total_distance_km,
            path=result.path,
            rejected=[r.__dict__ for r in result.rejected],
        )
        self.db.add(row)
        self.db.flush()
        return row
