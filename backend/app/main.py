"""AETHON API service.

One AI layer over a city's existing camera network, exposing the four
deliverables of SIH 2026 PS 26127 through a single HTTP/WebSocket surface:

    Component 1  ANPR + OCR              POST /api/observations, /api/benchmark/anpr
    Component 2  Trajectory tracking     GET  /api/trajectory/{plate}
    Component 3  Traffic analytics       GET  /api/analytics/*
    Component 4  Alerts                  GET  /api/alerts, WS /ws/alerts
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import analytics_routes, live, security, system, tracking
from .config import settings
from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=f"{settings.app_name} API",
    version=settings.version,
    description=__doc__,
    lifespan=lifespan,
)

# The dashboard is a separate origin during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(tracking.router)
app.include_router(analytics_routes.router)
app.include_router(security.router)
app.include_router(live.router)


@app.get("/", tags=["system"])
def root() -> dict:
    return {
        "service": settings.app_name,
        "problem_statement": f"SIH 2026 · PS {settings.ps_id} · Bharat Electronics Limited",
        "components": {
            "1_anpr_ocr": ["POST /api/observations", "GET /api/benchmark/anpr"],
            "2_trajectory": ["GET /api/trajectory/{plate}", "GET /api/plates/search"],
            "3_analytics": ["GET /api/analytics/heatmap", "GET /api/analytics/bottlenecks",
                            "GET /api/analytics/od", "GET /api/analytics/segment/{segment}"],
            "4_alerts": ["GET /api/alerts", "GET /api/blacklist", "WS /ws/alerts"],
        },
        "governance": ["GET /api/audit"],
        "docs": "/docs",
    }
