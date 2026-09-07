"""Component 4 — blacklist matching and route anomalies.

Each rule is tested for the alert it must raise *and* for the false positive it
must not. The second half matters more: an alerting system operators learn to
ignore is worse than none.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.engines.alerts import AlertEngine
from app.ingest.worker import process_event
from app.models import Alert, AuditLog, BlacklistEntry, Observation, ZonePermit

from .conftest import T0


@pytest.fixture()
def engine(db, city):
    return AlertEngine(db, city)


def observe(db, engine, camera, seconds, plate="DL4CAF3125", confidence=0.95,
            vtype="sedan", evaluate=True, profile=True):
    obs = Observation(
        camera_id=camera, ts=T0 + timedelta(seconds=seconds), plate_text=plate,
        plate_norm=plate, plate_confidence=confidence, vehicle_type=vtype,
        direction="east", lane=1, speed_estimate_kmph=35.0, frames_fused=6,
        format_valid=True, repairs=[], condition="day_clear",
        frame_ref=f"{camera}/{seconds}.jpg",
    )
    db.add(obs)
    db.flush()
    raised = engine.evaluate(obs) if evaluate else []
    if profile:
        engine.update_profile(obs)
    return obs, raised


def blacklist(db, engine, plate, severity="critical"):
    db.add(BlacklistEntry(plate_norm=plate, reason="test warrant",
                          severity=severity, added_by="tester"))
    db.flush()
    engine.invalidate_blacklist()


# --- blacklist ------------------------------------------------------------
def test_exact_blacklist_match_raises_a_critical_alert(db, engine):
    blacklist(db, engine, "DL4CAF3125")
    _obs, alerts = observe(db, engine, "C01", 0)
    assert [a.alert_type for a in alerts] == ["blacklist_hit"]
    assert alerts[0].severity == "critical"


def test_every_alert_carries_its_evidence(db, engine):
    """A match is a lead, not a verdict — an operator must be able to see what
    the system saw before acting on it."""
    blacklist(db, engine, "DL4CAF3125")
    _obs, alerts = observe(db, engine, "C01", 0)
    ev = alerts[0].evidence
    assert ev["camera_id"] == "C01" and ev["frame_ref"]
    assert ev["plate_confidence"] == 0.95
    assert ev["recognition"]["frames_fused"] == 6
    assert "observed_at" in ev


def test_alerts_are_written_to_the_audit_log(db, engine):
    blacklist(db, engine, "DL4CAF3125")
    observe(db, engine, "C01", 0)
    assert db.query(AuditLog).filter_by(action="alert_raised").count() == 1


def test_single_character_misread_still_surfaces_as_a_possible_match(db, engine):
    """Requiring an exact string means one misread character defeats the watch
    list entirely. The near-miss is surfaced at reduced severity instead."""
    blacklist(db, engine, "DL4CAF3125")
    _obs, alerts = observe(db, engine, "C01", 0, plate="DL4CAF3I25", confidence=0.95)
    assert [a.alert_type for a in alerts] == ["blacklist_possible"]
    assert alerts[0].severity == "medium"
    assert alerts[0].evidence["listed_plate"] == "DL4CAF3125"


def test_weak_reads_never_trigger_a_fuzzy_watch_list_hit(db, engine):
    """Fuzzy matching on low-confidence reads is how an alert feed fills with
    noise. The read is still stored — it just cannot accuse anyone."""
    blacklist(db, engine, "DL4CAF3125")
    _obs, alerts = observe(db, engine, "C01", 0, plate="DL4CAF3I25", confidence=0.55)
    assert alerts == []
    assert db.query(Observation).count() == 1


def test_alerts_are_deduplicated_within_the_cooldown(db, engine):
    blacklist(db, engine, "DL4CAF3125")
    observe(db, engine, "C01", 0)
    observe(db, engine, "C02", 120)
    assert db.query(Alert).filter_by(alert_type="blacklist_hit").count() == 1


def test_an_unlisted_vehicle_raises_nothing(db, engine):
    _obs, alerts = observe(db, engine, "C01", 0)
    assert alerts == []


# --- impossible travel / cloned plates ------------------------------------
def test_same_plate_in_two_places_at_once_is_flagged(db, engine):
    observe(db, engine, "C09", 0)
    _obs, alerts = observe(db, engine, "C05", 90)      # opposite side of the city
    assert "impossible_travel" in [a.alert_type for a in alerts]
    ev = next(a for a in alerts if a.alert_type == "impossible_travel").evidence
    assert ev["implied_speed_kmph"] > 130


def test_a_normal_journey_is_not_flagged_as_impossible(db, engine):
    observe(db, engine, "C01", 0)
    _obs, alerts = observe(db, engine, "C02", 240)
    assert alerts == []


def test_clone_detection_requires_two_confident_reads(db, engine):
    """Two uncertain reads that happen to produce the same string are not
    evidence of a clone — they are evidence of bad OCR."""
    observe(db, engine, "C09", 0, confidence=0.50)
    _obs, alerts = observe(db, engine, "C05", 90, confidence=0.50)
    assert alerts == []


# --- restricted zone ------------------------------------------------------
def test_unpermitted_entry_to_a_restricted_corridor_alerts(db, engine):
    _obs, alerts = observe(db, engine, "C10", 0, vtype="truck")
    assert [a.alert_type for a in alerts] == ["restricted_zone"]


def test_a_permitted_fleet_vehicle_does_not_alert(db, engine):
    db.add(ZonePermit(plate_norm="DL4CAF3125", zone="industrial"))
    db.flush()
    engine.invalidate_blacklist()
    _obs, alerts = observe(db, engine, "C10", 0, vtype="truck")
    assert alerts == []


def test_an_established_corridor_user_stops_alerting(db, engine):
    """A vehicle with a record of legitimately using the corridor is not an
    anomaly, permit paperwork notwithstanding."""
    for i in range(4):
        observe(db, engine, "C10", i * 3600, evaluate=False)   # build history
    _obs, alerts = observe(db, engine, "C10", 5 * 3600)
    assert alerts == []


# --- loitering ------------------------------------------------------------
def test_repeated_circling_of_one_zone_is_flagged(db, engine):
    raised = []
    for i, cam in enumerate(["C07", "C14", "C13", "C07", "C14"]):
        _obs, alerts = observe(db, engine, cam, i * 400)
        raised += [a.alert_type for a in alerts]
    # Fires once the threshold is crossed, then stays quiet inside the cooldown
    # rather than re-alerting on every subsequent lap.
    assert raised.count("loitering") == 1


def test_a_vehicle_parked_at_one_camera_is_not_loitering(db, engine):
    """Circling means moving between cameras. Repeated reads at a single
    camera is a parked vehicle, which is a different thing entirely."""
    raised = []
    for i in range(6):
        _obs, alerts = observe(db, engine, "C07", i * 400)
        raised += [a.alert_type for a in alerts]
    assert "loitering" not in raised


def test_a_vehicle_passing_through_once_is_not_loitering(db, engine):
    for i, cam in enumerate(["C07", "C14", "C03"]):
        _obs, alerts = observe(db, engine, cam, i * 300)
    assert alerts == []


# --- odd hours ------------------------------------------------------------
def _night(seconds: int) -> int:
    """Offset landing at 03:00, well inside the odd-hours window."""
    return int((17 * 3600) + seconds)                 # T0 is 10:00 UTC


def test_breaking_an_established_routine_is_flagged(db, engine):
    for day in range(3):
        for i, cam in enumerate(["C09", "C08", "C07"]):
            observe(db, engine, cam, day * 86_400 + i * 300)   # daytime routine
    _obs, alerts = observe(db, engine, "C08", _night(0))
    assert "odd_hours" in [a.alert_type for a in alerts]


def test_a_vehicle_that_always_runs_at_night_is_not_flagged(db, engine):
    """A night-shift delivery van must not trip a curfew rule. The baseline is
    the plate's own history, not a global schedule."""
    for day in range(3):
        for i, cam in enumerate(["C09", "C08", "C07"]):
            observe(db, engine, cam, _night(day * 86_400 + i * 300))
    _obs, alerts = observe(db, engine, "C13", _night(4 * 86_400))
    assert "odd_hours" not in [a.alert_type for a in alerts]


def test_a_vehicle_with_no_history_is_not_flagged(db, engine):
    """A first sighting cannot deviate from a pattern that does not exist."""
    _obs, alerts = observe(db, engine, "C08", _night(0))
    assert "odd_hours" not in [a.alert_type for a in alerts]


# --- write path ordering --------------------------------------------------
def test_an_observation_cannot_mask_its_own_anomaly(db, city):
    """Regression guard. If the plate profile is updated before the rules run,
    a 03:00 sighting makes 03:00 look normal and the rule never fires."""
    from app.anpr.pipeline import PlateEvent

    engine = AlertEngine(db, city)
    for day in range(3):
        for i, cam in enumerate(["C09", "C08", "C07"]):
            observe(db, engine, cam, day * 86_400 + i * 300)

    event = PlateEvent(
        camera_id="C08", timestamp=T0 + timedelta(seconds=_night(0)),
        plate_text="DL4CAF3125", plate_norm="DL4CAF3125", plate_confidence=0.95,
        vehicle_type="sedan", direction="east", lane=1,
    )
    _obs, alerts = process_event(db, city, event, engine)
    assert "odd_hours" in [a.alert_type for a in alerts]
