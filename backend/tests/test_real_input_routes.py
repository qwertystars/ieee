"""Todo 15 route tests using committed SAR input and explicit degradation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.enums import Resampling
from rasterio.windows import Window

import app.api.routes.scenarios as scenarios_routes
from app.auth.seed import seed_demo_users
from app.db import SessionLocal
from app.main import app
from app.perception.ensemble import GFMMember
from app.perception.serving import ContractResolution, ContractState

_PASSWORD = "demo1234"
_ADMIN_EMAIL = "admin@demo.disaster"
_SAR_FIXTURE = Path(__file__).resolve().parents[1] / "data" / "sample-sar" / "sample.tif"


@pytest.fixture(scope="module", autouse=True)
def _seed_users() -> None:
    db = SessionLocal()
    try:
        seed_demo_users(db)
    finally:
        db.close()


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/auth/login",
        data={"username": _ADMIN_EMAIL, "password": _PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _incident(client: TestClient, token: str) -> str:
    response = client.post(
        "/api/incidents",
        json={"title": "Real input route test", "disaster_type": "flood"},
        headers=_auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _sar_payload() -> dict[str, Any]:
    with rasterio.open(_SAR_FIXTURE) as source:
        window = Window(100, 100, 512, 512)
        bands = source.read(
            indexes=(1, 2),
            window=window,
            out_shape=(2, 512, 512),
            resampling=Resampling.bilinear,
        )
        masks = source.read_masks(
            indexes=(1, 2),
            window=window,
            out_shape=(2, 512, 512),
            resampling=Resampling.nearest,
        )
        tensor = np.asarray(bands, dtype=np.float32)[np.newaxis, ...]
        resolution_m = float(max(source.res))
        crs = str(source.crs)
    valid_fraction = float((masks > 0).all(axis=0).mean())
    nodata_fraction = 1.0 - valid_fraction
    snr_db = float(20.0 * np.log10(float(tensor.mean()) / float(tensor.std())))
    return {
        "input_data": tensor.tolist(),
        "crs": crs,
        "resolution_m": resolution_m,
        "quality": {
            "valid_fraction": valid_fraction,
            "nodata_fraction": nodata_fraction,
            "snr_db": snr_db,
        },
    }


def test_sar_real_input_abstains_without_onnx_calibration() -> None:
    with TestClient(app) as client:
        token = _login(client)
        incident_id = _incident(client, token)
        response = client.post(
            f"/api/incidents/{incident_id}/flood-map",
            json=_sar_payload(),
            headers=_auth_header(token),
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "abstain"
    assert body["review_status"] == "draft"
    assert body["reason"] == "calibration_unavailable"
    assert "prediction" not in body
    provenance = body["provenance"]
    assert provenance["model_id"] == "sar-flood-mapping"
    assert provenance["model_version"] == "2.0.0"
    assert provenance["feature_schema_version"] == "2.0.0"
    assert provenance["preprocessing_version"] == "2.0.0"
    assert provenance["calibration_version"] == "unavailable"
    assert provenance["output_schema_version"] == "2.0.0"
    assert provenance["state"] == "abstain"


def test_damage_and_nlp_report_explicit_degradation() -> None:
    with TestClient(app) as client:
        token = _login(client)
        incident_id = _incident(client, token)
        damage = client.post(
            f"/api/incidents/{incident_id}/damage-assessment",
            json={},
            headers=_auth_header(token),
        )
        nlp = client.post(
            f"/api/incidents/{incident_id}/nlp-report",
            json={"text": "Water is rising near the shelter."},
            headers=_auth_header(token),
        )

    assert damage.status_code == 200, damage.text
    assert damage.json()["status"] in {"abstain", "unavailable"}
    assert damage.json()["review_status"] == "draft"
    assert nlp.status_code == 200, nlp.text
    assert nlp.json()["status"] in {"abstain", "unavailable"}
    assert nlp.json()["review_status"] == "draft"


def test_sar_missing_weights_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scenarios_routes,
        "_route_resolution",
        lambda _model_id, _requested=None: ContractResolution(
            ContractState.unavailable,
            None,
            "weights_unavailable",
        ),
    )
    with TestClient(app) as client:
        token = _login(client)
        incident_id = _incident(client, token)
        response = client.post(
            f"/api/incidents/{incident_id}/flood-map",
            json=_sar_payload(),
            headers=_auth_header(token),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["reason"] == "weights_unavailable"
    assert "prediction" not in body


def test_sar_low_quality_input_abstains() -> None:
    payload = _sar_payload()
    quality = payload["quality"]
    assert isinstance(quality, dict)
    quality["valid_fraction"] = 0.4
    with TestClient(app) as client:
        token = _login(client)
        incident_id = _incident(client, token)
        response = client.post(
            f"/api/incidents/{incident_id}/flood-map",
            json=payload,
            headers=_auth_header(token),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "abstain"
    assert body["reason"] == "input_quality_low"
    assert "prediction" not in body


def test_malformed_sar_payload_is_rejected() -> None:
    payload = _sar_payload()
    payload["input_data"] = [[[1.0]]]
    with TestClient(app) as client:
        token = _login(client)
        incident_id = _incident(client, token)
        response = client.post(
            f"/api/incidents/{incident_id}/flood-map",
            json=payload,
            headers=_auth_header(token),
        )

    assert response.status_code == 422


def test_ensemble_rejects_constant_external_member_without_provenance() -> None:
    with pytest.raises(ValueError, match="real raster|provenance"):
        GFMMember({"flood_prob": 0.5})


def test_ensemble_get_without_real_members_abstains() -> None:
    with TestClient(app) as client:
        token = _login(client)
        incident_id = _incident(client, token)
        response = client.get(
            f"/api/incidents/{incident_id}/flood-ensemble",
            headers=_auth_header(token),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"abstain", "unavailable"}
    assert body["review_status"] == "draft"
