"""Shared fixtures: an in-memory city with a known topology."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.camera_graph import CameraGraph      # noqa: E402
from app.models import Base, Camera, CameraLink       # noqa: E402
from app.sim.city import build_camera_rows, build_link_rows  # noqa: E402

T0 = datetime(2026, 9, 7, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool, future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False, future=True)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def city(db):
    """The full 16-camera synthetic network."""
    db.add_all([Camera(**r) for r in build_camera_rows()])
    db.flush()
    db.add_all([CameraLink(**r) for r in build_link_rows()])
    db.commit()
    return CameraGraph.from_db(db)


@pytest.fixture()
def at():
    """Helper: a timestamp N seconds after the fixed test epoch."""
    return lambda seconds: T0 + timedelta(seconds=seconds)
