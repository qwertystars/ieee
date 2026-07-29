"""Integration test — low-connectivity degraded mode.

Verifies that the platform degrades gracefully when Redis and Kafka/Redpanda
are unavailable (the test environment has neither). The app must:
1. Return None from get_redis() (not crash).
2. Return False from is_token_revoked() (denylist disabled, not crash).
3. Start the FastAPI app without crashing (Kafka producer fails non-fatal).
4. Serve API requests normally (auth, health, observations).

No mocking — we test the real degradation behavior against the real
(unavailable) Redis and Kafka endpoints.
"""

from __future__ import annotations

import socket
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from app.auth.seed import seed_demo_users
from app.config import settings
from app.db import SessionLocal
from app.deps import get_redis, is_token_revoked
from app.main import app
from app.streaming.producer import ProducerManager


def _redis_is_reachable() -> bool:
    """Return True if a TCP connection to the Redis URL host:port succeeds."""
    parsed = urlparse(settings.REDIS_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _redpanda_is_reachable() -> bool:
    """Return True if a TCP connection to the Redpanda bootstrap host:port succeeds."""
    bootstrap = settings.REDPANDA_BOOTSTRAP_SERVERS
    host, _, port = bootstrap.partition(":")
    host = host or "localhost"
    try:
        port_int = int(port) if port else 9092
    except ValueError:
        port_int = 9092
    try:
        with socket.create_connection((host, port_int), timeout=2):
            return True
    except OSError:
        return False

PASSWORD = "demo1234"


@pytest.fixture(scope="module", autouse=True)
def _seed_users() -> None:
    db = SessionLocal()
    seed_demo_users(db)
    db.close()


def test_get_redis_returns_none_when_unavailable() -> None:
    """get_redis() returns None when Redis is unreachable (not an exception)."""
    if _redis_is_reachable():
        pytest.skip("Redis is running — cannot test unavailability")
    # Reset the cached client so it tries to reconnect.
    import app.deps as deps_module
    deps_module._redis_client = None

    result = get_redis()
    assert result is None, (
        f"expected None when Redis is down, got {type(result)}"
    )


def test_is_token_revoked_returns_false_when_redis_down() -> None:
    """is_token_revoked() returns False when Redis is unavailable.

    The denylist is disabled — tokens are assumed valid (fail-open).
    """
    import app.deps as deps_module
    deps_module._redis_client = None

    assert is_token_revoked("any.token.here") is False


def test_app_starts_without_kafka() -> None:
    """The FastAPI app starts and serves requests even when Kafka is down."""
    with TestClient(app) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True


def test_login_works_without_redis_or_kafka() -> None:
    """Login succeeds even when Redis and Kafka are unavailable."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/auth/login",
            data={
                "username": "admin@demo.disaster",
                "password": PASSWORD,
            },
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()


def test_protected_endpoint_works_without_redis() -> None:
    """A protected endpoint (GET /api/auth/me) works without Redis."""
    with TestClient(app) as client:
        login_resp = client.post(
            "/api/auth/login",
            data={
                "username": "admin@demo.disaster",
                "password": PASSWORD,
            },
        )
        token = login_resp.json()["access_token"]

        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "admin@demo.disaster"
        assert body["role"] == "admin"


def test_producer_manager_fails_gracefully() -> None:
    """ProducerManager.start() raises when Kafka is down.

    The caller (lifespan, simulator) is expected to catch this and continue.
    """
    import asyncio

    producer = ProducerManager(bootstrap_servers="localhost:9092")
    assert producer.is_started is False

    with pytest.raises((ConnectionError, RuntimeError, OSError)):
        asyncio.run(producer.start())


def test_deep_health_check_reports_redis_and_redpanda_down() -> None:
    """Deep health check reports redis=False and redpanda=False when down.

    Adaptive: when Redis/Redpanda are actually running (e.g. Docker stack up),
    we skip the corresponding down-assertions instead of asserting False.
    The database is always expected to be up in the test environment.
    """
    with TestClient(app) as client:
        resp = client.get("/healthz/deep")
        assert resp.status_code == 200
        body = resp.json()
        checks = body["checks"]
        assert checks["database"] is True, "database should be up"

        if _redis_is_reachable():
            assert checks["redis"] is True, (
                "redis is reachable — should report True"
            )
        else:
            assert checks["redis"] is False, "redis should be down"

        if _redpanda_is_reachable():
            assert checks["redpanda"] is True, (
                "redpanda is reachable — should report True"
            )
        else:
            assert checks["redpanda"] is False, "redpanda should be down"
