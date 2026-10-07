"""Integration tests — production user provisioning CLI (app.auth.create_user).

Runs against the real PostgreSQL database and logs in through the real app.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.create_user import PASSWORD_ENV, main, upsert_user
from app.auth.passwords import verify_password
from app.db import SessionLocal
from app.lib.ulid import generate_ulid
from app.models.user import User

PASSWORD = "provisioned-pass-123"


def _email() -> str:
    return f"ops-{generate_ulid().lower()}@example.org"


def test_upsert_creates_then_updates_user() -> None:
    email = _email()
    db = SessionLocal()
    try:
        assert upsert_user(db, email=email, role="admin", org_id="org_a", password=PASSWORD)
        assert not upsert_user(
            db, email=email, role="viewer", org_id="org_b", password=PASSWORD + "x"
        )
        user = db.query(User).filter(User.email == email).one()
        assert (user.role, user.org_id) == ("viewer", "org_b")
        assert verify_password(PASSWORD + "x", user.hashed_password)
        assert len(user.id) == 26
    finally:
        db.close()


@pytest.mark.parametrize(
    ("role", "password", "message"),
    [("superuser", PASSWORD, "role"), ("admin", "short", "password")],
)
def test_upsert_rejects_invalid_input(role: str, password: str, message: str) -> None:
    db = SessionLocal()
    try:
        with pytest.raises(ValueError, match=message):
            upsert_user(db, email=_email(), role=role, org_id="org_a", password=password)
    finally:
        db.close()


def test_cli_user_can_log_in(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    email = _email()
    monkeypatch.setenv(PASSWORD_ENV, PASSWORD)
    assert main(["--email", email, "--role", "emergency_manager", "--org-id", "org_cli"]) == 0

    response = client.post("/api/auth/login", data={"username": email, "password": PASSWORD})
    assert response.status_code == 200
    token = response.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert (me["role"], me["org_id"]) == ("emergency_manager", "org_cli")
