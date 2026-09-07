"""Component 1 — format validation and confusion repair."""
from __future__ import annotations

import pytest

from app.anpr.plate_format import STATE_CODES, normalize, validate


@pytest.mark.parametrize("raw,expected", [
    ("DL4CAF3125", "DL4CAF3125"),
    ("MH12DE1433", "MH12DE1433"),
    ("KA05MG2345", "KA05MG2345"),
    ("22BH1234AA", "22BH1234AA"),      # Bharat series
])
def test_clean_plates_pass_untouched(raw, expected):
    r = validate(raw)
    assert r.valid and r.plate == expected and r.repair_count == 0


@pytest.mark.parametrize("misread,truth,repaired_from", [
    ("DL4CAF3I25", "DL4CAF3125", "I"),   # I read where a digit belongs
    ("MH12DE143S", "MH12DE1435", "S"),   # S/5
    ("DL4CAF3L25", "DL4CAF3125", "L"),
])
def test_repairs_confusions_the_format_makes_unambiguous(misread, truth, repaired_from):
    r = validate(misread)
    assert r.valid and r.plate == truth
    assert r.repairs[0]["from"] == repaired_from


def test_state_code_disambiguates_an_ambiguous_glyph():
    """`0` could be O, D or Q. Only DL is a real RTO code, so it must pick D."""
    r = validate("0L4CAF3125")
    assert r.valid and r.plate == "DL4CAF3125"
    assert r.repairs == [{"index": 0, "from": "0", "to": "D", "expected": "A"}]


@pytest.mark.parametrize("junk", ["HELLOWORLD", "ZZ99XX0000", "DL4CAF31", "", "12"])
def test_abstains_rather_than_inventing_a_plate(junk):
    """Unrecognised structure must fail closed. Guessing here would put a
    fabricated registration in front of a police operator."""
    assert not validate(junk).valid


def test_repair_budget_is_enforced():
    assert not validate("0L4CAF3I2S", max_repairs=2).valid
    assert validate("0L4CAF312S", max_repairs=2).valid


def test_normalize_strips_separators_and_case():
    assert normalize("dl-4c af 3125") == "DL4CAF3125"


def test_state_code_table_is_sane():
    assert {"DL", "MH", "KA", "TN", "UP"} <= STATE_CODES
