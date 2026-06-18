"""Smoke tests proving the skeleton boots without a database (DESIGN boot contract)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_openapi_loads():
    resp = client.get("/openapi.json")
    assert resp.status_code == 200


def test_metadata_complete():
    from app.db import Base
    import app.models  # noqa: F401

    # All 15 entities from DESIGN §4 are registered.
    assert len(Base.metadata.tables) == 15


def test_engine_signatures_importable():
    from app.ingestion.pipeline import ingest_record, process_record, run_source  # noqa: F401
    from app.analysis.engine import recompute_assessments  # noqa: F401
    from app.recommend.rules import generate_recommendations  # noqa: F401
    from app.realtime.manager import manager  # noqa: F401
    from app.realtime.events import emit, EventType  # noqa: F401

    assert EventType.ALERT_CREATED == "alert_created"
