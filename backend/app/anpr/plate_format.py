"""Format-aware validation and repair for Indian number plates.

This is the cheapest accuracy win in the whole pipeline. A general OCR model
confuses characters that *look* alike (0/O, 1/I, 8/B). But an Indian plate has
rigid structure: positions 0-1 are always a state code, the next 1-2 are
numeric, then an alphabetic series, then a 4-digit number. Knowing which
positions must be alphabetic and which must be numeric turns an ambiguous read
into a decidable one.

The repair is deliberately conservative:
  * only substitutions from a known visual-confusion table are allowed,
  * at most `max_repairs` characters may change,
  * the state code must exist,
  * each repair is recorded so the evidence trail shows what was changed.

If no format explains the read within budget, we mark it invalid rather than
inventing a plate. Abstaining beats guessing when the output can trigger a
police alert.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import product

# RTO state / UT codes. First two characters of every civilian plate.
STATE_CODES = {
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA", "GJ",
    "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP",
    "MZ", "NL", "OD", "OR", "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UK",
    "UP", "WB",
}

# Visual confusion table, read as "OCR emitted X, the truth may be one of Y".
# Only these substitutions are ever applied. Several glyphs are ambiguous in
# both directions (0 reads as O or D on a dirty plate), so each entry is a
# ranked list and the validator searches them.
DIGIT_FOR_ALPHA = {
    "0": ["O", "D", "Q"], "1": ["I", "L", "J"], "2": ["Z"], "3": ["E"],
    "4": ["A"], "5": ["S"], "6": ["G"], "7": ["T"], "8": ["B", "R"],
    "9": ["G", "P"],
}
ALPHA_FOR_DIGIT = {
    "O": ["0"], "D": ["0"], "Q": ["0"], "U": ["0"], "I": ["1"], "L": ["1"],
    "J": ["1"], "Z": ["2"], "E": ["3"], "A": ["4"], "S": ["5"], "G": ["6", "9"],
    "T": ["7"], "B": ["8"], "R": ["8"], "P": ["9"],
}

_NON_ALNUM = re.compile(r"[^A-Z0-9]")

# A format is a sequence of segments: (kind, min_len, max_len).
# kind 'A' = alphabetic, 'N' = numeric, 'L' = literal text.
FORMATS: list[tuple[str, tuple]] = [
    # DL4CAF3125 / MH12DE1433 — the modern standard, series 0-3 letters.
    ("standard", (("A", 2, 2), ("N", 1, 2), ("A", 0, 3), ("N", 4, 4))),
    # 22BH1234AA — Bharat series (new all-India registration).
    ("bharat", (("N", 2, 2), ("L", "BH", "BH"), ("N", 4, 4), ("A", 1, 2))),
    # Older three-part plates with a shorter numeric tail.
    ("legacy_short", (("A", 2, 2), ("N", 1, 2), ("A", 1, 2), ("N", 1, 3))),
    # 07C123456N — military/defence plates.
    ("defence", (("N", 2, 2), ("A", 1, 1), ("N", 6, 6), ("A", 1, 1))),
]


@dataclass
class FormatResult:
    """Outcome of validating one candidate read."""

    original: str
    plate: str                      # repaired text (== original when clean)
    valid: bool
    format_name: str | None = None
    repairs: list[dict] = field(default_factory=list)
    reason: str = ""

    @property
    def repair_count(self) -> int:
        return len(self.repairs)


def normalize(text: str) -> str:
    """Uppercase, strip separators. Every lookup key in the system uses this."""
    return _NON_ALNUM.sub("", (text or "").upper())


def _shapes(fmt: tuple, length: int) -> list[str]:
    """Every A/N/literal position-mask a format can take at a given length."""
    ranges = []
    for kind, lo, hi in fmt:
        if kind == "L":
            ranges.append([lo])            # literal segment, fixed
        else:
            ranges.append([kind * n for n in range(lo, hi + 1)])
    out = []
    for combo in product(*ranges):
        joined = "".join(combo)
        if len(joined) == length:
            out.append(joined)
    return out


def _fits(char: str, slot: str) -> bool:
    if slot == "A":
        return char.isalpha()
    if slot == "N":
        return char.isdigit()
    return char == slot                    # literal


def _repair_candidates(char: str, slot: str) -> list[str]:
    """Legal characters this glyph could really be, given the slot's class.
    Empty when the confusion is not one we recognise."""
    if slot == "A":
        return DIGIT_FOR_ALPHA.get(char, [])
    if slot == "N":
        return ALPHA_FOR_DIGIT.get(char, [])
    return [slot] if slot else []


def _score_against_shape(text: str, shape: str, budget: int) -> list[tuple[str, list[dict]]]:
    """Every way to bend `text` onto `shape` within the repair budget.

    Returns (repaired_text, repairs) pairs — plural, because an ambiguous glyph
    like `0` may legitimately be `O` or `D`. The caller disambiguates using the
    state-code table, which is what makes the choice decidable rather than a
    coin flip.
    """
    # Each state is (chars_so_far, repairs_so_far).
    states: list[tuple[list[str], list[dict]]] = [([], [])]
    for i, slot in enumerate(shape):
        char = text[i]
        nxt: list[tuple[list[str], list[dict]]] = []
        for chars, repairs in states:
            if _fits(char, slot):
                nxt.append((chars + [char], repairs))
                continue
            if len(repairs) >= budget:
                continue                   # out of budget on this branch
            for cand in _repair_candidates(char, slot):
                nxt.append((
                    chars + [cand],
                    repairs + [{"index": i, "from": char, "to": cand, "expected": slot}],
                ))
        if not nxt:
            return []
        states = nxt
    return [("".join(c), r) for c, r in states]


def validate(text: str, max_repairs: int = 2) -> FormatResult:
    """Validate a raw OCR string, repairing visual confusions where the format
    makes the correct character unambiguous."""
    raw = normalize(text)
    if not raw:
        return FormatResult(text or "", "", False, reason="empty")
    if not (6 <= len(raw) <= 11):
        return FormatResult(raw, raw, False, reason=f"implausible length {len(raw)}")

    best: FormatResult | None = None
    for name, fmt in FORMATS:
        for shape in _shapes(fmt, len(raw)):
            for repaired, repairs in _score_against_shape(raw, shape, max_repairs):
                # Civilian formats must carry a real state code. This is what
                # resolves an ambiguous first character: `0L...` can only be
                # `DL` because `OL` and `QL` are not RTO codes.
                if name in ("standard", "legacy_short") and repaired[:2] not in STATE_CODES:
                    continue
                cand = FormatResult(raw, repaired, True, name, repairs)
                if best is None or cand.repair_count < best.repair_count:
                    best = cand
                if best.repair_count == 0:
                    return best            # perfect match, stop searching
    if best:
        return best
    return FormatResult(raw, raw, False, reason="no format matched within repair budget")


def is_plausible_plate(text: str) -> bool:
    return validate(text).valid
