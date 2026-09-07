"""Component 1 orchestrator: raw vehicle pass -> one validated plate event.

    frames -> detect -> rectify -> per-frame OCR -> multi-frame fusion
           -> format validate/repair -> confidence gate -> PlateEvent

The stages after recognition are the ones that carry the accuracy target, and
they run identically regardless of which `Recognizer` backend produced the
per-frame reads.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from ..config import ANPRConfig, settings
from .backends import Recognizer
from .fusion import FusedRead, fuse
from .plate_format import FormatResult, normalize, validate


@dataclass
class PlateEvent:
    """The single structured event every camera emits. This schema is the
    contract the three downstream engines share."""

    camera_id: str
    timestamp: datetime
    plate_text: str
    plate_norm: str
    plate_confidence: float
    vehicle_type: str = "unknown"
    direction: str = "unknown"
    lane: int = 1
    speed_estimate_kmph: float | None = None
    condition: str = "day_clear"

    # Recognition provenance — the evidence trail behind the read.
    frames_fused: int = 1
    frames_seen: int = 1
    agreement: float = 1.0
    contested_positions: list[int] = field(default_factory=list)
    format_valid: bool = True
    format_name: str | None = None
    repairs: list[dict] = field(default_factory=list)
    frame_ref: str | None = None

    @property
    def alertable(self) -> bool:
        """Whether this read is strong enough to drive an operator alert."""
        return self.plate_confidence >= settings.anpr.min_alert_confidence and self.format_valid

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class PipelineResult:
    event: PlateEvent | None
    abstained: bool = False
    reason: str = ""
    fused: FusedRead | None = None
    format_result: FormatResult | None = None


class ANPRPipeline:
    def __init__(self, recognizer: Recognizer, config: ANPRConfig | None = None):
        self.recognizer = recognizer
        self.cfg = config or settings.anpr

    def process_pass(self, context: dict) -> PipelineResult:
        """Run one vehicle pass through every stage.

        `context` carries camera_id, timestamp, condition, and either raw
        `frames` (production) or ground truth (simulation).
        """
        reads = self.recognizer.read_pass(context)
        if not reads:
            return PipelineResult(None, abstained=True, reason="no_detection")

        # Stage: multi-frame fusion. Redundancy across frames beats any single
        # frame's best guess.
        fused = fuse(reads)
        if fused is None:
            return PipelineResult(None, abstained=True, reason="fusion_failed")

        # Stage: format validation. Repairs visual confusions the structure of
        # an Indian plate makes unambiguous.
        fmt = validate(fused.text, max_repairs=self.cfg.max_format_repairs)

        confidence = fused.confidence
        if fmt.repair_count:
            # A repaired read is still a read, but it is not as good as a clean
            # one and must not pretend otherwise.
            confidence *= self.cfg.repair_confidence_penalty ** fmt.repair_count
        if not fmt.valid:
            # Unrecognised structure is a strong signal something is wrong
            # (occlusion, damage, a foreign plate) — cap the score hard.
            confidence = min(confidence, 0.45)

        confidence = round(min(1.0, confidence), 4)

        # Stage: confidence gate. Below the store threshold we abstain outright
        # rather than emit a plate nobody should trust.
        if confidence < self.cfg.min_store_confidence:
            return PipelineResult(
                None, abstained=True, reason="below_store_threshold",
                fused=fused, format_result=fmt,
            )

        plate = fmt.plate if fmt.valid else fused.text
        event = PlateEvent(
            camera_id=context["camera_id"],
            timestamp=context["timestamp"],
            plate_text=plate,
            plate_norm=normalize(plate),
            plate_confidence=confidence,
            vehicle_type=context.get("vehicle_type", "unknown"),
            direction=context.get("direction", "unknown"),
            lane=context.get("lane", 1),
            speed_estimate_kmph=context.get("speed_estimate_kmph"),
            condition=context.get("condition", "day_clear"),
            frames_fused=fused.frames_used,
            frames_seen=fused.frames_total,
            agreement=fused.agreement,
            contested_positions=fused.contested_positions,
            format_valid=fmt.valid,
            format_name=fmt.format_name,
            repairs=fmt.repairs,
            frame_ref=context.get("frame_ref"),
        )
        return PipelineResult(event, fused=fused, format_result=fmt)
