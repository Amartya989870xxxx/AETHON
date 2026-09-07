"""Request/response contracts for the HTTP API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from .anpr.plate_format import normalize


class PlateEventIn(BaseModel):
    """The event a camera/edge node posts to the core.

    This is the shared schema from the design brief — the single contract every
    camera speaks, and the reason three engines can consume one stream instead
    of needing three bespoke integrations.
    """

    camera_id: str
    timestamp: datetime
    plate_text: str
    plate_confidence: float = Field(ge=0.0, le=1.0)
    vehicle_type: str = "unknown"
    direction: str = "unknown"
    lane: int = 1
    speed_estimate_kmph: float | None = None
    condition: str = "day_clear"
    frames_fused: int = 1
    frame_ref: str | None = None

    @field_validator("plate_text")
    @classmethod
    def _norm(cls, v: str) -> str:
        return normalize(v)


class ObservationOut(BaseModel):
    id: int
    camera_id: str
    ts: datetime
    plate_text: str
    plate_norm: str
    plate_confidence: float
    vehicle_type: str
    direction: str
    lane: int
    speed_estimate_kmph: float | None
    frames_fused: int
    format_valid: bool
    repairs: list
    condition: str
    frame_ref: str | None

    model_config = {"from_attributes": True}


class BlacklistIn(BaseModel):
    plate_text: str
    reason: str
    severity: str = "high"
    added_by: str = "operator"

    @field_validator("plate_text")
    @classmethod
    def _norm(cls, v: str) -> str:
        return normalize(v)


class BlacklistOut(BaseModel):
    id: int
    plate_norm: str
    reason: str
    severity: str
    added_by: str
    added_at: datetime
    active: bool

    model_config = {"from_attributes": True}


class AlertOut(BaseModel):
    id: int
    alert_type: str
    severity: str
    plate_norm: str
    camera_id: str | None
    observation_id: int | None
    confidence: float
    status: str
    title: str
    evidence: dict
    created_at: datetime
    acknowledged_by: str | None

    model_config = {"from_attributes": True}


class AcknowledgeIn(BaseModel):
    actor: str
    disposition: str = "confirmed"      # confirmed | false_positive | escalated
    note: str = ""
