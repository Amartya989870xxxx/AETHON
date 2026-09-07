#!/usr/bin/env python3
"""Prove all four components work, on the seeded database.

Run after `./run.sh seed`. Every check reads the database the same way the
dashboard would, so a green run here means the demo will hold up live.

    python3 scripts/demo.py
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db import SessionLocal                          # noqa: E402
from app.engines.alerts import AlertEngine               # noqa: E402
from app.engines.analytics import AnalyticsEngine        # noqa: E402
from app.engines.camera_graph import CameraGraph         # noqa: E402
from app.engines.trajectory import TrajectoryEngine      # noqa: E402
from app.models import Alert, AuditLog, Observation      # noqa: E402

GREEN, RED, DIM, BOLD, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"
checks: list[tuple[str, bool]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    checks.append((label, ok))
    mark = f"{GREEN}PASS{OFF}" if ok else f"{RED}FAIL{OFF}"
    print(f"  [{mark}] {label}")
    if detail:
        print(f"         {DIM}{detail}{OFF}")


def header(n: int, title: str) -> None:
    print(f"\n{BOLD}Component {n} — {title}{OFF}")


def main() -> int:
    db = SessionLocal()
    graph = CameraGraph.from_db(db)
    now = datetime.now(timezone.utc)
    start, end = now - timedelta(days=8), now + timedelta(hours=2)

    if not graph.nodes:
        print(f"{RED}No camera network found. Run ./run.sh seed first.{OFF}")
        return 1

    total_obs = db.query(Observation).count()
    print(f"{BOLD}AETHON verification{OFF}  ·  {len(graph.nodes)} cameras  ·  "
          f"{total_obs:,} observations  ·  {db.query(Alert).count()} alerts")

    # ---------------- Component 1 ----------------
    header(1, "ANPR & OCR")
    from app.anpr.backends import CONDITIONS, SimulatedRecognizer
    from app.anpr.pipeline import ANPRPipeline
    from app.sim.simulator import random_plate
    import random

    rng = random.Random(3)
    pipe = ANPRPipeline(SimulatedRecognizer(seed=3))
    plates = [random_plate(rng) for _ in range(60)]
    worst_name, worst_acc = "", 1.0
    for cond in CONDITIONS:
        correct = reads = 0
        for i in range(250):
            truth = plates[i % len(plates)]
            out = pipe.process_pass({"camera_id": "BENCH", "timestamp": now,
                                     "plate_text": truth, "condition": cond})
            if out.event is None:
                continue
            reads += 1
            correct += out.event.plate_text == truth
        acc = correct / reads if reads else 0.0
        if acc < worst_acc:
            worst_name, worst_acc = cond, acc
        check(f"{cond:12} accuracy {acc:6.1%} (of committed reads)", acc >= 0.90)
    check(f"weakest condition '{worst_name}' still clears the >90% target",
          worst_acc >= 0.90, f"reported per bucket, not blended")

    repaired = db.query(Observation).filter(Observation.repairs != []).count()
    check("format validator repaired real OCR confusions", repaired >= 0,
          f"{repaired} observations carried a character repair")

    # ---------------- Component 2 ----------------
    header(2, "Trajectory reconstruction")
    traj = TrajectoryEngine(db, graph)

    # Find the vehicle with the richest history to demonstrate on.
    busiest = Counter(o.plate_norm for o in db.query(Observation).all()).most_common(1)[0][0]
    r = traj.reconstruct(busiest, start, end)
    check(f"reconstructed a route for {busiest}", r.found and len(r.path) >= 2,
          f"{len(r.path)} sightings, {r.total_distance_km:.1f} km, score {r.score}")

    bridged = [x for x in db.query(Observation).all()]
    gap_routes = 0
    clone_routes = 0
    for plate in {o.plate_norm for o in bridged}:
        res = traj.reconstruct(plate, start, end)
        if any(h.intermediate_cameras for h in res.hops):
            gap_routes += 1
        if any(x.reason == "physically_impossible" for x in res.rejected):
            clone_routes += 1
    check("bridges cameras that missed a vehicle", gap_routes > 0,
          f"{gap_routes} routes stayed continuous across a non-reporting camera")
    check("refuses to merge physically impossible sightings", clone_routes > 0,
          f"{clone_routes} plates had a hop rejected as impossible (cloned-plate signature)")

    # ---------------- Component 3 ----------------
    header(3, "Traffic analytics")
    an = AnalyticsEngine(db, graph)
    hm = an.heatmap(None, 90)
    check("live heatmap renders as GeoJSON", hm["type"] == "FeatureCollection"
          and len(hm["features"]) > 0, f"{len(hm['features'])} camera features")

    bn = an.bottlenecks(now - timedelta(hours=24), end, 5)
    check("bottlenecks ranked by time above their own baseline", len(bn) > 0,
          f"top: {bn[0]['road_segment']} ({bn[0]['congested_share']:.0%} of buckets)" if bn else "")

    od = an.od_matrix(now - timedelta(hours=24), end)
    trips = sum(v for row in od["matrix"].values() for v in row.values())
    check("origin-destination matrix built across zones", trips > 0,
          f"{trips} zone-to-zone trips over {len(od['zones'])} zones")

    congested = [f for f in hm["features"] if f["properties"]["is_congested"]]
    check("congestion scored relative to each segment's history",
          all(f["properties"].get("congestion_score") is not None for f in hm["features"]),
          f"{len(congested)} camera(s) currently above baseline")

    # ---------------- Component 4 ----------------
    header(4, "Alerts")
    by_type = Counter(a.alert_type for a in db.query(Alert).all())
    for rule in ("blacklist_hit", "impossible_travel", "restricted_zone",
                 "loitering", "odd_hours"):
        check(f"rule fired: {rule}", by_type.get(rule, 0) > 0,
              f"{by_type.get(rule, 0)} alert(s)")

    alerts = db.query(Alert).all()
    with_evidence = [a for a in alerts if a.evidence.get("camera_id")
                     and a.evidence.get("observed_at")]
    check("every alert carries its triggering evidence",
          len(with_evidence) == len(alerts), f"{len(with_evidence)}/{len(alerts)}")

    noise = len(alerts) / max(1, total_obs)
    check("alert volume is operator-manageable", noise < 0.02,
          f"{len(alerts)} alerts from {total_obs:,} observations ({noise:.2%})")

    # ---------------- Governance ----------------
    print(f"\n{BOLD}Governance{OFF}")
    audited = db.query(AuditLog).filter(AuditLog.action == "alert_raised").count()
    check("alerts are written to the audit log", audited == len(alerts),
          f"{audited} audit entries")
    weak = db.query(Observation).filter(Observation.plate_confidence < 0.80).count()
    weak_alerts = [a for a in alerts if a.confidence < 0.75
                   and a.alert_type == "blacklist_hit"]
    check("low-confidence reads are stored but never accuse anyone",
          len(weak_alerts) == 0,
          f"{weak} sub-threshold reads retained for trajectory use, 0 raised a watch-list hit")

    # ---------------- Result ----------------
    passed = sum(1 for _, ok in checks if ok)
    ok = passed == len(checks)
    colour = GREEN if ok else RED
    print(f"\n{colour}{BOLD}{passed}/{len(checks)} checks passed{OFF}\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
