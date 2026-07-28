"""Integration test — calibration-validation harness (T8).

Verifies the full fit → intervals → metrics round-trip through the API:
  1. POST /api/incidents/{id}/calibration/data stores fixture samples → 201
  2. POST /api/incidents/{id}/calibration/fit fits ConformalCalibrator → 200
  3. Response includes prediction intervals + Brier/ECE/coverage metrics
  4. Conformal coverage is within [0.85, 0.95] for alpha=0.1

Uses the real PostgreSQL database, real FastAPI app via TestClient, and
demo users seeded by seed_demo_users(). Follows the test_role_denial.py
pattern for auth + incident creation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.seed import seed_demo_users
from app.db import SessionLocal
from app.main import app

PASSWORD = "demo1234"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "calibration_samples.json"


@pytest.fixture(scope="module", autouse=True)
def _seed_users() -> None:
    db = SessionLocal()
    seed_demo_users(db)
    db.close()


def _login(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/auth/login",
        data={"username": email, "password": PASSWORD},
    )
    assert resp.status_code == 200, f"login failed for {email}: {resp.text}"
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _load_fixture() -> dict:
    with open(FIXTURE_PATH) as f:
        return json.load(f)


def test_store_calibration_data_returns_201() -> None:
    """POST /api/incidents/{id}/calibration/data stores samples → 201."""
    with TestClient(app) as client:
        admin_token = _login(client, "admin@demo.disaster")
        inc_resp = client.post(
            "/api/incidents",
            json={"title": "Calibration Test", "disaster_type": "flood"},
            headers=_auth_header(admin_token),
        )
        assert inc_resp.status_code == 201
        incident_id = inc_resp.json()["id"]

        fixture = _load_fixture()
        resp = client.post(
            f"/api/incidents/{incident_id}/calibration/data",
            json=fixture,
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 201, f"store failed: {resp.text}"
        body = resp.json()
        assert body["stored"] == len(fixture["samples"])
        assert body["incident_id"] == incident_id
        assert body["model_id"] == fixture["model_id"]


def test_fit_calibration_returns_intervals_and_metrics() -> None:
    """POST /api/incidents/{id}/calibration/fit → 200 with intervals + metrics."""
    with TestClient(app) as client:
        admin_token = _login(client, "admin@demo.disaster")
        inc_resp = client.post(
            "/api/incidents",
            json={"title": "Calibration Fit Test", "disaster_type": "flood"},
            headers=_auth_header(admin_token),
        )
        assert inc_resp.status_code == 201
        incident_id = inc_resp.json()["id"]

        fixture = _load_fixture()
        store_resp = client.post(
            f"/api/incidents/{incident_id}/calibration/data",
            json=fixture,
            headers=_auth_header(admin_token),
        )
        assert store_resp.status_code == 201

        fit_resp = client.post(
            f"/api/incidents/{incident_id}/calibration/fit",
            json={"alpha": 0.1},
            headers=_auth_header(admin_token),
        )
        assert fit_resp.status_code == 200, f"fit failed: {fit_resp.text}"
        body = fit_resp.json()
        assert body["alpha"] == 0.1
        assert body["n_samples"] == len(fixture["samples"])
        assert body["n_fit"] > 0
        assert body["n_predict"] > 0

        intervals = body["intervals"]
        for key in ("prediction", "interval_lower", "interval_upper", "interval_width"):
            assert key in intervals, f"missing interval key: {key}"
            assert len(intervals[key]) == body["n_predict"]

        metrics = body["metrics"]
        for key in ("conformal_coverage", "interval_width", "brier_score", "ece"):
            assert key in metrics, f"missing metric: {key}"


def test_fit_coverage_within_target_range() -> None:
    """Conformal coverage is within [0.85, 0.95] for alpha=0.1."""
    with TestClient(app) as client:
        admin_token = _login(client, "admin@demo.disaster")
        inc_resp = client.post(
            "/api/incidents",
            json={"title": "Calibration Coverage Test", "disaster_type": "flood"},
            headers=_auth_header(admin_token),
        )
        assert inc_resp.status_code == 201
        incident_id = inc_resp.json()["id"]

        fixture = _load_fixture()
        client.post(
            f"/api/incidents/{incident_id}/calibration/data",
            json=fixture,
            headers=_auth_header(admin_token),
        )

        fit_resp = client.post(
            f"/api/incidents/{incident_id}/calibration/fit",
            json={"alpha": 0.1},
            headers=_auth_header(admin_token),
        )
        assert fit_resp.status_code == 200
        coverage = fit_resp.json()["metrics"]["conformal_coverage"]
        assert 0.85 <= coverage <= 0.95, (
            f"coverage {coverage} outside [0.85, 0.95] for alpha=0.1"
        )


def test_fit_requires_minimum_samples() -> None:
    """POST /fit with fewer than 10 samples → 422."""
    with TestClient(app) as client:
        admin_token = _login(client, "admin@demo.disaster")
        inc_resp = client.post(
            "/api/incidents",
            json={"title": "Calibration Min Test", "disaster_type": "flood"},
            headers=_auth_header(admin_token),
        )
        assert inc_resp.status_code == 201
        incident_id = inc_resp.json()["id"]

        small_payload = {
            "model_id": "test_small",
            "samples": [
                {"X": [1.0, 2.0, 3.0], "y": 0.5},
                {"X": [4.0, 5.0, 6.0], "y": 1.2},
                {"X": [7.0, 8.0, 9.0], "y": 2.1},
            ],
        }
        store_resp = client.post(
            f"/api/incidents/{incident_id}/calibration/data",
            json=small_payload,
            headers=_auth_header(admin_token),
        )
        assert store_resp.status_code == 201

        fit_resp = client.post(
            f"/api/incidents/{incident_id}/calibration/fit",
            json={"alpha": 0.1},
            headers=_auth_header(admin_token),
        )
        assert fit_resp.status_code == 422


def test_store_data_requires_auth() -> None:
    """POST /calibration/data without auth → 401."""
    with TestClient(app) as client:
        admin_token = _login(client, "admin@demo.disaster")
        inc_resp = client.post(
            "/api/incidents",
            json={"title": "Auth Test", "disaster_type": "flood"},
            headers=_auth_header(admin_token),
        )
        incident_id = inc_resp.json()["id"]

        fixture = _load_fixture()
        resp = client.post(
            f"/api/incidents/{incident_id}/calibration/data",
            json=fixture,
        )
        assert resp.status_code == 401


def test_store_data_validates_model_id() -> None:
    """POST /calibration/data without model_id → 422."""
    with TestClient(app) as client:
        admin_token = _login(client, "admin@demo.disaster")
        inc_resp = client.post(
            "/api/incidents",
            json={"title": "Validation Test", "disaster_type": "flood"},
            headers=_auth_header(admin_token),
        )
        incident_id = inc_resp.json()["id"]

        fixture = _load_fixture()
        del fixture["model_id"]
        resp = client.post(
            f"/api/incidents/{incident_id}/calibration/data",
            json=fixture,
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 422
