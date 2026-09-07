"""ORM models — the physical form of the data model in the design brief.

Every table maps to one entity in the spec's Section 10 data model, plus the
audit/lineage tables a deployable system needs (AuditLog, PlateProfile).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------
# Topology: where the cameras are and how the road network connects them.
# --------------------------------------------------------------------------
class Camera(Base):
    __tablename__ = "cameras"

    camera_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    road_segment: Mapped[str] = mapped_column(String(64), index=True)
    zone: Mapped[str] = mapped_column(String(64), index=True)
    facing_direction: Mapped[str] = mapped_column(String(16))
    lanes: Mapped[int] = mapped_column(Integer, default=2)
    # Restricted zones drive one of the route-anomaly rules.
    is_restricted: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    calibration: Mapped[dict] = mapped_column(JSON, default=dict)

    observations: Mapped[list["Observation"]] = relationship(back_populates="camera")


class CameraLink(Base):
    """A directed, drivable edge of the road graph between two cameras.

    ``distance_km`` is road-network distance, not straight-line — the whole
    plausibility check depends on that distinction.
    """

    __tablename__ = "camera_links"
    __table_args__ = (UniqueConstraint("from_camera", "to_camera", name="uq_link"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_camera: Mapped[str] = mapped_column(ForeignKey("cameras.camera_id"), index=True)
    to_camera: Mapped[str] = mapped_column(ForeignKey("cameras.camera_id"), index=True)
    distance_km: Mapped[float] = mapped_column(Float)
    # Compass direction a vehicle must be travelling at `from_camera` to take
    # this edge. Used for the direction-consistency term.
    heading: Mapped[str] = mapped_column(String(16))
    road_name: Mapped[str] = mapped_column(String(80), default="")
    speed_limit_kmph: Mapped[float] = mapped_column(Float, default=50.0)


# --------------------------------------------------------------------------
# Component 1 output: one row per vehicle pass, per camera.
# --------------------------------------------------------------------------
class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        Index("ix_obs_plate_ts", "plate_norm", "ts"),
        Index("ix_obs_cam_ts", "camera_id", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.camera_id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    plate_text: Mapped[str] = mapped_column(String(24))
    # Normalised (upper, alphanumeric only) — every lookup uses this.
    plate_norm: Mapped[str] = mapped_column(String(24), index=True)
    plate_confidence: Mapped[float] = mapped_column(Float)

    vehicle_type: Mapped[str] = mapped_column(String(24), default="unknown")
    direction: Mapped[str] = mapped_column(String(16), default="unknown")
    lane: Mapped[int] = mapped_column(Integer, default=1)
    speed_estimate_kmph: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Recognition provenance — what the fusion stage actually saw. This is the
    # evidence attached to any alert this observation triggers.
    frames_fused: Mapped[int] = mapped_column(Integer, default=1)
    format_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    repairs: Mapped[list] = mapped_column(JSON, default=list)
    condition: Mapped[str] = mapped_column(String(24), default="day_clear", index=True)
    frame_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    frame_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    camera: Mapped["Camera"] = relationship(back_populates="observations")


# --------------------------------------------------------------------------
# Component 2 output.
# --------------------------------------------------------------------------
class Trajectory(Base):
    __tablename__ = "trajectories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plate_norm: Mapped[str] = mapped_column(String(24), index=True)
    from_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    to_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hop_count: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    total_distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    # Ordered [{observation_id, camera_id, ts, lat, lon, ...}] and the branches
    # the matcher considered and rejected (shown in the demo UI).
    path: Mapped[list] = mapped_column(JSON, default=list)
    rejected: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------
# Component 3 outputs.
# --------------------------------------------------------------------------
class TrafficAggregate(Base):
    __tablename__ = "traffic_aggregates"
    __table_args__ = (
        UniqueConstraint("bucket_start", "camera_id", name="uq_bucket_cam"),
        Index("ix_agg_seg_bucket", "road_segment", "bucket_start"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    bucket_seconds: Mapped[int] = mapped_column(Integer)
    camera_id: Mapped[str] = mapped_column(String(32), index=True)
    road_segment: Mapped[str] = mapped_column(String(64), index=True)
    zone: Mapped[str] = mapped_column(String(64), index=True)

    vehicle_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_speed_kmph: Mapped[float | None] = mapped_column(Float, nullable=True)
    density_per_lane: Mapped[float] = mapped_column(Float, default=0.0)
    direction_distribution: Mapped[dict] = mapped_column(JSON, default=dict)
    class_distribution: Mapped[dict] = mapped_column(JSON, default=dict)

    # Congestion is scored against this segment's own history for this
    # weekday+hour, so "busy at 9am" is normal and "busy at 2am" is a signal.
    congestion_score: Mapped[float] = mapped_column(Float, default=0.0)
    baseline_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_std: Mapped[float | None] = mapped_column(Float, nullable=True)
    z_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_congested: Mapped[bool] = mapped_column(Boolean, default=False)


class ODFlow(Base):
    """Origin-destination counts between zones, per time bucket."""

    __tablename__ = "od_flows"
    __table_args__ = (
        UniqueConstraint("bucket_start", "origin_zone", "dest_zone", name="uq_od"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    origin_zone: Mapped[str] = mapped_column(String(64), index=True)
    dest_zone: Mapped[str] = mapped_column(String(64), index=True)
    trip_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)


# --------------------------------------------------------------------------
# Component 4.
# --------------------------------------------------------------------------
class BlacklistEntry(Base):
    __tablename__ = "blacklist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plate_norm: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    reason: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(16), default="high")
    added_by: Mapped[str] = mapped_column(String(80), default="system")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alert_dedupe", "dedupe_key", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    plate_norm: Mapped[str] = mapped_column(String(24), index=True)
    camera_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    observation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    # Triggering evidence — never an alert without it.
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ZonePermit(Base):
    """Authorisation for a vehicle to use a restricted corridor.

    Without this the restricted-zone rule alerts on every legitimate delivery
    truck, which is exactly the false-positive flood that gets an alerting
    system muted by its operators.
    """

    __tablename__ = "zone_permits"
    __table_args__ = (UniqueConstraint("plate_norm", "zone", name="uq_permit"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plate_norm: Mapped[str] = mapped_column(String(24), index=True)
    zone: Mapped[str] = mapped_column(String(64), index=True)
    issued_by: Mapped[str] = mapped_column(String(80), default="city_transport_authority")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    """Every identity-sensitive read and every alert state change lands here."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    subject: Mapped[str] = mapped_column(String(120), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class PlateProfile(Base):
    """Rolling behavioural baseline per plate — what 'normal' looks like for
    this vehicle. The route-anomaly rules compare against this rather than
    against a global rule."""

    __tablename__ = "plate_profiles"

    plate_norm: Mapped[str] = mapped_column(String(24), primary_key=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sighting_count: Mapped[int] = mapped_column(Integer, default=0)
    # {"0": 3, "9": 41, ...} counts per hour-of-day
    hour_histogram: Mapped[dict] = mapped_column(JSON, default=dict)
    zone_histogram: Mapped[dict] = mapped_column(JSON, default=dict)
    known_vehicle_types: Mapped[dict] = mapped_column(JSON, default=dict)
