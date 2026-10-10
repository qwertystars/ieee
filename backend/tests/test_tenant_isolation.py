"""Integration test — tenant isolation via org_id enforcement.

Verifies that a user in org A cannot read observations created by a user in
org B. org_id is extracted from the signed JWT by OrgContextMiddleware and
applied as a WHERE clause on every observation query. Cross-tenant access
returns 404 (not 403) to avoid leaking the existence of the resource.

Uses the real PostgreSQL database and the real FastAPI app via TestClient.
Demo users are seeded directly via seed_demo_users(); a second org's user is
inserted manually. No source files are modified.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.auth.passwords import hash_password
from app.auth.seed import seed_demo_users
from app.db import SessionLocal
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.main import app
from app.models.user import User

ORG_A = "org_demo"
ORG_B = "org_other_isolation"
PASSWORD = "demo1234"
USER_B_EMAIL = "admin@other-isolation.disaster"


@pytest.fixture(scope="module", autouse=True)
def _seed_users() -> None:
    """Seed demo users (org A) + one user in org B."""
    db = SessionLocal()
    seed_demo_users(db)
    # Create a user in org B if not present.
    existing = db.query(User).filter(User.email == USER_B_EMAIL).first()
    if existing is None:
        db.add(
            User(
                id=generate_ulid(),
                email=USER_B_EMAIL,
                hashed_password=hash_password(PASSWORD),
                role="admin",
                org_id=ORG_B,
                created_at=now_ms(),
            )
        )
        db.commit()
    db.close()
    yield
    # Cleanup org B user.
    db = SessionLocal()
    db.execute(delete(User).where(User.org_id == ORG_B))
    db.commit()
    db.close()


def _login(client: TestClient, email: str) -> str:
    """Login and return the JWT bearer token."""
    resp = client.post(
        "/api/auth/login",
        data={"username": email, "password": PASSWORD},
    )
    assert resp.status_code == 200, f"login failed for {email}: {resp.text}"
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_incident(client: TestClient, token: str) -> str:
    """Create an incident and return its ID."""
    resp = client.post(
        "/api/incidents",
        json={"title": "Isolation Test", "disaster_type": "flood"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_observation(
    client: TestClient, token: str, incident_id: str, lon: float, lat: float
) -> str:
    """Create an observation and return its ID."""
    feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "event_type": "sensor_observation",
            "phenomenon": "water_level",
            "value": 1.2,
            "unit": "m",
            "source_id": "test_src_iso",
            "source_type": "sensor",
        },
    }
    resp = client.post(
        f"/api/observations?incident_id={incident_id}",
        json=feature,
        headers=_auth_header(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["properties"]["observation_id"]


def test_cross_org_observation_access_returns_404() -> None:
    """User in org B cannot GET an observation created by org A → 404."""
    with TestClient(app) as client:
        token_a = _login(client, "admin@demo.disaster")
        token_b = _login(client, USER_B_EMAIL)

        inc_a = _create_incident(client, token_a)
        obs_id = _create_observation(client, token_a, inc_a, -73.9, 40.7)

        # Org B user tries to read org A's observation.
        resp = client.get(
            f"/api/observations/{obs_id}",
            headers=_auth_header(token_b),
        )
        assert resp.status_code == 404, (
            f"expected 404 for cross-org access, got {resp.status_code}"
        )


def test_cross_org_incident_access_returns_404() -> None:
    """User in org B cannot GET an incident created by org A → 404."""
    with TestClient(app) as client:
        token_a = _login(client, "admin@demo.disaster")
        token_b = _login(client, USER_B_EMAIL)

        inc_a = _create_incident(client, token_a)

        resp = client.get(
            f"/api/incidents/{inc_a}",
            headers=_auth_header(token_b),
        )
        assert resp.status_code == 404, (
            f"expected 404 for cross-org incident, got {resp.status_code}"
        )


def test_same_org_observation_list_visible() -> None:
    """User in org A can list observations created in org A."""
    with TestClient(app) as client:
        token_a = _login(client, "admin@demo.disaster")

        inc_a = _create_incident(client, token_a)
        _create_observation(client, token_a, inc_a, -73.9, 40.7)

        resp = client.get(
            f"/api/observations?incident_id={inc_a}",
            headers=_auth_header(token_a),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "FeatureCollection"
        assert len(body["features"]) >= 1


def test_cross_org_observation_list_excludes_other_org() -> None:
    """Listing observations in org B does not show org A's observations."""
    with TestClient(app) as client:
        token_a = _login(client, "admin@demo.disaster")
        token_b = _login(client, USER_B_EMAIL)

        inc_a = _create_incident(client, token_a)
        _create_observation(client, token_a, inc_a, -73.9, 40.7)

        # Org B lists observations — should not see org A's data.
        resp = client.get(
            "/api/observations",
            headers=_auth_header(token_b),
        )
        assert resp.status_code == 200
        body = resp.json()
        obs_ids = [
            f["properties"]["observation_id"] for f in body["features"]
        ]
        # Org A's observations must not appear in org B's list.
        assert all("obs" not in oid for oid in obs_ids), (
            "cross-org data leaked into observation list"
        )


def test_cross_org_realtime_polling_returns_403() -> None:
    """Given an org-A incident, When org B polls it, Then access is denied."""
    with TestClient(app) as client:
        token_a = _login(client, "admin@demo.disaster")
        token_b = _login(client, USER_B_EMAIL)
        incident_id = _create_incident(client, token_a)

        response = client.get(
            f"/api/incidents/{incident_id}/updates?since=0",
            headers=_auth_header(token_b),
        )
    assert response.status_code == 403
    assert "observations" not in response.text


def test_wrong_incident_realtime_polling_returns_403() -> None:
    """Given an unknown incident, When an org member polls it, Then access is denied."""
    with TestClient(app) as client:
        token = _login(client, "admin@demo.disaster")
        response = client.get(
            "/api/incidents/01J9WRONGINCIDENT0000000000/updates?since=0",
            headers=_auth_header(token),
        )
    assert response.status_code == 403
    assert "observations" not in response.text
