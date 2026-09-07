"""Multi-frame fusion — where most of the >90% accuracy target is actually won.

A vehicle is visible for 5-15 frames on approach to a camera. Motion blur,
glare and rain corrupt *different* characters in different frames. Reading one
frame and trusting it throws that redundancy away.

This module fuses N per-frame reads into one plate string by voting per
character position, weighted by each frame's per-character confidence. It is
pure Python/numpy and is independently unit-tested, so its contribution to
accuracy is measurable on its own.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

# Plate alphabet: A-Z plus 0-9. When a frame reports character `x` with
# confidence p, the residual (1-p) is spread across the other 35 candidates.
ALPHABET_SIZE = 36

# Ceiling on any reported per-character confidence.
MAX_CHAR_CONFIDENCE = 0.99


@dataclass
class FrameRead:
    """One OCR result from one frame of a vehicle's approach."""

    text: str
    char_confidences: list[float]
    frame_index: int = 0
    # Sharper, larger crops deserve more say in the vote.
    quality: float = 1.0

    @property
    def mean_confidence(self) -> float:
        return sum(self.char_confidences) / len(self.char_confidences) if self.char_confidences else 0.0


@dataclass
class FusedRead:
    text: str
    char_confidences: list[float]
    confidence: float
    frames_used: int
    frames_total: int
    # Positions where frames disagreed — useful evidence on a borderline alert.
    contested_positions: list[int] = field(default_factory=list)
    agreement: float = 1.0


def _dominant_length(reads: list[FrameRead]) -> int:
    """Frames that saw a different number of characters usually clipped the
    plate. Pick the length with the most confidence mass behind it."""
    weight: Counter[int] = Counter()
    for r in reads:
        weight[len(r.text)] += r.mean_confidence * r.quality
    return weight.most_common(1)[0][0]


def fuse(reads: list[FrameRead]) -> FusedRead | None:
    """Fuse per-frame reads into a single best-estimate plate string."""
    reads = [r for r in reads if r.text and r.char_confidences]
    if not reads:
        return None

    target_len = _dominant_length(reads)
    usable = [r for r in reads if len(r.text) == target_len
              and len(r.char_confidences) == target_len]
    if not usable:
        # Every frame disagreed on length — fall back to the single strongest
        # read rather than fusing across misaligned character positions.
        best = max(reads, key=lambda r: r.mean_confidence * r.quality)
        return FusedRead(best.text, list(best.char_confidences),
                         best.mean_confidence, 1, len(reads), [], 1.0)

    chars: list[str] = []
    confs: list[float] = []
    contested: list[int] = []

    for pos in range(target_len):
        posterior = _pool_position(usable, pos)
        winner, p_win = max(posterior.items(), key=lambda kv: kv[1])
        chars.append(winner)
        # Capped: no recognition system should ever report certainty, however
        # many frames agreed. Downstream gates are calibrated against this.
        confs.append(round(min(p_win, MAX_CHAR_CONFIDENCE), 4))
        if len({r.text[pos] for r in usable}) > 1:
            contested.append(pos)

    # Overall confidence is weakest-link dominated: a plate is only as
    # trustworthy as its least certain character, softened by the mean so one
    # marginal character does not zero out an otherwise clean read.
    weakest = min(confs)
    mean = sum(confs) / len(confs)
    overall = round(0.6 * weakest + 0.4 * mean, 4)
    agreement = round(1.0 - (len(contested) / target_len), 4)

    return FusedRead(
        text="".join(chars),
        char_confidences=confs,
        confidence=overall,
        frames_used=len(usable),
        frames_total=len(reads),
        contested_positions=contested,
        agreement=agreement,
    )


def _pool_position(reads: list[FrameRead], pos: int) -> dict[str, float]:
    """Posterior over the true character at one position, pooling all frames.

    Each frame is treated as an independent noisy observation: a frame that
    reports `x` with confidence p asserts P(truth = x) = p, leaving (1-p)
    spread uniformly over the remaining alphabet. Log-likelihoods are summed
    across frames and normalised.

    This is why redundancy helps rather than merely averaging: six frames
    independently agreeing on `F` at 0.85 yields a posterior far above 0.85,
    while a genuine 4-2 split lands near the true balance of evidence instead
    of being decided by whichever frame happened to be most confident.

    Frame `quality` (crop sharpness) enters as an exponent, so a motion-blurred
    frame counts as a fraction of an observation instead of a full vote.
    """
    candidates = {r.text[pos] for r in reads}
    log_scores: dict[str, float] = {}
    for cand in candidates:
        total = 0.0
        for r in reads:
            p = min(0.999, max(0.001, r.char_confidences[pos]))
            # Likelihood of observing this frame's character if truth == cand.
            like = p if r.text[pos] == cand else (1.0 - p) / (ALPHABET_SIZE - 1)
            total += r.quality * math.log(like)
        log_scores[cand] = total

    # Normalise in log space to avoid underflow on long frame runs.
    top = max(log_scores.values())
    exp_scores = {c: math.exp(v - top) for c, v in log_scores.items()}
    # Mass reserved for characters no frame proposed at all.
    unseen = math.exp(
        sum(r.quality * math.log((1.0 - min(0.999, max(0.001, r.char_confidences[pos])))
                                 / (ALPHABET_SIZE - 1)) for r in reads) - top
    ) * (ALPHABET_SIZE - len(candidates))
    denom = sum(exp_scores.values()) + unseen
    return {c: v / denom for c, v in exp_scores.items()}
