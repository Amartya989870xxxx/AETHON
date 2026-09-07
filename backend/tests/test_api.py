"""End-to-end tests over the HTTP surface, including the privacy guarantees."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.db import get_db
from app.main import app
from app.models import Camera, CameraLink
from app.sim.city import build_camera_rows, build_link_rows

from .conftest import T0

WINDOW = {"start": (T0 - timedelta(hours=1)).isoformat(),
          "end": (T0 + timedelta(hours=6)).isoformat()}


@pytest.fixture()
def client(db):
    db.add_all([Camera(**r) for r in build_camera_rows()])
    db.flush()
    db.add_all([CameraLink(**r) for r in build_link_rows()])
    db.commit()
    deps.reset_graph()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    deps.reset_graph()


def post_obs(client, camera, seconds, plate="DL4CAF3125", confidence=0.95):
    return client.post("/api/observations", json={
        "camera_id": camera, "timestamp": (T0 + timedelta(seconds=seconds)).isoformat(),
        "plate_text": plate, "plate_confidence": confidence,
        "vehicle_type": "sedan", "direction": "east", "lane": 1,
        "speed_estimate_kmph": 38.0, "frames_fused": 6,
        "frame_ref": f"{camera}/{seconds}.jpg",
    })


def test_health_and_root(client):
    assert client.get("/health").json()["status"] == "ok"
    assert "1_anpr_ocr" in client.get("/").json()["components"]


def test_cameras_are_served_as_geojson(client):
    body = client.get("/api/cameras").json()
    assert body["type"] == "FeatureCollection" and len(body["features"]) == 16


def test_ingest_rejects_an_unknown_camera(client):
    assert post_obs(client, "C99", 0).status_code == 404


def test_ingest_repairs_the_plate_on_the_way_in(client):
    body = post_obs(client, "C01", 0, plate="0L4CAF3125").json()
    assert body["plate_norm"] == "DL4CAF3125"
    assert body["repairs"][0] == {"index": 0, "from": "0", "to": "D", "expected": "A"}


def test_full_flow_ingest_then_trajectory(client):
    for i, cam in enumerate(["C15", "C01", "C02", "C03"]):
        assert post_obs(client, cam, i * 300).status_code == 201
    traj = client.get("/api/trajectory/DL4CAF3125", params=WINDOW).json()
    assert traj["found"]
    assert [n["camera_id"] for n in traj["path"]] == ["C15", "C01", "C02", "C03"]


def test_watch_list_hit_is_raised_on_the_next_observation(client):
    assert client.post("/api/blacklist", json={
        "plate_text": "DL4CAF3125", "reason": "stolen vehicle",
        "severity": "critical", "added_by": "si_kumar"}).status_code == 201
    body = post_obs(client, "C01", 0).json()
    assert body["alerts_raised"][0]["type"] == "blacklist_hit"
    assert client.get("/api/alerts").json()[0]["severity"] == "critical"


def test_acknowledging_an_alert_records_the_disposition(client):
    client.post("/api/blacklist", json={"plate_text": "DL4CAF3125",
                                        "reason": "test", "added_by": "op"})
    alert_id = post_obs(client, "C01", 0).json()["alerts_raised"][0]["id"]
    res = client.post(f"/api/alerts/{alert_id}/acknowledge",
                      json={"actor": "si_kumar", "disposition": "false_positive",
                            "note": "different vehicle"}).json()
    assert res["status"] == "dismissed" and res["acknowledged_by"] == "si_kumar"
    assert client.get("/api/alerts/stats/summary").json()["false_positive_rate"] == 1.0


def test_trajectory_queries_are_always_audited(client):
    """Identity-sensitive lookups must leave a trace naming who ran them."""
    post_obs(client, "C01", 0)
    client.get("/api/trajectory/DL4CAF3125", params={**WINDOW, "actor": "si_kumar"})
    entries = client.get("/api/audit", params={**WINDOW, "action": "trajectory_query"}).json()
    assert entries["count"] == 1
    assert entries["entries"][0]["actor"] == "si_kumar"
    assert entries["entries"][0]["subject"] == "DL4CAF3125"


def test_aggregate_analytics_expose_no_plate_identity(client):
    """Density, OD and heatmap outputs are the broadly-shareable half of the
    system. Nothing in them may identify a vehicle."""
    for i, cam in enumerate(["C15", "C01", "C08"]):
        post_obs(client, cam, i * 300)
    client.post("/api/analytics/recompute", params=WINDOW)
    for path in ("/api/analytics/heatmap", "/api/analytics/od",
                 "/api/analytics/bottlenecks"):
        body = client.get(path, params=WINDOW).text
        assert "DL4CAF3125" not in body
        assert "plate" not in body.lower()


def test_partial_plate_search_finds_a_vehicle_from_a_fragment(client):
    post_obs(client, "C01", 0)
    body = client.get("/api/plates/search", params={**WINDOW, "partial": "CAF"}).json()
    assert body["matches"][0]["plate"] == "DL4CAF3125"


def test_benchmark_reports_accuracy_per_condition(client):
    body = client.get("/api/benchmark/anpr", params={"samples": 60}).json()
    assert set(body["by_condition"]) >= {"day_clear", "night_rain", "glare"}
    # The weakest bucket must be stated, not averaged away.
    assert body["worst_condition"]["condition"] in body["by_condition"]
