"""Integration test — WebSocket + polling fallback.

Verifies that:
1. The polling endpoint GET /api/incidents/{id}/updates works as a fallback
   when WebSocket is not available (returns observations newer than `since`).
2. The WebSocket endpoint /ws/realtime/{incident_id} rejects connections
   with invalid JWT tokens (closes with code 4001).
3. The WebSocket endpoint accepts connections with valid JWT tokens.

Uses the real PostgreSQL database and the real FastAPI app via TestClient.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.auth.seed import seed_demo_users
from app.db import SessionLocal
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.main import app
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.models.observation import Observation

PASSWORD = "demo1234"
ORG_ID = "org_demo"
INCIDENT_ID = "inc_ws_fallback_test"


@pytest.fixture(scope="module", autouse=True)
def _seed_users() -> None:
    db = SessionLocal()
    seed_demo_users(db)
    db.close()


@pytest.fixture
def db():
    """Yield a session and clean up test observations."""
    session = SessionLocal()
    session.execute(
        delete(Observation).where(Observation.incident_id == INCIDENT_ID)
    )
    session.commit()
    try:
        yield session
    finally:
        session.execute(
            delete(Observation).where(Observation.incident_id == INCIDENT_ID)
        )
        session.commit()
        session.close()


def _login(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/auth/login",
        data={"username": email, "password": PASSWORD},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _insert_observation(db, obs_id: str, observed_at: int) -> None:
    """Insert a minimal observation directly via ORM."""
    from geoalchemy2.elements import WKTElement

    db.add(
        Observation(
            observation_id=obs_id,
            event_type="sensor_observation",
            phenomenon="water_level",
            value=1.5,
            unit="m",
            geometry=WKTElement("POINT(-73.9 40.7)", srid=4326),
            geometry_uncertainty=5.0,
            observed_at=observed_at,
            valid_from=observed_at,
            received_at=observed_at,
            source_id="src_ws_test",
            source_type=SourceType.sensor,
            collection_method="gauge",
            source_reliability=0.9,
            freshness=1.0,
            corroboration_state=CorroborationState.uncorroborated,
            quality_flags={},
            access_policy=AccessPolicy.public,
            provenance_chain={},
            raw_data_hash="sha256:ws_test",
            org_id=ORG_ID,
            incident_id=INCIDENT_ID,
        )
    )
    db.commit()


def test_polling_returns_observations(db) -> None:
    """GET /api/incidents/{id}/updates returns observations newer than `since`."""
    base_ts = 1_700_000_000_000
    _insert_observation(db, "01J9TESTPOLL0001A", base_ts + 1000)
    _insert_observation(db, "01J9TESTPOLL0002A", base_ts + 2000)

    with TestClient(app) as client:
        token = _login(client, "admin@demo.disaster")
        resp = client.get(
            f"/api/incidents/{INCIDENT_ID}/updates?since={base_ts}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["incident_id"] == INCIDENT_ID
        assert body["since"] == base_ts
        assert body["count"] >= 2
        ids = [o["observation_id"] for o in body["observations"]]
        assert "01J9TESTPOLL0001A" in ids
        assert "01J9TESTPOLL0002A" in ids


def test_polling_filters_by_since(db) -> None:
    """Polling with a high `since` watermark excludes older observations."""
    base_ts = 1_700_000_100_000
    _insert_observation(db, "01J9TESTPOLL0003B", base_ts + 1000)
    _insert_observation(db, "01J9TESTPOLL0004B", base_ts + 5000)

    with TestClient(app) as client:
        token = _login(client, "admin@demo.disaster")
        # since = base_ts + 3000 → only the second observation qualifies.
        resp = client.get(
            f"/api/incidents/{INCIDENT_ID}/updates?since={base_ts + 3000}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        ids = [o["observation_id"] for o in body["observations"]]
        assert "01J9TESTPOLL0004B" in ids
        assert "01J9TESTPOLL0003B" not in ids


def test_websocket_rejects_invalid_token() -> None:
    """WebSocket with an invalid JWT token closes with code 4001."""
    from starlette.websockets import WebSocketDisconnect

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                f"/ws/realtime/{INCIDENT_ID}?token=invalid.jwt.token"
            ):
                pass
        assert exc_info.value.code == 4001


def test_websocket_accepts_valid_token() -> None:
    """WebSocket with a valid JWT token is accepted (no close code 4001)."""
    with TestClient(app) as client:
        token = _login(client, "admin@demo.disaster")
        with client.websocket_connect(
            f"/ws/realtime/{INCIDENT_ID}?token={token}"
        ) as ws:
            ws.send_text("ping")
        from app.realtime.manager import manager
        assert manager.get_connection_count(INCIDENT_ID) == 0
