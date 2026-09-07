#!/usr/bin/env python3
"""Build a complete demo dataset from scratch.

Loads the camera network, generates a period of city traffic, pushes every
vehicle pass through the real ANPR pipeline and the real write path, plants
the alert scenarios, then runs aggregation. The result is a database a
dashboard can be pointed at immediately.

    python3 scripts/seed.py --hours 12 --vehicles-per-hour 90
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db import SessionLocal, engine, init_db          # noqa: E402
from app.engines.alerts import AlertEngine                # noqa: E402
from app.engines.analytics import AnalyticsEngine         # noqa: E402
from app.engines.camera_graph import CameraGraph          # noqa: E402
from app.ingest.worker import process_event               # noqa: E402
from app.models import (                                  # noqa: E402
    Alert, AuditLog, BlacklistEntry, Base, Camera, CameraLink, ODFlow,
    Observation, PlateProfile, TrafficAggregate, Trajectory, ZonePermit,
)
from app.sim.city import build_camera_rows, build_link_rows   # noqa: E402
from app.sim.scenarios import build_all                       # noqa: E402
from app.sim.simulator import TrafficSimulator                # noqa: E402


def reset(db):
    for model in (Alert, AuditLog, Trajectory, TrafficAggregate, ODFlow,
                  PlateProfile, Observation, BlacklistEntry, ZonePermit,
                  CameraLink, Camera):
        db.query(model).delete()
    db.commit()


def load_topology(db):
    db.add_all([Camera(**row) for row in build_camera_rows()])
    db.flush()
    db.add_all([CameraLink(**row) for row in build_link_rows()])
    db.commit()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=12, help="hours of traffic to generate")
    ap.add_argument("--vehicles-per-hour", type=int, default=90)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    t0 = time.time()
    init_db()
    db = SessionLocal()
    try:
        print("resetting database…")
        reset(db)
        load_topology(db)

        graph = CameraGraph.from_db(db)
        print(f"topology: {graph.summary()}")

        sim = TrafficSimulator(graph, seed=args.seed)
        alert_engine = AlertEngine(db, graph)

        # Window ends now so the dashboard's "last 15 minutes" view has data.
        end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(hours=args.hours)

        print(f"generating {args.hours}h of traffic from {start:%Y-%m-%d %H:%M} UTC…")
        passes = sim.generate_period(start, args.hours, args.vehicles_per_hour)
        print(f"  {len(passes):,} vehicle passes across {len(graph.nodes)} cameras")

        # --- scenarios ----------------------------------------------------
        scenario_start = end - timedelta(hours=3)
        scenarios = build_all(sim, scenario_start)
        for sc in scenarios:
            passes.extend(sc.passes)
        # The watch list is populated *before* ingestion, as it would be in
        # reality — the alert engine must catch the vehicle live, not in hindsight.
        blacklisted = next(s for s in scenarios if s.key == "blacklist")
        db.add_all([
            BlacklistEntry(plate_norm=blacklisted.plate,
                           reason="Vehicle of interest — theft investigation TR/2026/1188",
                           severity="critical", added_by="control_room_si_kumar"),
            BlacklistEntry(plate_norm="DL9CX4471",
                           reason="Outstanding challans exceeding threshold",
                           severity="medium", added_by="rto_sync"),
        ])
        # Permits for the commercial fleet that works the industrial corridor.
        db.add_all([
            ZonePermit(plate_norm=plate, zone="industrial",
                       issued_by="city_transport_authority")
            for plate in sim.industrial_fleet
        ])
        db.commit()
        alert_engine.invalidate_blacklist()

        passes.sort(key=lambda p: p.timestamp)

        # --- ingest -------------------------------------------------------
        print(f"running ANPR + ingestion on {len(passes):,} passes…")
        stored = abstained = alerts_raised = 0
        for i, vp in enumerate(passes, 1):
            event = sim.recognise(vp)
            if event is None:
                abstained += 1
                continue
            _obs, alerts = process_event(db, graph, event, alert_engine)
            stored += 1
            alerts_raised += len(alerts)
            if i % 2000 == 0:
                db.commit()
                print(f"  {i:,}/{len(passes):,} …")
        db.commit()

        print(f"  stored {stored:,} observations, abstained on {abstained:,} "
              f"({abstained/max(1,len(passes)):.1%}), raised {alerts_raised} alerts")

        # --- analytics ----------------------------------------------------
        print("aggregating traffic analytics…")
        analytics = AnalyticsEngine(db, graph)
        n_buckets = analytics.aggregate(start, end + timedelta(hours=1))
        n_od = analytics.compute_od(start, end + timedelta(hours=1))
        db.commit()
        print(f"  {n_buckets:,} aggregate buckets, {n_od:,} OD cells")

        # --- summary ------------------------------------------------------
        print("\nscenario plates for the demo:")
        for sc in scenarios:
            print(f"  {sc.plate:12}  {sc.key:11}  expect={sc.expect:20} {sc.title}")

        by_type = {}
        for a in db.query(Alert).all():
            by_type[a.alert_type] = by_type.get(a.alert_type, 0) + 1
        print(f"\nalerts by type: {by_type}")
        print(f"done in {time.time()-t0:.1f}s")
    finally:
        db.close()


if __name__ == "__main__":
    main()
