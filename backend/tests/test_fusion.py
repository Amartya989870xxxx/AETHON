"""Component 1 — multi-frame fusion.

These tests pin the property the accuracy target depends on: agreement across
independent frames must raise confidence above any single frame's, and genuine
disagreement must lower it.
"""
from __future__ import annotations

from app.anpr.fusion import FrameRead, fuse


def frames(texts, conf=0.85, quality=1.0):
    return [FrameRead(t, [conf] * len(t), i, quality) for i, t in enumerate(texts)]


def test_returns_none_without_reads():
    assert fuse([]) is None


def test_single_frame_confidence_is_not_inflated():
    f = fuse(frames(["DL4CAF3125"], conf=0.85))
    assert f.text == "DL4CAF3125"
    assert 0.84 <= f.confidence <= 0.86


def test_agreement_across_frames_beats_any_single_frame():
    """Six independent frames agreeing at 0.85 is stronger evidence than one
    frame at 0.85 — this redundancy is where the >90% target is won."""
    one = fuse(frames(["DL4CAF3125"], conf=0.85))
    six = fuse(frames(["DL4CAF3125"] * 6, conf=0.85))
    assert six.confidence > one.confidence
    assert six.agreement == 1.0


def test_majority_overrules_a_confident_but_wrong_frame():
    reads = [FrameRead("DL4CAF3125", [0.80] * 10, i) for i in range(5)]
    reads.append(FrameRead("DL4CAB3125", [0.95] * 10, 5))   # confidently wrong
    f = fuse(reads)
    assert f.text == "DL4CAF3125"
    assert 5 in f.contested_positions


def test_blur_weighted_frames_count_for_less():
    """A motion-blurred frame is a fraction of a vote, not a full one."""
    sharp = [FrameRead("DL4CAF3125", [0.75] * 10, i, quality=1.5) for i in range(3)]
    blurry = [FrameRead("DL4CAB3125", [0.75] * 10, i, quality=0.2) for i in range(3)]
    assert fuse(sharp + blurry).text == "DL4CAF3125"


def test_genuine_split_lowers_confidence():
    split = fuse(frames(["DL4CAF3125"] * 2 + ["DL4CAB3125"] * 2, conf=0.8))
    clean = fuse(frames(["DL4CAF3125"] * 4, conf=0.8))
    assert split.confidence < clean.confidence


def test_never_reports_certainty():
    f = fuse(frames(["DL4CAF3125"] * 20, conf=0.99))
    assert f.confidence < 1.0


def test_clipped_frames_are_excluded_from_the_vote():
    reads = frames(["DL4CAF3125"] * 4) + frames(["DL4CAF312"])   # one clipped
    f = fuse(reads)
    assert f.text == "DL4CAF3125"
    assert f.frames_used == 4 and f.frames_total == 5
