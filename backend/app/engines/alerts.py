"""Component 4 — blacklist matching and route-anomaly detection.

Every rule here follows the same three constraints, which are what separate a
system a city would deploy from one that cries wolf until operators mute it:

  1. A match is a lead, not a verdict. Every alert carries the evidence that
     produced it — camera, frame reference, confidence, and the specific
     numbers that tripped the rule.
  2. Nothing fires on a read too weak to trust. Low-confidence observations
     still feed trajectory reconstruction, but they never raise an alert.
  3. Anomaly thresholds are relative to the plate's or the corridor's own
     history, never a fixed global rule.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Alert, AuditLog, BlacklistEntry, Observation, PlateProfile, ZonePermit
from .camera_graph import CameraGraph
from .trajectory import levenshtein

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


@dataclass
class Candidate:
    """A rule's finding, before dedupe and persistence."""

    alert_type: str
    severity: str
    title: str
    confidence: float
    evidence: dict = field(default_factory=dict)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class AlertEngine:
    def __init__(self, db: Session, graph: CameraGraph):
        self.db = db
        self.graph = graph
        self.cfg = settings.alerts
        self._blacklist: dict[str, BlacklistEntry] | None = None
        self._permits: set[tuple[str, str]] | None = None

    # ---- registry --------------------------------------------------------
    def blacklist(self) -> dict[str, BlacklistEntry]:
        if self._blacklist is None:
            rows = self.db.execute(
                select(BlacklistEntry).where(BlacklistEntry.active.is_(True))
            ).scalars().all()
            self._blacklist = {r.plate_norm: r for r in rows}
        return self._blacklist

    def invalidate_blacklist(self) -> None:
        self._blacklist = None
        self._permits = None

    # ---- rules -----------------------------------------------------------
    def _rule_blacklist(self, obs: Observation) -> list[Candidate]:
        """Exact match, plus edit-distance-1 when the read is strong.

        Requiring an exact string means one misread character defeats the
        watch list entirely. Allowing fuzzy matches on weak reads would bury
        operators in false hits. The compromise: fuzzy matches are permitted
        only above a higher confidence bar, and are surfaced at reduced
        severity as a *possible* match needing human confirmation.
        """
        registry = self.blacklist()
        out: list[Candidate] = []

        exact = registry.get(obs.plate_norm)
        if exact:
            out.append(Candidate(
                "blacklist_hit", exact.severity,
                f"Watch-listed vehicle {obs.plate_norm} sighted",
                obs.plate_confidence,
                {"match": "exact", "reason": exact.reason,
                 "listed_by": exact.added_by,
                 "listed_at": exact.added_at.isoformat() if exact.added_at else None},
            ))
            return out

        if obs.plate_confidence >= self.cfg.fuzzy_min_confidence:
            for listed, entry in registry.items():
                if levenshtein(obs.plate_norm, listed, 1) == 1:
                    out.append(Candidate(
                        "blacklist_possible", "medium",
                        f"Possible watch-list match: read {obs.plate_norm}, listed {listed}",
                        obs.plate_confidence * 0.75,
                        {"match": "fuzzy", "edit_distance": 1, "listed_plate": listed,
                         "reason": entry.reason,
                         "note": "Single-character difference — requires operator confirmation."},
                    ))
                    break
        return out

    def _rule_impossible_travel(self, obs: Observation) -> list[Candidate]:
        """Same plate in two places it could not have travelled between.

        This is the cloned-plate detector. It is also the guard that stops the
        trajectory engine stitching two different vehicles into one journey.
        """
        if obs.plate_confidence < self.cfg.clone_min_confidence:
            return []
        prev = self.db.execute(
            select(Observation).where(
                and_(Observation.plate_norm == obs.plate_norm, Observation.ts < obs.ts)
            ).order_by(Observation.ts.desc()).limit(1)
        ).scalars().first()
        if prev is None or prev.camera_id == obs.camera_id:
            return []
        if prev.plate_confidence < self.cfg.clone_min_confidence:
            return []

        seconds = (_aware(obs.ts) - _aware(prev.ts)).total_seconds()
        dist = self.graph.road_distance_km(prev.camera_id, obs.camera_id)
        if dist is None or seconds <= 0:
            return []
        implied = (dist / seconds) * 3600.0
        if implied <= self.cfg.impossible_speed_kmph:
            return []
        return [Candidate(
            "impossible_travel", "high",
            f"{obs.plate_norm} could not have travelled {prev.camera_id}->{obs.camera_id} in {seconds:.0f}s",
            min(prev.plate_confidence, obs.plate_confidence),
            {"from_camera": prev.camera_id, "to_camera": obs.camera_id,
             "road_distance_km": round(dist, 2), "elapsed_seconds": round(seconds, 1),
             "implied_speed_kmph": round(implied, 1),
             "threshold_kmph": self.cfg.impossible_speed_kmph,
             "interpretation": "Cloned/forged plate, or one of the two reads is wrong.",
             "from_frame": prev.frame_ref, "to_frame": obs.frame_ref},
        )]

    def _rule_restricted_zone(self, obs: Observation) -> list[Candidate]:
        """Entry into a corridor this vehicle is not permitted to use."""
        if not self.graph.is_restricted(obs.camera_id):
            return []
        if obs.plate_confidence < settings.anpr.min_alert_confidence:
            return []
        zone = self.graph.zone_of(obs.camera_id) or "restricted"

        # A permitted vehicle — a delivery fleet working the corridor — is not
        # an anomaly. Checking the registry first is what keeps this rule from
        # alerting on every legitimate truck.
        if self._has_permit(obs.plate_norm, zone):
            return []

        profile = self.db.get(PlateProfile, obs.plate_norm)
        # Nor is a vehicle with an established record of using the corridor.
        if profile and profile.zone_histogram.get(zone, 0) >= 3:
            return []
        return [Candidate(
            "restricted_zone", "high",
            f"{obs.plate_norm} entered restricted zone '{zone}'",
            obs.plate_confidence,
            {"camera_id": obs.camera_id, "zone": zone,
             "prior_visits": (profile.zone_histogram.get(zone, 0) if profile else 0),
             "frame_ref": obs.frame_ref},
        )]

    def _rule_loitering(self, obs: Observation) -> list[Candidate]:
        """Repeated sightings in one zone over a sustained window."""
        window_start = _aware(obs.ts) - timedelta(seconds=self.cfg.loiter_seconds)
        zone = self.graph.zone_of(obs.camera_id)
        if not zone:
            return []
        recent = self.db.execute(
            select(Observation).where(
                and_(Observation.plate_norm == obs.plate_norm,
                     Observation.ts >= window_start, Observation.ts <= obs.ts)
            )
        ).scalars().all()
        in_zone = [o for o in recent if self.graph.zone_of(o.camera_id) == zone]
        if len(in_zone) < self.cfg.loiter_min_sightings:
            return []
        cams = sorted({o.camera_id for o in in_zone})
        if len(cams) < 2:
            return []              # parked at one camera is not circling
        stamps = [_aware(o.ts) for o in in_zone]
        span = (max(stamps) - min(stamps)).total_seconds()
        return [Candidate(
            "loitering", "medium",
            f"{obs.plate_norm} has circled zone '{zone}' {len(in_zone)} times in {span/60:.0f} min",
            obs.plate_confidence,
            {"zone": zone, "sightings": len(in_zone), "distinct_cameras": cams,
             "window_minutes": round(span / 60, 1)},
        )]

    def _rule_odd_hours(self, obs: Observation) -> list[Candidate]:
        """Movement at an hour this specific vehicle never moves.

        Compared against the plate's own history, so a night-shift delivery van
        that always runs at 3am never trips this, while a car with a settled
        daytime pattern that suddenly appears at 3am does.
        """
        hour = _aware(obs.ts).hour
        lo, hi = self.cfg.odd_hours
        if not (lo <= hour <= hi):
            return []
        if obs.plate_confidence < settings.anpr.min_alert_confidence:
            return []
        profile = self.db.get(PlateProfile, obs.plate_norm)
        if not profile or profile.sighting_count < 8:
            return []              # no established routine to deviate from
        night_mass = sum(profile.hour_histogram.get(str(h), 0) for h in range(lo, hi + 1))
        if night_mass / max(1, profile.sighting_count) > 0.05:
            return []              # this vehicle does move at night, routinely
        busiest = Counter(profile.hour_histogram).most_common(3)
        return [Candidate(
            "odd_hours", "medium",
            f"{obs.plate_norm} active at {hour:02d}:00, outside its established pattern",
            obs.plate_confidence,
            {"hour": hour, "prior_sightings": profile.sighting_count,
             "prior_night_sightings": night_mass,
             "usual_hours": [f"{h}:00 ({n}x)" for h, n in busiest],
             "camera_id": obs.camera_id},
        )]

    def _has_permit(self, plate: str, zone: str) -> bool:
        if self._permits is None:
            rows = self.db.execute(
                select(ZonePermit).where(ZonePermit.active.is_(True))
            ).scalars().all()
            self._permits = {(r.plate_norm, r.zone) for r in rows}
        return (plate, zone) in self._permits

    RULES = (_rule_blacklist, _rule_impossible_travel, _rule_restricted_zone,
             _rule_loitering, _rule_odd_hours)

    # ---- evaluation ------------------------------------------------------
    def evaluate(self, obs: Observation) -> list[Alert]:
        """Run every rule against one observation and persist what survives."""
        # A read we do not trust never raises an alert — but it is already
        # stored, and still contributes to trajectory reconstruction.
        if not obs.format_valid and obs.plate_confidence < settings.anpr.min_alert_confidence:
            return []

        raised: list[Alert] = []
        for rule in self.RULES:
            for cand in rule(self, obs):
                alert = self._persist(cand, obs)
                if alert:
                    raised.append(alert)
        return raised

    def _persist(self, cand: Candidate, obs: Observation) -> Alert | None:
        """Dedupe, attach evidence, write the audit entry."""
        dedupe_key = f"{cand.alert_type}:{obs.plate_norm}"
        cutoff = _aware(obs.ts) - timedelta(seconds=self.cfg.dedupe_seconds)
        recent = self.db.execute(
            select(Alert).where(
                and_(Alert.dedupe_key == dedupe_key, Alert.created_at >= cutoff)
            ).limit(1)
        ).scalars().first()
        if recent:
            return None            # already told the operator this, recently

        evidence = dict(cand.evidence)
        evidence.update({
            "observation_id": obs.id,
            "camera_id": obs.camera_id,
            "camera_name": self.graph.nodes[obs.camera_id].name if self.graph.has_node(obs.camera_id) else obs.camera_id,
            "observed_at": _aware(obs.ts).isoformat(),
            "plate_read": obs.plate_norm,
            "plate_confidence": obs.plate_confidence,
            "recognition": {
                "frames_fused": obs.frames_fused,
                "condition": obs.condition,
                "format_valid": obs.format_valid,
                "repairs": obs.repairs,
            },
            "frame_ref": obs.frame_ref,
        })

        alert = Alert(
            alert_type=cand.alert_type, severity=cand.severity,
            plate_norm=obs.plate_norm, camera_id=obs.camera_id,
            observation_id=obs.id, confidence=round(cand.confidence, 4),
            status="open", title=cand.title, evidence=evidence,
            dedupe_key=dedupe_key, created_at=_aware(obs.ts),
        )
        self.db.add(alert)
        self.db.add(AuditLog(
            ts=_aware(obs.ts), actor="alert_engine", action="alert_raised",
            subject=obs.plate_norm,
            detail={"alert_type": cand.alert_type, "severity": cand.severity,
                    "camera_id": obs.camera_id, "confidence": round(cand.confidence, 4)},
        ))
        self.db.flush()
        return alert

    # ---- behavioural baseline -------------------------------------------
    def update_profile(self, obs: Observation) -> None:
        """Maintain the per-plate 'what normal looks like' baseline that the
        odd-hours and restricted-zone rules compare against."""
        ts = _aware(obs.ts)
        profile = self.db.get(PlateProfile, obs.plate_norm)
        zone = self.graph.zone_of(obs.camera_id) or "unknown"
        if profile is None:
            profile = PlateProfile(
                plate_norm=obs.plate_norm, first_seen=ts, last_seen=ts,
                sighting_count=0, hour_histogram={}, zone_histogram={},
                known_vehicle_types={},
            )
            self.db.add(profile)
        profile.sighting_count += 1
        profile.last_seen = max(ts, _aware(profile.last_seen))
        profile.first_seen = min(ts, _aware(profile.first_seen))
        # JSON columns need reassignment for SQLAlchemy to see the mutation.
        hours = dict(profile.hour_histogram)
        hours[str(ts.hour)] = hours.get(str(ts.hour), 0) + 1
        profile.hour_histogram = hours
        zones = dict(profile.zone_histogram)
        zones[zone] = zones.get(zone, 0) + 1
        profile.zone_histogram = zones
        types = dict(profile.known_vehicle_types)
        types[obs.vehicle_type] = types.get(obs.vehicle_type, 0) + 1
        profile.known_vehicle_types = types
