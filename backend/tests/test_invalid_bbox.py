"""Integration test — invalid bbox rejection.

Verifies that the observations list endpoint rejects malformed bbox query
parameters with HTTP 422. The _parse_bbox helper in observations.py accepts
only "minx,miny,maxx,maxy" with exactly 4 numeric values.

Uses the real PostgreSQL database and the real FastAPI app via TestClient.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.seed import seed_demo_users
from app.db import SessionLocal
from app.main import app

PASSWORD = "demo1234"


@pytest.fixture(scope="module", autouse=True)
def _seed_users() -> None:
    db = SessionLocal()
    seed_demo_users(db)
    db.close()


def _login(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/auth/login",
        data={"username": email, "password": PASSWORD},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_incident(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/incidents",
        json={"title": "BBox Test", "disaster_type": "flood"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_bbox_non_numeric_rejected() -> None:
    """bbox with non-numeric values → 422."""
    with TestClient(app) as client:
        token = _login(client, "admin@demo.disaster")
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/observations?incident_id={inc_id}&bbox=a,b,c,d",
            headers=_auth_header(token),
        )
        assert resp.status_code == 422, (
            f"expected 422 for non-numeric bbox, got {resp.status_code}"
        )
        body = resp.json()
        assert "error" in body
        assert "numeric" in body["error"]["message"].lower()


def test_bbox_wrong_count_rejected() -> None:
    """bbox with wrong number of parts → 422."""
    with TestClient(app) as client:
        token = _login(client, "admin@demo.disaster")
        inc_id = _create_incident(client, token)

        # 3 parts
        resp = client.get(
            f"/api/observations?incident_id={inc_id}&bbox=1,2,3",
            headers=_auth_header(token),
        )
        assert resp.status_code == 422, (
            f"expected 422 for 3-part bbox, got {resp.status_code}"
        )

        # 5 parts
        resp = client.get(
            f"/api/observations?incident_id={inc_id}&bbox=1,2,3,4,5",
            headers=_auth_header(token),
        )
        assert resp.status_code == 422, (
            f"expected 422 for 5-part bbox, got {resp.status_code}"
        )


def test_bbox_empty_string_rejected() -> None:
    """bbox with empty string → 422 (single empty part, wrong count)."""
    with TestClient(app) as client:
        token = _login(client, "admin@demo.disaster")
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/observations?incident_id={inc_id}&bbox=",
            headers=_auth_header(token),
        )
        assert resp.status_code == 422


def test_valid_bbox_accepted() -> None:
    """A valid bbox returns 200 with a FeatureCollection (positive control)."""
    with TestClient(app) as client:
        token = _login(client, "admin@demo.disaster")
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/observations?incident_id={inc_id}&bbox=-180,-90,180,90",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "FeatureCollection"


def test_bbox_with_negative_coords_accepted() -> None:
    """bbox with negative coordinates (western/southern hemispheres) → 200."""
    with TestClient(app) as client:
        token = _login(client, "admin@demo.disaster")
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/observations?incident_id={inc_id}"
            "&bbox=-122.5,37.7,-122.4,37.8",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
