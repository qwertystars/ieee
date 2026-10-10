"""Task 9 regression tests for production settings and identity claims."""

from datetime import timedelta

import pytest

from app.auth.jwt import (
    create_access_token,
    create_device_access_token,
    create_service_access_token,
    decode_token,
)
from app.config import Settings

SAFE_PRODUCTION = {
    "ENVIRONMENT": "production",
    "DATABASE_URL": "postgresql+psycopg://resqnet_app:unique-db-secret@db:5432/disaster",
    "JWT_SECRET": "production-signing-secret-with-more-than-32-characters",
    "CORS_ORIGINS": "https://console.example.org",
    "MINIO_ACCESS_KEY": "resqnet-app",
    "MINIO_SECRET_KEY": "unique-minio-secret",
}


def test_production_settings_reject_each_unsafe_control() -> None:
    """Given one unsafe production control, When settings load, Then startup rejects it by name."""
    controls = {
        "JWT_SECRET": "dev-secret-change-me",
        "CORS_ORIGINS": "*",
        "UVICORN_RELOAD": True,
        "SOURCE_MOUNTS_ENABLED": True,
        "MOCK_BINDINGS_ENABLED": True,
        "EXPOSE_INTERNAL_PORTS": True,
        "REDIS_REVOCATION_REQUIRED": False,
        "REFRESH_TOKEN_ROTATION_REQUIRED": False,
        "ACCESS_TOKEN_EXPIRE_MINUTES": 720,
        "DATABASE_URL": "postgresql+psycopg://disaster:disaster@db:5432/disaster",
        "MINIO_SECRET_KEY": "minio123",
    }
    for name, value in controls.items():
        with pytest.raises(ValueError, match=name):
            values = {**SAFE_PRODUCTION, name: value}
            Settings(_env_file=None, **values)


def test_production_settings_error_does_not_echo_secret() -> None:
    """Given an unsafe secret, When settings fail, Then the secret is absent from diagnostics."""
    secret = "unique-production-secret-that-must-not-appear"
    with pytest.raises(ValueError) as caught:
        values = {
            **SAFE_PRODUCTION,
            "JWT_SECRET": secret,
            "CORS_ORIGINS": "*",
        }
        Settings(
            _env_file=None,
            **values,
        )
    assert secret not in str(caught.value)


def test_identity_tokens_have_distinct_principal_claims() -> None:
    """Given human, device, and service issuers, When tokens are created, Then claims stay distinct."""
    human = decode_token(
        create_access_token(
            {"sub": "human@example.org", "org_id": "org-a", "role": "admin"},
            timedelta(minutes=15),
        )
    )
    device = decode_token(
        create_device_access_token("device-a", "org-a", ("edge:ingest",))
    )
    service = decode_token(
        create_service_access_token("worker-a", "org-a", ("jobs:consume",))
    )

    assert human["principal_type"] == "human"
    assert human["aud"] == "resqnet-api"
    assert human["scope"] == "api:read api:write"
    assert device["principal_type"] == "device"
    assert device["aud"] == "resqnet-device"
    assert device["scope"] == "edge:ingest"
    assert service["principal_type"] == "service"
    assert service["aud"] == "resqnet-service"
    assert service["scope"] == "jobs:consume"
