"""Integration tests — refresh token hardening (T37).

Verifies that login returns both an access token (15 min) and a refresh
token (7 day), that POST /api/auth/refresh exchanges a refresh token for
a new access token, and that the existing login flow still works.

Uses the real PostgreSQL database and the real FastAPI app via TestClient.
Demo users are seeded directly via seed_demo_users(). No source files mocked.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.auth.seed import seed_demo_users
from app.db import SessionLocal
from app.main import app

PASSWORD = "demo1234"
ADMIN_EMAIL = "admin@demo.disaster"


@pytest.fixture(scope="module", autouse=True)
def _seed_users() -> None:
    db = SessionLocal()
    seed_demo_users(db)
    db.close()


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
