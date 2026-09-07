"""Health, camera inventory, road graph, and the ANPR accuracy benchmark."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..engines.camera_graph import CameraGraph
from ..ingest.bus import bus
from ..models import Alert, Camera, Observation
from .deps import get_graph

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.version,
        "problem_statement": settings.ps_id,
        "counts": {
            "cameras": db.scalar(select(func.count()).select_from(Camera)) or 0,
            "observations": db.scalar(select(func.count()).select_from(Observation)) or 0,
            "alerts": db.scalar(select(func.count()).select_from(Alert)) or 0,
        },
        "ingest": bus.stats(),
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/cameras")
def list_cameras(db: Session = Depends(get_db)) -> dict:
    """Camera inventory as GeoJSON — drops straight onto the map layer."""
    cams = db.execute(select(Camera)).scalars().all()
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [c.lon, c.lat]},
                "properties": {
                    "camera_id": c.camera_id, "name": c.name,
                    "road_segment": c.road_segment, "zone": c.zone,
                    "facing_direction": c.facing_direction, "lanes": c.lanes,
                    "is_restricted": c.is_restricted, "active": c.active,
                },
            }
            for c in cams
        ],
    }


@router.get("/api/cameras/graph")
def camera_graph(graph: CameraGraph = Depends(get_graph)) -> dict:
    """The road network as nodes and edges, for drawing route lines."""
    return {
        "summary": graph.summary(),
        "nodes": [
            {"camera_id": n.camera_id, "name": n.name, "lat": n.lat, "lon": n.lon,
             "zone": n.zone, "road_segment": n.road_segment,
             "is_restricted": n.is_restricted}
            for n in graph.nodes.values()
        ],
        "edges": [
            {"from": u, "to": v, "distance_km": d["distance_km"],
             "heading": d["heading"], "road_name": d["road_name"],
             "speed_limit_kmph": d["speed_limit"]}
            for u, v, d in graph.g.edges(data=True)
        ],
    }


@router.get("/api/benchmark/anpr")
def anpr_benchmark(
    samples: int = Query(300, ge=50, le=5000,
                         description="passes to simulate per condition bucket"),
    seed: int = Query(7),
) -> dict:
    """Measure recognition accuracy **per capture condition**.

    Reporting one blended number is how a system claims 97% while failing at
    night in the rain. The problem statement asks for >90% under adverse
    conditions, so accuracy is measured and reported per bucket, and the
    weakest bucket is stated explicitly rather than averaged away.
    """
    import random
    import statistics

    from ..anpr.backends import CONDITIONS, SimulatedRecognizer
    from ..anpr.pipeline import ANPRPipeline
    from ..sim.simulator import random_plate

    rng = random.Random(seed)
    pipeline = ANPRPipeline(SimulatedRecognizer(seed=seed))
    plates = [random_plate(rng) for _ in range(120)]

    results = {}
    for condition in CONDITIONS:
        correct = abstained = alertable = 0
        wrong_plates: list[dict] = []
        confidences: list[float] = []
        for i in range(samples):
            truth = plates[i % len(plates)]
            out = pipeline.process_pass({
                "camera_id": "BENCH", "timestamp": datetime.now(timezone.utc),
                "plate_text": truth, "condition": condition,
            })
            if out.event is None:
                abstained += 1
                continue
            confidences.append(out.event.plate_confidence)
            if out.event.plate_text == truth:
                correct += 1
            elif len(wrong_plates) < 5:
                wrong_plates.append({"truth": truth, "read": out.event.plate_text,
                                     "confidence": out.event.plate_confidence})
            if out.event.alertable:
                alertable += 1
        read = samples - abstained
        results[condition] = {
            "samples": samples,
            "abstained": abstained,
            "abstention_rate": round(abstained / samples, 4),
            # Accuracy over reads the system actually committed to.
            "accuracy_of_reads": round(correct / read, 4) if read else 0.0,
            # Stricter: an abstention counts as a miss.
            "end_to_end_accuracy": round(correct / samples, 4),
            "alertable_rate": round(alertable / samples, 4),
            "mean_confidence": round(statistics.mean(confidences), 4) if confidences else 0.0,
            "example_errors": wrong_plates,
        }

    per_read = [v["accuracy_of_reads"] for v in results.values()]
    worst = min(results.items(), key=lambda kv: kv[1]["accuracy_of_reads"])
    return {
        "target": ">90% correct full-plate recognition under adverse conditions",
        "by_condition": results,
        "blended_accuracy_of_reads": round(statistics.mean(per_read), 4),
        "worst_condition": {"condition": worst[0], **worst[1]},
        "meets_target_in_all_conditions": all(a >= 0.90 for a in per_read),
        "note": (
            "Measured on the production ANPR pipeline (multi-frame fusion, "
            "format validation, confidence gating) driven by a simulated "
            "camera. The camera is simulated; the recognition logic under test "
            "is not."
        ),
    }
