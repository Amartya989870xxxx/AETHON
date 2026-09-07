"""Central configuration. Every tunable the engines read lives here, so a
judge/operator can retune the system without touching engine code."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)


def _f(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _i(name: str, default: int) -> int:
    return int(os.getenv(name, default))


@dataclass(frozen=True)
class ANPRConfig:
    """Component 1 — recognition thresholds."""
    # A read below this never drives an alert; it is still stored so the
    # trajectory engine can use it as a weak candidate.
    min_alert_confidence: float = _f("ANPR_MIN_ALERT_CONF", 0.80)
    # Below this we abstain entirely rather than guess (dirty/damaged plates).
    min_store_confidence: float = _f("ANPR_MIN_STORE_CONF", 0.35)
    # Frames fused per vehicle pass before emitting one observation.
    fusion_window: int = _i("ANPR_FUSION_WINDOW", 7)
    # Format validator may repair at most this many characters.
    max_format_repairs: int = _i("ANPR_MAX_REPAIRS", 2)
    # Confidence multiplier applied when the format validator had to repair.
    repair_confidence_penalty: float = _f("ANPR_REPAIR_PENALTY", 0.93)


@dataclass(frozen=True)
class TrajectoryConfig:
    """Component 2 — graph matching over the camera/road network."""
    # Plausible vehicle speed envelope on urban roads (km/h).
    min_speed_kmph: float = _f("TRAJ_MIN_SPEED", 4.0)
    max_speed_kmph: float = _f("TRAJ_MAX_SPEED", 110.0)
    # A hop may span at most this many missed cameras before we break the path.
    max_skipped_hops: int = _i("TRAJ_MAX_SKIPS", 2)
    # Scoring weights (must sum to ~1 for interpretable scores).
    w_time: float = _f("TRAJ_W_TIME", 0.45)
    w_direction: float = _f("TRAJ_W_DIR", 0.25)
    w_ocr: float = _f("TRAJ_W_OCR", 0.30)
    # Each skipped camera costs this much score — prefers dense evidence.
    skip_penalty: float = _f("TRAJ_SKIP_PENALTY", 0.12)
    # Fuzzy plate search: max edit distance when the exact plate is sparse.
    fuzzy_edit_distance: int = _i("TRAJ_FUZZY_ED", 1)
    # A fuzzy-matched observation is down-weighted by this factor.
    fuzzy_weight: float = _f("TRAJ_FUZZY_WEIGHT", 0.6)
    # Two sightings closer than this are the same pass, not a hop.
    min_hop_seconds: float = _f("TRAJ_MIN_HOP_S", 5.0)


@dataclass(frozen=True)
class AnalyticsConfig:
    """Component 3 — aggregation and congestion scoring."""
    bucket_seconds: int = _i("ANALYTICS_BUCKET_S", 300)
    # Free-flow reference speed used to normalise the speed-drop term.
    free_flow_kmph: float = _f("ANALYTICS_FREE_FLOW", 50.0)
    # Vehicles per bucket that saturate the density term for one camera.
    saturation_count: float = _f("ANALYTICS_SATURATION", 60.0)
    # A segment is congested when its z-score vs its own (weekday,hour)
    # baseline exceeds this. Per-segment, not a global threshold.
    congestion_z_threshold: float = _f("ANALYTICS_Z_THRESHOLD", 1.5)
    # Baselines need at least this many historical samples to be trusted.
    min_baseline_samples: int = _i("ANALYTICS_MIN_SAMPLES", 3)


@dataclass(frozen=True)
class AlertConfig:
    """Component 4 — blacklist and route anomalies."""
    # Same (plate, type) will not re-alert inside this window.
    dedupe_seconds: int = _i("ALERT_DEDUPE_S", 900)
    # Fuzzy blacklist match needs a stronger read than an exact match.
    fuzzy_min_confidence: float = _f("ALERT_FUZZY_MIN_CONF", 0.88)
    # Speed above this between two cameras is physically implausible.
    impossible_speed_kmph: float = _f("ALERT_IMPOSSIBLE_SPEED", 130.0)
    # Dwelling longer than this inside one zone counts as loitering.
    loiter_seconds: int = _i("ALERT_LOITER_S", 2700)
    loiter_min_sightings: int = _i("ALERT_LOITER_MIN_HITS", 4)
    # Odd-hours window (local): plate active here that is never active here
    # historically raises an anomaly.
    odd_hours: tuple[int, int] = (1, 5)
    # Clone detection: same plate at two cameras that cannot both be true.
    clone_min_confidence: float = _f("ALERT_CLONE_MIN_CONF", 0.85)


@dataclass(frozen=True)
class Settings:
    app_name: str = "PlateTrail"
    version: str = "0.1.0"
    ps_id: str = "26127"
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR/'platetrail.db'}")
    # Raw imagery retention (privacy): frames are dropped after this.
    frame_retention_seconds: int = _i("FRAME_RETENTION_S", 3600)
    anpr: ANPRConfig = field(default_factory=ANPRConfig)
    trajectory: TrajectoryConfig = field(default_factory=TrajectoryConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)


settings = Settings()
