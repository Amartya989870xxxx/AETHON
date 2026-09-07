# PlateTrail

**City-Wide AI Engine for Multi-Camera ANPR Trajectory Tracking and Urban
Traffic Analytics**

SIH 2026 · Problem Statement **26127** · Bharat Electronics Limited · Software
· Smart Automation

A correlation layer over a city's **existing** ANPR/CCTV network. It reads
plates under adverse conditions, stitches sightings of the same vehicle across
cameras into a chronological route on a GIS map, rolls every camera's readings
into city-wide flow analytics, and raises real-time alerts on watch-listed
plates and route anomalies.

No new camera hardware. Only ~200-byte structured events leave each camera
site — never video.

---

## Quick start

```bash
pip install -r requirements.txt

./run.sh seed --hours 12 --vehicles-per-hour 70   # build a demo dataset (~4s)
./run.sh demo                                     # 24-check verification
./run.sh test                                     # 82 tests
./run.sh serve                                    # API on :8000, docs at /docs
```

---

## The four deliverables

| # | Component | Code | Endpoint |
|---|---|---|---|
| 1 | ANPR & OCR | `app/anpr/` | `POST /api/observations`, `GET /api/benchmark/anpr` |
| 2 | Trajectory reconstruction | `app/engines/trajectory.py` | `GET /api/trajectory/{plate}` |
| 3 | Traffic analytics | `app/engines/analytics.py` | `GET /api/analytics/*` |
| 4 | Alerts | `app/engines/alerts.py` | `GET /api/alerts`, `WS /ws/alerts` |
| — | Governance | `app/models.py` | `GET /api/audit` |

### What each one actually does

**1 — Recognition.** Multi-frame fusion by independent-evidence log-odds
pooling (six frames agreeing at 0.85 → 0.99, not 0.85), plus format-aware
repair against Indian plate structure. `0L4CAF3125` → `DL4CAF3125`, because
`OL` and `QL` are not RTO codes but `DL` is. Abstains rather than guessing.

**2 — Trajectory.** Best-path search over a road-network graph, not
`ORDER BY time`. Bridges cameras that missed a vehicle; refuses to merge
sightings the road network says are impossible — which is how cloned plates get
caught (several hundred km/h implied, in the demo).

**3 — Analytics.** Density, speed, OD matrix and congestion heatmaps, scored
against each segment's **own** baseline for that weekday and hour. Runs even
where OCR confidence is poor.

**4 — Alerts.** Watch list (exact + confidence-gated fuzzy) and five anomaly
rules. 16 alerts from 3,779 observations — 0.42%. Every alert carries its
evidence; every rule is tested for what it must *not* fire on.

---

## Measured accuracy

Per condition bucket, never blended (`GET /api/benchmark/anpr`):

| Condition | Accuracy of committed reads |
|---|---|
| day_clear | 99.8% |
| day_rain | 99.8% |
| night_clear | 99.8% |
| night_rain | 96.5% |
| glare | 98.3% |
| angled | 99.8% |

The simulator fakes the **camera**, not the **algorithm** — fusion, format
repair and confidence gating are the production code paths. A trained OCR model
is not yet attached; see *Honest limits* in the architecture doc.

---

## Layout

```
backend/app/
  anpr/         Component 1 — fusion, format repair, rectification, backends
  engines/      Components 2-4 — camera graph, trajectory, analytics, alerts
  ingest/       one write path; event bus (asyncio now, MQTT/Kafka later)
  sim/          synthetic city, traffic generator, demo scenarios
  api/          FastAPI routers
  models.py     11 tables
backend/tests/  82 tests
scripts/        seed.py, demo.py
docs/           ARCHITECTURE.md · PITCH_SCRIPT.md · HANDOFF.md · SPEC_v2.md
```

## Docs

- **`docs/ARCHITECTURE.md`** — full walkthrough: how every component works and
  why, with the honest limits
- **`docs/PITCH_SCRIPT.md`** — 5-minute pitch, timed, plus a Q&A bank
- **`docs/HANDOFF.md`** — slide-by-slide deck guide and quotable numbers

## Stack

FastAPI · SQLAlchemy 2 · NetworkX · OpenCV · NumPy · SQLite (→ PostGIS +
TimescaleDB via one connection string).
