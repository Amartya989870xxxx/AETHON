"""Pluggable recognition backends.

The ANPR pipeline never imports a model directly. It talks to the
`Recognizer` protocol, so the same pipeline code runs against:

  * `YoloCrnnRecognizer` — production path. YOLO detects vehicle + plate, the
    crop is rectified, a CRNN/PARSeq head reads characters. Requires the model
    weights and a GPU-class edge box.
  * `SimulatedRecognizer` — demo/benchmark path. Emits *degraded per-frame
    character reads* from known ground truth using a published-rate confusion
    model, then hands them to the real fusion and format stages.

The second one matters for honesty: it fakes the camera, not the algorithm.
Fusion, format repair, confidence gating, and everything downstream are the
identical production code paths, so the accuracy numbers we report measure our
logic rather than a hard-coded answer.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

from .fusion import FrameRead
from .plate_format import ALPHA_FOR_DIGIT, DIGIT_FOR_ALPHA


class Recognizer(Protocol):
    """Turns one vehicle pass into a list of per-frame plate reads."""

    def read_pass(self, context: dict) -> list[FrameRead]:
        ...


# --------------------------------------------------------------------------
# Condition model
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ConditionProfile:
    """How hard a given capture condition is, per condition bucket.

    `char_error_rate` is the chance a single character is misread in a single
    frame. `frames` is how many usable frames the vehicle is visible for —
    this is the redundancy fusion exploits, and it shrinks at night and in
    rain, which is exactly why accuracy degrades under those conditions.
    """

    name: str
    char_error_rate: float
    frames: tuple[int, int]
    base_confidence: float
    dropout: float          # probability the plate is not detected at all


CONDITIONS: dict[str, ConditionProfile] = {
    "day_clear":   ConditionProfile("day_clear",   0.030, (8, 14), 0.94, 0.01),
    "day_rain":    ConditionProfile("day_rain",    0.090, (5, 10), 0.84, 0.05),
    "night_clear": ConditionProfile("night_clear", 0.075, (5, 11), 0.86, 0.04),
    "night_rain":  ConditionProfile("night_rain",  0.150, (3, 7),  0.74, 0.10),
    "glare":       ConditionProfile("glare",       0.120, (4, 9),  0.78, 0.08),
    "angled":      ConditionProfile("angled",      0.100, (5, 10), 0.81, 0.06),
}


def _confuse(char: str, rng: random.Random) -> str:
    """Corrupt a character the way an OCR head actually errs — into a glyph
    that looks like it, never into a random one."""
    if char.isdigit():
        opts = DIGIT_FOR_ALPHA.get(char, [])
    else:
        opts = ALPHA_FOR_DIGIT.get(char, [])
    return rng.choice(opts) if opts else char


class SimulatedRecognizer:
    """Ground-truth-driven per-frame read generator for demo and benchmarking."""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def read_pass(self, context: dict) -> list[FrameRead]:
        truth: str = context["plate_text"]
        profile = CONDITIONS.get(context.get("condition", "day_clear"), CONDITIONS["day_clear"])
        rng = self.rng

        if rng.random() < profile.dropout:
            return []                       # camera missed this vehicle entirely

        n_frames = rng.randint(*profile.frames)
        reads: list[FrameRead] = []
        for i in range(n_frames):
            chars, confs = [], []
            for ch in truth:
                if rng.random() < profile.char_error_rate:
                    wrong = _confuse(ch, rng)
                    chars.append(wrong)
                    # A wrong read still carries confidence — that is exactly
                    # why single-frame OCR fails and voting is needed.
                    confs.append(round(rng.uniform(0.30, 0.62), 3))
                else:
                    chars.append(ch)
                    confs.append(round(min(0.995, rng.gauss(profile.base_confidence, 0.05)), 3))
            # Occasionally the crop clips a character at the frame edge.
            text = "".join(chars)
            if rng.random() < 0.06 and len(text) > 7:
                text, confs = text[:-1], confs[:-1]
            reads.append(FrameRead(
                text=text,
                char_confidences=confs,
                frame_index=i,
                quality=round(max(0.25, rng.gauss(1.0, 0.22)), 3),
            ))
        return reads


class YoloCrnnRecognizer:
    """Production backend: YOLO plate detection + CRNN/PARSeq character head.

    Kept import-lazy so the service starts, and every other component stays
    demoable, on a machine with no model weights installed.
    """

    def __init__(self, detector_weights: str, ocr_weights: str, device: str = "cpu"):
        self.detector_weights = detector_weights
        self.ocr_weights = ocr_weights
        self.device = device
        self._detector = None
        self._ocr = None

    def _load(self):
        if self._detector is None:
            from ultralytics import YOLO      # noqa: PLC0415 - deliberate lazy load

            self._detector = YOLO(self.detector_weights)
        if self._ocr is None:
            self._ocr = _load_ocr_head(self.ocr_weights, self.device)

    def read_pass(self, context: dict) -> list[FrameRead]:
        """`context['frames']` is a list of BGR ndarrays for one vehicle pass."""
        from .rectify import enhance_low_light, rectify_plate, sharpness

        self._load()
        frames = context.get("frames") or []
        low_light = context.get("condition", "").startswith("night")
        reads: list[FrameRead] = []

        for i, frame in enumerate(frames):
            img = enhance_low_light(frame) if low_light else frame
            det = self._detector(img, verbose=False)[0]
            if not len(det.boxes):
                continue
            box = max(det.boxes, key=lambda b: float(b.conf))
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
            quad = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
            crop = rectify_plate(img, quad)
            text, char_confs = self._ocr.read(crop)
            if not text:
                continue
            reads.append(FrameRead(
                text=text,
                char_confidences=char_confs,
                frame_index=i,
                # Sharper crops get a proportionally louder vote in fusion.
                quality=min(2.0, sharpness(crop) / 120.0),
            ))
        return reads


def _load_ocr_head(weights: str, device: str):  # pragma: no cover - needs weights
    """Load the character-sequence head. Isolated so the model choice
    (CRNN / PARSeq / TrOCR) can change without touching the pipeline."""
    raise NotImplementedError(
        "Attach a trained OCR head here (CRNN/PARSeq). "
        "The pipeline, fusion and format stages are model-agnostic."
    )
