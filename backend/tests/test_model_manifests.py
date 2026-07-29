"""Tests for manifest-gated capabilities and model validation (T10, T17).

Verifies the model manifest system end-to-end:
  1. Manifest files exist for all 3 models (sar_flood_mapping, building_damage, incident_nlp)
  2. Validated manifests have validation_status="validated" and signed=true
  3. Capabilities endpoint returns "available" for onnx_models and model_weights
     when all manifests are validated
  4. ML endpoints (flood-map, damage-assessment, nlp-report) return
     model_unavailable WITHOUT reason="placeholder_model_not_validated"
     when manifests are validated but weights are missing
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from app.auth.seed import seed_demo_users
from app.db import SessionLocal
from app.main import app

PASSWORD = "demo1234"
ADMIN_EMAIL = "admin@demo.disaster"

# Path to the manifests file — same calculation as capabilities.py / scenarios.py.
_MANIFEST_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "models", "manifests.json",
)
_MANIFEST_PATH = os.path.normpath(_MANIFEST_PATH)

EXPECTED_MODEL_TYPES = {
    "sar_flood_mapping",
    "building_damage",
    "incident_nlp",
}


@pytest.fixture(scope="module", autouse=True)
def _seed_users() -> None:
    """Seed demo users once for the module."""
    db = SessionLocal()
    seed_demo_users(db)
    db.close()
    yield


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
        json={"title": "Manifest Test Incident", "disaster_type": "flood"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _load_manifests() -> list[dict]:
    """Load and return the manifests JSON array."""
    with open(_MANIFEST_PATH, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data


# ── Manifest file existence ──────────────────────────────────────────────────


def test_manifest_files_exist() -> None:
    """Manifest file exists, is valid JSON, and contains 3 model entries."""
    assert os.path.isfile(_MANIFEST_PATH), (
        f"manifest file not found at {_MANIFEST_PATH}"
    )
    manifests = _load_manifests()
    assert isinstance(manifests, list), (
        f"manifests must be a JSON array, got {type(manifests).__name__}"
    )
    assert len(manifests) == 3, (
        f"expected 3 manifest entries, got {len(manifests)}"
    )
    model_types = {m["model_type"] for m in manifests}
    assert model_types == EXPECTED_MODEL_TYPES, (
        f"missing models: {EXPECTED_MODEL_TYPES - model_types}, "
        f"extra models: {model_types - EXPECTED_MODEL_TYPES}"
    )


# ── Validated manifest status ───────────────────────────────────────────────


def test_validated_manifests_have_correct_status() -> None:
    """All 3 manifests have validation_status='validated' and signed=true."""
    manifests = _load_manifests()
    for entry in manifests:
        model_type = entry.get("model_type", "<unknown>")
        assert entry.get("validation_status") == "validated", (
            f"model {model_type} validation_status="
            f"{entry.get('validation_status')!r}, expected 'validated'"
        )
        assert entry.get("signed") is True, (
            f"model {model_type} signed={entry.get('signed')!r}, expected True"
        )


# ── Capabilities endpoint ────────────────────────────────────────────────────


def test_capabilities_returns_available_with_validated_manifests() -> None:
    """GET /api/capabilities reports onnx_models and model_weights as 'available'.

    With all manifests validated and ONNX weight files on disk, the
    capabilities endpoint must report both ML features as 'available'
    (not 'degraded'), because the manifests are validated and signed.
    """
    with TestClient(app) as client:
        resp = client.get("/api/capabilities")
    assert resp.status_code == 200, resp.text
    features = {f["feature"]: f["status"] for f in resp.json()["features"]}
    assert features["onnx_models"] == "available", (
        f"onnx_models status={features['onnx_models']!r}, expected 'available'"
    )
    assert features["model_weights"] == "available", (
        f"model_weights status={features['model_weights']!r}, expected 'available'"
    )


# ── ML endpoints return model_unavailable when weights missing (not placeholder) ─


def test_ml_endpoints_unavailable_when_weights_missing(degrade_env: None) -> None:
    """ML endpoints return model_unavailable WITHOUT placeholder reason.

    With validated manifests, the placeholder guard does NOT fire. The routes
    fall through to the weights check and return model_unavailable because
    the ONNX files are moved aside by degrade_env. The response must NOT
    contain reason='placeholder_model_not_validated' — that reason only
    appears when manifests are unvalidated placeholders.

    Tests flood-map (GET), damage-assessment (POST), and nlp-report (POST).
    """
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)
        headers = _auth_header(token)

        # flood-map (GET)
        flood_resp = client.get(
            f"/api/incidents/{inc_id}/flood-map",
            headers=headers,
        )
        assert flood_resp.status_code == 200, flood_resp.text
        flood_body = flood_resp.json()
        assert flood_body["status"] == "model_unavailable", (
            f"flood-map status={flood_body.get('status')!r}"
        )
        assert flood_body.get("reason") != "placeholder_model_not_validated", (
            f"flood-map reason={flood_body.get('reason')!r} — "
            "placeholder guard should not fire with validated manifests"
        )

        # damage-assessment (POST)
        damage_resp = client.post(
            f"/api/incidents/{inc_id}/damage-assessment",
            json={"flood_prob": 0.6, "damage_prob": 0.3, "road_class": "primary"},
            headers=headers,
        )
        assert damage_resp.status_code == 200, damage_resp.text
        damage_body = damage_resp.json()
        assert damage_body["status"] == "model_unavailable", (
            f"damage-assessment status={damage_body.get('status')!r}"
        )
        assert damage_body.get("reason") != "placeholder_model_not_validated", (
            f"damage-assessment reason={damage_body.get('reason')!r} — "
            "placeholder guard should not fire with validated manifests"
        )

        # nlp-report (POST)
        nlp_resp = client.post(
            f"/api/incidents/{inc_id}/nlp-report",
            json={"text": "There is severe flooding near the river bank."},
            headers=headers,
        )
        assert nlp_resp.status_code == 200, nlp_resp.text
        nlp_body = nlp_resp.json()
        assert nlp_body["status"] == "model_unavailable", (
            f"nlp-report status={nlp_body.get('status')!r}"
        )
        assert nlp_body.get("reason") != "placeholder_model_not_validated", (
            f"nlp-report reason={nlp_body.get('reason')!r} — "
            "placeholder guard should not fire with validated manifests"
        )
