"""The road graph — the structure every correlation decision rests on."""
from __future__ import annotations

from app.engines.camera_graph import haversine_km, heading_delta


def test_topology_is_connected(city):
    s = city.summary()
    assert s["cameras"] == 16
    assert s["strongly_connected"], "every camera must be reachable from every other"
    assert set(s["restricted_cameras"]) == {"C10", "C11"}


def test_road_distance_exceeds_straight_line(city):
    """Road distance must never be shorter than the crow flies — a matcher
    using straight-line distance would accept physically impossible hops."""
    a, b = city.nodes["C15"], city.nodes["C04"]
    straight = haversine_km(a.lat, a.lon, b.lat, b.lon)
    assert city.road_distance_km("C15", "C04") > straight


def test_travel_window_brackets_plausible_speeds(city):
    fastest, slowest = city.travel_window_seconds("C01", "C02")
    dist = city.road_distance_km("C01", "C02")
    assert (dist / fastest) * 3600 <= 110.0 + 1e-6     # max urban speed
    assert (dist / slowest) * 3600 >= 4.0 - 1e-6       # min crawl speed
    assert fastest < slowest


def test_hop_count_reveals_skipped_cameras(city):
    assert city.hop_count("C01", "C02") == 1
    assert city.hop_count("C15", "C03") == 3           # via C01, C02


def test_through_traffic_avoids_the_restricted_corridor(city):
    """A restricted corridor must not be the only south-west route, or every
    transiting vehicle would trip the restricted-zone rule."""
    path = city.path_between("C16", "C09")
    assert "C10" not in path and "C11" not in path


def test_direction_score_rewards_travelling_toward_the_next_camera(city):
    heading = city.g["C01"]["C02"]["heading"]
    toward = city.direction_score(heading, "C01", "C02")
    opposite = {"north": "south", "south": "north", "east": "west", "west": "east"}
    away = city.direction_score(opposite.get(heading, "south"), "C01", "C02")
    assert toward > away
    assert city.direction_score("unknown", "C01", "C02") == 0.5


def test_heading_delta_wraps_around_the_compass():
    assert heading_delta("north", "north") == 0
    assert heading_delta("north", "south") == 180
    assert heading_delta("north", "northwest") == 45     # not 315
