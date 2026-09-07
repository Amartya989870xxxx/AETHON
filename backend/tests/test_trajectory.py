"""Component 2 — trajectory reconstruction.

The behaviours pinned here are the ones a naive "sort by timestamp" query gets
wrong: bridging a missed detection, refusing to merge a cloned plate, and
recovering a vehicle whose plate was misread at one camera.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.engines.trajectory import TrajectoryEngine, levenshtein
from app.models import Observation

from .conftest import T0


def add_obs(db, camera, seconds, plate="DL4CAF3125", confidence=0.95,
            direction="east", vehicle_type="sedan"):
    o = Observation(
        camera_id=camera, ts=T0 + timedelta(seconds=seconds), plate_text=plate,
        plate_norm=plate, plate_confidence=confidence, vehicle_type=vehicle_type,
        direction=direction, lane=1, speed_estimate_kmph=35.0,
        frames_fused=6, format_valid=True, repairs=[], condition="day_clear",
    )
    db.add(o)
    db.flush()
    return o


@pytest.fixture()
def engine(db, city):
    return TrajectoryEngine(db, city)


def window():
    return T0 - timedelta(hours=1), T0 + timedelta(hours=6)


def test_levenshtein_early_exit():
    assert levenshtein("DL4CAF3125", "DL4CAF3I25") == 1
    assert levenshtein("DL4CAF3125", "MH12DE1433", cap=2) == 3      # capped


def test_no_sightings_reports_nothing_found(engine):
    r = engine.reconstruct("DL4CAF3125", *window())
    assert not r.found and r.candidates_considered == 0


def test_single_sighting_is_not_a_route(db, engine, city):
    add_obs(db, "C01", 0)
    r = engine.reconstruct("DL4CAF3125", *window())
    assert r.found and len(r.path) == 1 and r.hops == []


def test_reconstructs_an_ordinary_route_in_order(db, engine, city):
    add_obs(db, "C15", 0, direction="southeast")
    add_obs(db, "C01", 180, direction="east")
    add_obs(db, "C02", 400, direction="east")
    r = engine.reconstruct("DL4CAF3125", *window())
    assert [n["camera_id"] for n in r.path] == ["C15", "C01", "C02"]
    assert len(r.hops) == 2
    assert r.total_distance_km > 0


def test_bridges_a_missed_detection(db, engine, city):
    """C02 never reports the vehicle. The route must stay continuous rather
    than splitting into two unrelated fragments."""
    add_obs(db, "C15", 0, direction="southeast")
    add_obs(db, "C01", 180, direction="east")
    add_obs(db, "C03", 900, direction="east")        # C02 skipped
    r = engine.reconstruct("DL4CAF3125", *window())
    assert [n["camera_id"] for n in r.path] == ["C15", "C01", "C03"]
    bridged = [h for h in r.hops if h.intermediate_cameras]
    assert bridged and bridged[0].intermediate_cameras == ["C02"]
    assert "did not report" in r.note


def test_refuses_to_merge_a_cloned_plate(db, engine, city):
    """Two vehicles sharing a plate, on opposite sides of the city. Stitching
    them into one journey would invent a trip nobody made."""
    add_obs(db, "C09", 0, direction="north")
    add_obs(db, "C12", 130, direction="north")
    add_obs(db, "C05", 200, direction="west")        # impossible from C12
    r = engine.reconstruct("DL4CAF3125", *window())
    assert "C05" not in [n["camera_id"] for n in r.path]
    assert any(x.reason == "physically_impossible" for x in r.rejected)


def test_rejects_a_gap_too_long_to_be_one_journey(db, engine, city):
    """C01->C02 is 1.7km. Even crawling at 4km/h that is ~26 minutes; 83
    minutes apart means these are two separate trips, not one hop."""
    add_obs(db, "C01", 0)
    add_obs(db, "C02", 5_000)
    r = engine.reconstruct("DL4CAF3125", *window())
    assert any(x.reason == "gap_too_long" for x in r.rejected)
    assert len(r.path) == 1


def test_collapses_repeat_reads_of_one_pass(db, engine, city):
    add_obs(db, "C01", 0)
    add_obs(db, "C01", 2)                             # same vehicle, same pass
    add_obs(db, "C02", 300)
    r = engine.reconstruct("DL4CAF3125", *window())
    assert len(r.path) == 2


def test_fuzzy_match_recovers_a_misread_plate(db, engine, city):
    """The vehicle was read correctly at C01 and misread at C02. With only one
    exact sighting the engine widens to edit-distance 1 and recovers it."""
    add_obs(db, "C01", 0, plate="DL4CAF3125")
    add_obs(db, "C02", 300, plate="DL4CAF3I25")       # one character wrong
    r = engine.reconstruct("DL4CAF3125", *window())
    assert r.fuzzy_used
    assert [n["camera_id"] for n in r.path] == ["C01", "C02"]
    assert r.path[1]["edit_distance"] == 1


def test_fuzzy_sightings_are_weighted_below_exact_ones(db, engine, city):
    add_obs(db, "C01", 0, plate="DL4CAF3125")
    add_obs(db, "C02", 300, plate="DL4CAF3I25")
    r = engine.reconstruct("DL4CAF3125", *window())
    exact, fuzzy = r.path[0], r.path[1]
    assert exact["match"] == "exact" and fuzzy["match"].startswith("fuzzy")


def test_persist_writes_a_row_only_for_real_routes(db, engine, city):
    add_obs(db, "C01", 0)
    assert engine.persist(engine.reconstruct("DL4CAF3125", *window())) is None
    add_obs(db, "C02", 300)
    assert engine.persist(engine.reconstruct("DL4CAF3125", *window())) is not None
