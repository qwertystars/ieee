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

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

import app.deps as deps_module
from app.auth.seed import seed_demo_users
from app.db import SessionLocal
from app.deps import revoke_token
from app.main import app
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.models.incident import Incident
from app.models.observation import Observation

PASSWORD = "demo1234"
ORG_ID = "org_demo"
INCIDENT_ID = "inc_ws_fallback_test"


@pytest.fixture(scope="module", autouse=True)
def _seed_users() -> None:
    db = SessionLocal()
    seed_demo_users(db)
    if db.query(Incident).filter(Incident.id == INCIDENT_ID).first() is None:
        db.add(
            Incident(
                id=INCIDENT_ID,
                org_id=ORG_ID,
                title="WebSocket fallback test",
                disaster_type="flood",
                severity="moderate",
                status="active",
                start_time=1_700_000_000_000,
                created_at=1_700_000_000_000,
                updated_at=1_700_000_000_000,
            )
        )
        db.commit()
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


def _insert_observation(
    db,
    obs_id: str,
    observed_at: int,
    access_policy: AccessPolicy = AccessPolicy.public,
) -> None:
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
            access_policy=access_policy,
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


def test_polling_requires_authentication(db) -> None:
    """Given no bearer token, When polling, Then the endpoint returns 401."""
    with TestClient(app) as client:
        resp = client.get(f"/api/incidents/{INCIDENT_ID}/updates?since=0")
    assert resp.status_code == 401


def test_polling_denies_new_token_when_redis_is_unavailable(db) -> None:
    """Given auth state is unavailable, When polling, Then access fails closed."""
    with TestClient(app) as client:
        token = _login(client, "admin@demo.disaster")
        with patch.object(deps_module, "get_redis", return_value=None):
            resp = client.get(
                f"/api/incidents/{INCIDENT_ID}/updates?since=0",
                headers={"Authorization": f"Bearer {token}"},
            )
    assert resp.status_code == 401


def test_polling_filters_sensitive_records_for_viewer(db) -> None:
    """Given public and sensitive rows, When a viewer polls, Then only public data is returned."""
    base_ts = 1_700_000_200_000
    _insert_observation(db, "01J9TESTPUBLIC001", base_ts + 1000)
    _insert_observation(
        db,
        "01J9TESTSENSIT001",
        base_ts + 2000,
        access_policy=AccessPolicy.sensitive,
    )

    with TestClient(app) as client:
        token = _login(client, "viewer@demo.disaster")
        resp = client.get(
            f"/api/incidents/{INCIDENT_ID}/updates?since={base_ts}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    observations = resp.json()["observations"]
    ids = {observation["observation_id"] for observation in observations}
    assert "01J9TESTPUBLIC001" in ids
    assert "01J9TESTSENSIT001" not in ids
    assert all(observation["access_policy"] == "public" for observation in observations)
    assert all("raw_data_hash" not in observation for observation in observations)


def test_websocket_rejects_invalid_token() -> None:
    """Given an invalid JWT, When connecting, Then the stream closes with 4401."""
    from starlette.websockets import WebSocketDisconnect

    with TestClient(app) as client:
        with client.websocket_connect(
            f"/ws/realtime/{INCIDENT_ID}?token=invalid.jwt.token"
        ) as websocket:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                websocket.receive_text()
            assert exc_info.value.code == 4401


def test_websocket_rejects_missing_token() -> None:
    """Given no token, When connecting, Then the stream closes with 4401."""
    from starlette.websockets import WebSocketDisconnect

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/realtime/{INCIDENT_ID}") as websocket:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                websocket.receive_text()
            assert exc_info.value.code == 4401


def test_websocket_rejects_revoked_token() -> None:
    """Given a revoked JWT, When connecting, Then the stream closes with 4401."""
    from starlette.websockets import WebSocketDisconnect

    with TestClient(app) as client:
        token = _login(client, "admin@demo.disaster")
        with patch.object(deps_module, "get_redis", return_value=None):
            revoke_token(token, 3600)
            with client.websocket_connect(
                f"/ws/realtime/{INCIDENT_ID}?token={token}"
            ) as websocket:
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    websocket.receive_text()
                assert exc_info.value.code == 4401


def test_existing_websocket_closes_after_revocation() -> None:
    """Given an active stream, When its JWT is revoked, Then it closes with 4401."""
    from starlette.websockets import WebSocketDisconnect

    with TestClient(app) as client:
        token = _login(client, "admin@demo.disaster")
        with client.websocket_connect(
            f"/ws/realtime/{INCIDENT_ID}?token={token}"
        ) as ws:
            db = SessionLocal()
            try:
                revoke_token(token, 3600, db=db, org_id="org_demo")
            finally:
                db.close()
            ws.send_text("recheck-auth")
            with pytest.raises(WebSocketDisconnect) as exc_info:
                ws.receive_text()
    assert exc_info.value.code == 4401


def test_websocket_accepts_valid_token() -> None:
    """Given a valid JWT and incident membership, Then the stream is accepted."""
    with TestClient(app) as client:
        token = _login(client, "admin@demo.disaster")
        with client.websocket_connect(
            f"/ws/realtime/{INCIDENT_ID}?token={token}"
        ) as ws:
            ws.send_text("ping")
        from app.realtime.manager import manager
        assert manager.get_connection_count(INCIDENT_ID) == 0
