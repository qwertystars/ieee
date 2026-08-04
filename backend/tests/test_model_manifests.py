"""Tests for manifest-gated capabilities and model validation (T10, T17).

Verifies the model manifest system end-to-end:
  1. Manifest files exist for all 3 models (sar_flood_mapping, building_damage, incident_nlp)
  2. Validated manifests have validation_status="validated" and signed=true
  3. Capabilities endpoint returns "available" for onnx_models and model_weights
     when all manifests are validated
  4. ML endpoints return status="unavailable" with a canonical provenance
     record when manifests are valid but weights are missing
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.auth.seed import seed_demo_users
from app.db import SessionLocal
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.main import app
from app.perception.models import ModelFramework, ModelRecord, ModelTask
from app.perception.serving import (
    ContractState,
    ContractVersions,
    InferenceContractError,
    ModelServing,
    resolve_contract,
)

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


def test_manifest_contracts_pin_versions_and_artifacts() -> None:
    required_versions = {
        "contract_version",
        "model_version",
        "feature_schema_version",
        "preprocessing_version",
        "calibration_version",
        "output_schema_version",
    }
    for entry in _load_manifests():
        contract = entry["contract"]
        assert set(contract) == required_versions
        assert all(
            isinstance(contract[name], str) and contract[name]
            for name in required_versions
        )
        assert entry["model_id"]
        assert entry["artifact"]["sha256"] == entry["checksum"]
        assert len(entry["artifact"]["sha256"]) == 64


@pytest.mark.parametrize(
    "field",
    (
        "contract_version",
        "model_version",
        "feature_schema_version",
        "preprocessing_version",
        "calibration_version",
        "output_schema_version",
    ),
)
def test_contract_resolution_rejects_each_incompatible_version(field: str) -> None:
    resolved = resolve_contract("sar-flood-mapping")
    assert resolved.contract is not None

    versions = resolved.contract.versions
    mismatched = ContractVersions(
        contract_version="9.9.9" if field == "contract_version" else versions.contract_version,
        model_version="9.9.9" if field == "model_version" else versions.model_version,
        feature_schema_version=(
            "9.9.9" if field == "feature_schema_version" else versions.feature_schema_version
        ),
        preprocessing_version=(
            "9.9.9" if field == "preprocessing_version" else versions.preprocessing_version
        ),
        calibration_version=(
            "9.9.9" if field == "calibration_version" else versions.calibration_version
        ),
        output_schema_version=(
            "9.9.9" if field == "output_schema_version" else versions.output_schema_version
        ),
    )
    incompatible = resolve_contract("sar-flood-mapping", mismatched)
    assert incompatible.state is ContractState.incompatible
    assert field in incompatible.reason


def test_uncalibrated_contract_abstains() -> None:
    resolved = resolve_contract("building-damage")
    assert resolved.state is ContractState.abstain
    assert resolved.reason == "calibration_unavailable"


def test_stale_registry_state_fails_closed(tmp_path, monkeypatch) -> None:
    import app.perception.serving as serving_module

    manifest = _load_manifests()
    manifest[0]["version"] = "9.9.9"
    stale_path = tmp_path / "manifests.json"
    stale_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(serving_module, "_MANIFEST_PATH", stale_path)

    resolved = resolve_contract("sar-flood-mapping")
    assert resolved.state is ContractState.unavailable
    assert resolved.reason == "registry_unavailable"


def test_unregistered_model_record_fails_closed() -> None:
    record = ModelRecord(
        id=generate_ulid(),
        org_id="org_contract_test",
        name="legacy-model",
        version="9.9.9",
        framework=ModelFramework.onnx,
        task=ModelTask.flood_mapping,
        r2_key="models/legacy-model.onnx",
        input_schema={},
        output_schema={},
        calibration_metrics={},
        created_at=now_ms(),
    )
    record_id = record.id
    db = SessionLocal()
    try:
        db.add(record)
        db.commit()
    finally:
        db.close()
    serving = ModelServing(SessionLocal)
    with pytest.raises(InferenceContractError) as failure:
        serving.run_inference(record_id, {})
    assert failure.value.resolution.state is ContractState.unavailable
    assert failure.value.resolution.reason == "model_not_registered"


def test_cached_artifact_tamper_invalidates_session(tmp_path, monkeypatch) -> None:
    import app.perception.serving as serving_module

    manifest = _load_manifests()
    entry = manifest[0]
    entry["model_id"] = "cache-test"
    entry["contract"]["calibration_version"] = "2.0.0"
    entry["calibration"]["status"] = "available"
    entry["artifact"]["filename"] = "cache-test.onnx"
    entry["artifact"]["r2_key"] = "models/cache-test.onnx"
    artifact = b"canonical-artifact"
    entry["checksum"] = hashlib.sha256(artifact).hexdigest()
    entry["artifact"]["sha256"] = entry["checksum"]
    manifest_path = tmp_path / "manifests.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    model_path = tmp_path / "models" / "cache-test.onnx"
    model_path.parent.mkdir()
    model_path.write_bytes(artifact)
    monkeypatch.setattr(serving_module, "_MANIFEST_PATH", manifest_path)

    class Session:
        pass

    serving = ModelServing(lambda: None, cache_dir=str(tmp_path))
    serving._create_session = lambda _: Session()
    serving.load_registered_model("cache-test")
    model_path.write_bytes(b"tampered-artifact")
    with pytest.raises(InferenceContractError) as failure:
        serving.load_registered_model("cache-test")
    assert failure.value.resolution.state is ContractState.unavailable
    assert failure.value.resolution.reason == "weights_unavailable"


def test_output_dtype_mismatch_is_incompatible() -> None:
    contract = resolve_contract("sar-flood-mapping").contract
    assert contract is not None

    class Metadata:
        def __init__(self, name: str) -> None:
            self.name = name

    class Session:
        def get_inputs(self):
            return [Metadata("input")]

        def get_outputs(self):
            return [Metadata("output")]

        def run(self, _names, _feeds):
            return [np.empty((1, 2, 512, 512), dtype=np.float64)]

    with pytest.raises(InferenceContractError) as failure:
        ModelServing._run_session(
            Session(),
            {"input": np.empty((1, 2, 512, 512), dtype=np.float32)},
            contract,
        )
    assert failure.value.resolution.reason == "output_dtype_mismatch:output"


def test_downloader_has_no_alternate_nlp_source() -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "download_real_models.py"
    assert "disaster-tweets-bert" not in script.read_text(encoding="utf-8")


def test_malformed_provided_inputs_reject_before_calibration_abstention() -> None:
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        incident_id = _create_incident(client, token)
        headers = _auth_header(token)
        damage = client.post(
            f"/api/incidents/{incident_id}/damage-assessment",
            json={"image_data": [[[[1.0]]]]},
            headers=headers,
        )
        nlp = client.post(
            f"/api/incidents/{incident_id}/nlp-report",
            json={"text": ""},
            headers=headers,
        )
    assert damage.status_code == 422
    assert nlp.status_code == 422


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


def test_ml_endpoints_missing_weights_return_unavailable(degrade_env: None) -> None:
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
        assert flood_body["status"] == "unavailable", (
            f"flood-map status={flood_body.get('status')!r}"
        )
        assert flood_body["reason"] == "weights_unavailable"

        # damage-assessment (POST)
        damage_resp = client.post(
            f"/api/incidents/{inc_id}/damage-assessment",
            json={"flood_prob": 0.6, "damage_prob": 0.3, "road_class": "primary"},
            headers=headers,
        )
        assert damage_resp.status_code == 200, damage_resp.text
        damage_body = damage_resp.json()
        assert damage_body["status"] == "unavailable", (
            f"damage-assessment status={damage_body.get('status')!r}"
        )
        assert damage_body["reason"] == "weights_unavailable"

        # nlp-report (POST)
        nlp_resp = client.post(
            f"/api/incidents/{inc_id}/nlp-report",
            json={"text": "There is severe flooding near the river bank."},
            headers=headers,
        )
        assert nlp_resp.status_code == 200, nlp_resp.text
        nlp_body = nlp_resp.json()
        assert nlp_body["status"] == "unavailable", (
            f"nlp-report status={nlp_body.get('status')!r}"
        )
        assert nlp_body["reason"] == "weights_unavailable"
