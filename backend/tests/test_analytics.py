"""Component 3 — aggregation, congestion scoring, and OD."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.engines.analytics import AnalyticsEngine, floor_bucket
from app.models import Observation, TrafficAggregate

from .conftest import T0


@pytest.fixture()
def analytics(db, city):
    return AnalyticsEngine(db, city)


def add(db, camera, seconds, plate="DL4CAF3125", speed=40.0, vtype="sedan",
        direction="east", confidence=0.95):
    db.add(Observation(
        camera_id=camera, ts=T0 + timedelta(seconds=seconds), plate_text=plate,
        plate_norm=plate, plate_confidence=confidence, vehicle_type=vtype,
        direction=direction, lane=1, speed_estimate_kmph=speed,
        frames_fused=5, format_valid=True, repairs=[], condition="day_clear",
    ))
    db.flush()


def test_floor_bucket_snaps_down():
    b = floor_bucket(T0 + timedelta(seconds=299), 300)
    assert b == T0
    assert floor_bucket(T0 + timedelta(seconds=300), 300) == T0 + timedelta(seconds=300)


def test_congestion_needs_both_volume_and_slowness(analytics):
    """A busy free-flowing expressway is not congested, and neither is an empty
    road with one slow truck. Only the combination is."""
    busy_fast = analytics.congestion_score(count=60, avg_speed=55.0, lanes=4)
    busy_slow = analytics.congestion_score(count=60, avg_speed=8.0, lanes=4)
    empty_slow = analytics.congestion_score(count=2, avg_speed=8.0, lanes=4)
    assert busy_slow > busy_fast
    assert busy_slow > empty_slow


def test_aggregation_buckets_by_camera_and_time(db, analytics):
    for i in range(10):
        add(db, "C01", i * 20)                        # all inside one 5-min bucket
    add(db, "C01", 600)                               # a later bucket
    add(db, "C02", 30)
    n = analytics.aggregate(T0 - timedelta(hours=1), T0 + timedelta(hours=1))
    assert n == 3
    rows = db.query(TrafficAggregate).filter_by(camera_id="C01").all()
    assert sorted(r.vehicle_count for r in rows) == [1, 10]


def test_aggregation_records_direction_and_class_mix(db, analytics):
    add(db, "C01", 0, vtype="truck", direction="east")
    add(db, "C01", 10, vtype="two_wheeler", direction="east")
    add(db, "C01", 20, vtype="two_wheeler", direction="west")
    analytics.aggregate(T0 - timedelta(hours=1), T0 + timedelta(hours=1))
    row = db.query(TrafficAggregate).filter_by(camera_id="C01").one()
    assert row.class_distribution == {"truck": 1, "two_wheeler": 2}
    assert row.direction_distribution == {"east": 2, "west": 1}


def test_analytics_does_not_gate_on_plate_quality(db, analytics):
    """Counting a vehicle is a lower bar than reading its plate. Density must
    stay accurate at cameras where OCR is struggling."""
    for i in range(6):
        add(db, "C01", i * 10, confidence=0.20)       # unusable for identity
    analytics.aggregate(T0 - timedelta(hours=1), T0 + timedelta(hours=1))
    assert db.query(TrafficAggregate).filter_by(camera_id="C01").one().vehicle_count == 6


def test_congestion_is_relative_to_the_segments_own_baseline(db, analytics):
    """The same volume must read as normal at a busy hour and abnormal at a
    quiet one, once history exists for that segment."""
    # Four weeks of quiet Mondays at this hour on C01's segment.
    for week in range(4):
        base = T0 - timedelta(days=7 * (week + 1))
        db.add(TrafficAggregate(
            bucket_start=base, bucket_seconds=300, camera_id="C01",
            road_segment="NH-44-North", zone="north", vehicle_count=2,
            avg_speed_kmph=55.0, density_per_lane=0.5, congestion_score=0.10,
            direction_distribution={}, class_distribution={},
        ))
    db.flush()
    for i in range(40):                               # today is very different
        add(db, "C01", i * 5, speed=6.0)
    analytics.aggregate(T0 - timedelta(minutes=1), T0 + timedelta(hours=1))
    row = db.query(TrafficAggregate).filter(
        TrafficAggregate.camera_id == "C01",
        TrafficAggregate.bucket_start == T0).one()
    assert row.z_score is not None and row.z_score > 1.5
    assert row.is_congested


def test_od_records_zone_to_zone_trips_without_plates(db, analytics):
    add(db, "C15", 0, plate="DL4CAF3125")             # north
    add(db, "C01", 200, plate="DL4CAF3125")           # north
    add(db, "C08", 600, plate="DL4CAF3125")           # central
    analytics.compute_od(T0 - timedelta(hours=1), T0 + timedelta(hours=1))
    matrix = analytics.od_matrix(T0 - timedelta(hours=1), T0 + timedelta(hours=1))
    assert matrix["matrix"]["north"]["central"] == 1
    # The OD tables carry no plate column at all — identity is dropped here.
    from app.models import ODFlow
    assert not hasattr(ODFlow, "plate_norm")


def test_od_ignores_trips_that_never_leave_a_zone(db, analytics):
    add(db, "C15", 0)
    add(db, "C01", 200)                               # both north
    assert analytics.compute_od(T0 - timedelta(hours=1), T0 + timedelta(hours=1)) == 0


def test_heatmap_emits_valid_geojson(db, analytics):
    add(db, "C01", 0)
    analytics.aggregate(T0 - timedelta(hours=1), T0 + timedelta(hours=1))
    hm = analytics.heatmap(T0 + timedelta(minutes=1), 30)
    assert hm["type"] == "FeatureCollection"
    f = hm["features"][0]
    assert f["geometry"]["type"] == "Point"
    lon, lat = f["geometry"]["coordinates"]
    assert 68 < lon < 98 and 6 < lat < 38          # inside India's bounding box
