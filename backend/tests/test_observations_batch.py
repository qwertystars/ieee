"""Tests for POST /api/observations/batch (T22).

Verifies:
  1. Happy path: 100 features -> 201 with count=100 and 100 obs in DB.
  2. 101 features -> 422 (exceeds max batch).
  3. Empty FeatureCollection -> 422.
  4. No auth token -> 401.
  5. Single-obs POST still works (regression).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.seed import seed_demo_users
from app.db import SessionLocal
from app.main import app
from app.models.observation import Observation

PASSWORD = "demo1234"
ADMIN_EMAIL = "admin@demo.disaster"

_POINT_GEOMETRY = {
    "type": "Point",
    "coordinates": [144.9631, -37.8136],
}


def _feature(idx: int) -> dict[str, Any]:
    """Build a minimal valid GeoJSON Feature for observation ingestion."""
    return {
        "type": "Feature",
        "geometry": _POINT_GEOMETRY,
        "properties": {
            "event_type": "flood_depth",
            "phenomenon": "water_level",
            "value": float(idx) * 0.1,
            "unit": "m",
            "source_id": f"sensor_{idx}",
            "source_type": "sensor",
            "observed_at": 1756000000000 + idx,
        },
    }


def _feature_collection(n: int) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": [_feature(i) for i in range(n)]}


@pytest.fixture(scope="module", autouse=True)
def _seed_users() -> None:
    db = SessionLocal()
    seed_demo_users(db)
    db.close()
    yield


def _login(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/auth/login",
        data={"username": email, "password": PASSWORD},
    )
    assert resp.status_code == 200, f"login failed for {email}: {resp.text}"
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_incident(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/incidents",
        json={"title": "Batch Test Incident", "disaster_type": "flood"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── Happy path: 100 features -> 201 ──────────────────────────────────────────


def test_batch_100_features_returns_201_with_count() -> None:
    """Given 100 valid features, POST /batch returns 201 with count=100."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)
        resp = client.post(
            "/api/observations/batch",
            params={"incident_id": inc_id},
            json=_feature_collection(100),
            headers=_auth_header(token),
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["count"] == 100
    assert len(body["observations"]) == 100
    for entry in body["observations"]:
        assert entry["status"] == "created"
        assert len(entry["id"]) == 26  # ULID length


def test_batch_100_features_creates_100_rows_in_db() -> None:
    """The 100 observations from the batch are persisted in the DB."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)
        resp = client.post(
            "/api/observations/batch",
            params={"incident_id": inc_id},
            json=_feature_collection(100),
            headers=_auth_header(token),
        )
        assert resp.status_code == 201
        obs_ids = {o["id"] for o in resp.json()["observations"]}

    db = SessionLocal()
    try:
        rows = db.execute(
            select(Observation.observation_id).where(
                Observation.incident_id == inc_id,
                Observation.observation_id.in_(obs_ids),
            )
        ).scalars().all()
        assert len(rows) == 100
    finally:
        db.close()


# ── 101 features -> 422 ──────────────────────────────────────────────────────


def test_batch_101_features_returns_422() -> None:
    """Exceeding the 100-feature cap returns 422, not 201."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)
        resp = client.post(
            "/api/observations/batch",
            params={"incident_id": inc_id},
            json=_feature_collection(101),
            headers=_auth_header(token),
        )
    assert resp.status_code == 422, resp.text


# ── Empty FeatureCollection -> 422 ───────────────────────────────────────────


def test_batch_empty_feature_collection_returns_422() -> None:
    """An empty FeatureCollection (zero features) returns 422."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)
        resp = client.post(
            "/api/observations/batch",
            params={"incident_id": inc_id},
            json={"type": "FeatureCollection", "features": []},
            headers=_auth_header(token),
        )
    assert resp.status_code == 422, resp.text


# ── No auth -> 401 ───────────────────────────────────────────────────────────


def test_batch_no_auth_returns_401() -> None:
    """Missing Authorization header yields 401."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/observations/batch",
            params={"incident_id": "01K0KF2EG0XC8KE3AD81HK0VEW"},
            json=_feature_collection(1),
        )
    assert resp.status_code == 401, resp.text


# ── Single-obs POST regression ───────────────────────────────────────────────


def test_single_obs_post_still_works() -> None:
    """The original POST /api/observations endpoint is unaffected."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)
        resp = client.post(
            "/api/observations",
            params={"incident_id": inc_id},
            json=_feature(0),
            headers=_auth_header(token),
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["type"] == "Feature"
    assert body["properties"]["event_type"] == "flood_depth"
