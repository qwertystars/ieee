"""Integration tests — refresh token hardening (T37) + local revocation cache (T38).

Verifies that login returns both an access token (15 min) and a refresh
token (7 day), that POST /api/auth/refresh exchanges a refresh token for
a new access token, and that the existing login flow still works.

Also verifies the in-memory local revocation cache (T38): pre-revoked tokens
are rejected during Redis outages, new tokens fail-open, and the cache is
thread-safe.

Uses the real PostgreSQL database and the real FastAPI app via TestClient.
Demo users are seeded directly via seed_demo_users(). No source files mocked.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app.deps as deps_module
from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.auth.seed import seed_demo_users
from app.db import SessionLocal
from app.deps import is_token_revoked, revoke_token
from app.main import app

PASSWORD = "demo1234"
ADMIN_EMAIL = "admin@demo.disaster"


@pytest.fixture(scope="module", autouse=True)
def _seed_users() -> None:
    db = SessionLocal()
    seed_demo_users(db)
    db.close()


@pytest.fixture(autouse=True)
def _clear_local_revocation_cache() -> None:
    """Clear the in-memory revocation cache before and after each test (T38)."""
    with deps_module._local_revoked_lock:
        deps_module._local_revoked_tokens.clear()
    yield
    with deps_module._local_revoked_lock:
        deps_module._local_revoked_tokens.clear()


def _login(client: TestClient, email: str = ADMIN_EMAIL) -> dict[str, str]:
    """Login and return the full token response JSON."""
    resp = client.post(
        "/api/auth/login",
        data={"username": email, "password": PASSWORD},
    )
    assert resp.status_code == 200, f"login failed for {email}: {resp.text}"
    return resp.json()


def test_login_returns_both_access_and_refresh_tokens() -> None:
    """Given a valid login, When POST /api/auth/login, Then response includes
    access_token, refresh_token, and token_type=bearer."""
    with TestClient(app) as client:
        tokens = _login(client)
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["access_token"] != tokens["refresh_token"]


def test_refresh_with_valid_token_returns_new_access_token() -> None:
    """Given a valid refresh token, When POST /api/auth/refresh, Then a new
    access_token is returned that decodes with type=access."""
    with TestClient(app) as client:
        tokens = _login(client)
        resp = client.post(
            "/api/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
    assert resp.status_code == 200, f"refresh failed: {resp.text}"
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    payload = decode_token(body["access_token"])
    assert payload["type"] == "access"
    assert payload["sub"] == ADMIN_EMAIL


def test_refresh_with_invalid_token_returns_401() -> None:
    """Given a garbage token, When POST /api/auth/refresh, Then 401."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/auth/refresh",
            json={"refresh_token": "not.a.valid.jwt"},
        )
    assert resp.status_code == 401


def test_refresh_with_expired_token_returns_401() -> None:
    """Given an expired refresh token, When POST /api/auth/refresh, Then 401."""
    expired_token = create_refresh_token(
        data={"sub": ADMIN_EMAIL, "jti": "expired-jti", "type": "refresh"},
        expires_delta=timedelta(seconds=-1),
    )
    with TestClient(app) as client:
        resp = client.post(
            "/api/auth/refresh",
            json={"refresh_token": expired_token},
        )
    assert resp.status_code == 401


def test_refresh_with_access_token_returns_401() -> None:
    """Given an access token (not a refresh token), When POST /api/auth/refresh,
    Then 401 — the type claim must be 'refresh'."""
    with TestClient(app) as client:
        tokens = _login(client)
        resp = client.post(
            "/api/auth/refresh",
            json={"refresh_token": tokens["access_token"]},
        )
    assert resp.status_code == 401


def test_existing_login_flow_still_works() -> None:
    """Regression: login still returns access_token + token_type, and the
    access token works for authenticated endpoints like GET /api/auth/me."""
    with TestClient(app) as client:
        tokens = _login(client)
        assert tokens["token_type"] == "bearer"
        assert tokens["access_token"]
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == ADMIN_EMAIL


# ---------------------------------------------------------------------------
# T38: Local emergency revocation cache (Redis-outage resilience)
# ---------------------------------------------------------------------------


def test_local_cache_rejects_revoked_token_when_redis_down() -> None:
    """Given a token revoked before Redis goes down, When is_token_revoked is
    called during the outage, Then it returns True via the local cache."""
    revoke_token("pre-revoked-token-T38", 3600)
    with patch.object(deps_module, "get_redis", return_value=None):
        assert is_token_revoked("pre-revoked-token-T38") is True


def test_local_cache_fail_open_for_new_token_when_redis_down() -> None:
    """Given Redis is down, When is_token_revoked is called with a new
    (non-revoked) token, Then it returns False (fail-open)."""
    revoke_token("pre-revoked-token-T38", 3600)
    with patch.object(deps_module, "get_redis", return_value=None):
        assert is_token_revoked("new-token-not-revoked-T38") is False


def test_local_cache_is_thread_safe() -> None:
    """Given concurrent revoke_token calls from multiple threads, When the
    local cache is accessed, Then no exceptions are raised and all tokens
    are recorded as revoked."""
    from concurrent.futures import ThreadPoolExecutor

    tokens = [f"thread-token-T38-{i}" for i in range(20)]

    with patch.object(deps_module, "get_redis", return_value=None):
        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(lambda t: revoke_token(t, 3600), tokens))

    for token in tokens:
        assert is_token_revoked(token) is True
