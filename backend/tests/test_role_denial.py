"""Integration test — role-based access denial.

Verifies that the viewer role is denied write operations that require
elevated roles. The viewer can read public observations but cannot create
observations, incidents, or tasks. Admin can perform all write operations.

Uses the real PostgreSQL database and the real FastAPI app via TestClient.
Demo users are seeded directly via seed_demo_users(). No source files modified.
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
    assert resp.status_code == 200, f"login failed for {email}: {resp.text}"
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_viewer_cannot_create_observation() -> None:
    """POST /api/observations as viewer → 403 (requires write roles)."""
    with TestClient(app) as client:
        viewer_token = _login(client, "viewer@demo.disaster")
        admin_token = _login(client, "admin@demo.disaster")

        # Create an incident as admin so the viewer has a valid incident_id.
        inc_resp = client.post(
            "/api/incidents",
            json={"title": "Role Test", "disaster_type": "flood"},
            headers=_auth_header(admin_token),
        )
        assert inc_resp.status_code == 201
        incident_id = inc_resp.json()["id"]

        feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-73.9, 40.7]},
            "properties": {
                "event_type": "sensor_observation",
                "phenomenon": "water_level",
                "source_id": "test_src_role",
                "source_type": "sensor",
            },
        }
        resp = client.post(
            f"/api/observations?incident_id={incident_id}",
            json=feature,
            headers=_auth_header(viewer_token),
        )
        assert resp.status_code == 403, (
            f"expected 403 for viewer creating observation, got {resp.status_code}"
        )


def test_viewer_cannot_create_incident() -> None:
    """POST /api/incidents as viewer → 403 (requires admin/emergency_manager)."""
    with TestClient(app) as client:
        viewer_token = _login(client, "viewer@demo.disaster")

        resp = client.post(
            "/api/incidents",
            json={"title": "Viewer Incident", "disaster_type": "flood"},
            headers=_auth_header(viewer_token),
        )
        assert resp.status_code == 403, (
            f"expected 403 for viewer creating incident, got {resp.status_code}"
        )


def test_viewer_cannot_create_task() -> None:
    """POST /api/incidents/{id}/tasks as viewer → 403 (requires manage roles)."""
    with TestClient(app) as client:
        viewer_token = _login(client, "viewer@demo.disaster")
        admin_token = _login(client, "admin@demo.disaster")

        inc_resp = client.post(
            "/api/incidents",
            json={"title": "Task Role Test", "disaster_type": "flood"},
            headers=_auth_header(admin_token),
        )
        assert inc_resp.status_code == 201
        incident_id = inc_resp.json()["id"]

        resp = client.post(
            f"/api/incidents/{incident_id}/tasks",
            json={"title": "Test Task"},
            headers=_auth_header(viewer_token),
        )
        assert resp.status_code == 403, (
            f"expected 403 for viewer creating task, got {resp.status_code}"
        )


def test_admin_can_create_incident() -> None:
    """POST /api/incidents as admin → 201 (positive control)."""
    with TestClient(app) as client:
        admin_token = _login(client, "admin@demo.disaster")

        resp = client.post(
            "/api/incidents",
            json={"title": "Admin Incident", "disaster_type": "flood"},
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "Admin Incident"
        assert body["disaster_type"] == "flood"


def test_field_responder_can_create_observation() -> None:
    """POST /api/observations as field_responder → 201 (allowed write role)."""
    with TestClient(app) as client:
        admin_token = _login(client, "admin@demo.disaster")
        fr_token = _login(client, "field_responder@demo.disaster")

        inc_resp = client.post(
            "/api/incidents",
            json={"title": "FR Test", "disaster_type": "flood"},
            headers=_auth_header(admin_token),
        )
        assert inc_resp.status_code == 201
        incident_id = inc_resp.json()["id"]

        feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-73.9, 40.7]},
            "properties": {
                "event_type": "sensor_observation",
                "phenomenon": "water_level",
                "source_id": "test_src_fr",
                "source_type": "sensor",
            },
        }
        resp = client.post(
            f"/api/observations?incident_id={incident_id}",
            json=feature,
            headers=_auth_header(fr_token),
        )
        assert resp.status_code == 201, resp.text


def test_viewer_cannot_start_simulator() -> None:
    """POST /api/simulator/start as viewer → 403 (requires admin/em)."""
    with TestClient(app) as client:
        viewer_token = _login(client, "viewer@demo.disaster")

        resp = client.post(
            "/api/simulator/start",
            json={
                "org_id": "org_demo",
                "incident_id": "inc_sim_test",
                "device_count": 1,
                "seed": 42,
            },
            headers=_auth_header(viewer_token),
        )
        assert resp.status_code == 403, (
            f"expected 403 for viewer starting simulator, got {resp.status_code}"
        )
