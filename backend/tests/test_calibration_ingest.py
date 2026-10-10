"""Integration test — sensor telemetry ingest through calibration pipeline.

Verifies the Wave 4 wiring: mock-sensor telemetry from a SensorSource is
converted to calibration samples, ingested via the calibration API route,
stored in the calibration_data table, and fit by ConformalCalibrator to
produce prediction intervals + metrics.

Pipeline:
  1. CalibrationSensorSource (implements SensorSource protocol) produces
     deterministic real-format water-level telemetry
  2. telemetry_to_samples() converts each reading to {X, y} calibration
     format — X = [value, lat, lon], y = ground-truth flood depth
  3. POST /api/incidents/{id}/calibration/data stores samples -> 201
  4. POST /api/incidents/{id}/calibration/fit fits ConformalCalibrator
     -> 200 with intervals + Brier/ECE/coverage metrics
  5. Coverage is within a reasonable range for alpha=0.1

Follows the test_calibration_harness.py pattern (TestClient, admin auth,
incident creation). The SensorSource protocol compliance reuses the
pattern from test_sensor_source.py.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.seed import seed_demo_users
from app.db import SessionLocal
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.main import app
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.sensing.sensor_source import SensorSource, build_sensor_provenance

PASSWORD = "demo1234"
ORG_ID = "org_calib_ingest"
INCIDENT_ID = "inc_calib_ingest"
DEVICE_ID = "calib-sensor-001"
N_SAMPLES = 50


class CalibrationSensorSource:
    """Deterministic SensorSource producing water-level telemetry for calibration.

    Implements the SensorSource protocol. Each read_telemetry() call returns
    the next sample from a fixed deterministic list of N_SAMPLES readings.
    The telemetry is real-format (provenance_chain without simulated: True)
    and carries value, lat, lon — the fields needed to construct calibration
    samples.
    """

    def __init__(self) -> None:
        self._device_id = DEVICE_ID
        self._org_id = ORG_ID
        self._incident_id = INCIDENT_ID
        self._samples = self._build_samples()
        self._index = 0

    @staticmethod
    def _build_samples() -> list[dict[str, Any]]:
        """Produce N_SAMPLES deterministic water-level readings.

        Values follow a deterministic pattern (no RNG) so the test is
        reproducible: water_level varies from 0.5m to 3.0m across a
        grid of lat/lon coordinates in Rivertown.
        """
        samples: list[dict[str, Any]] = []
        for i in range(N_SAMPLES):
            value = 0.5 + (i * 2.5 / N_SAMPLES)
            lat = 40.70 + (i * 0.01)
            lon = -73.99 - (i * 0.01)
            samples.append(
                {
                    "phenomenon": "water_level",
                    "value": round(value, 4),
                    "unit": "m",
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                }
            )
        return samples

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def org_id(self) -> str:
        return self._org_id

    @property
    def incident_id(self) -> str:
        return self._incident_id

    def read_telemetry(self) -> dict[str, Any]:
        if self._index >= len(self._samples):
            raise StopIteration("No more telemetry samples")
        raw = self._samples[self._index]
        self._index += 1
        return self._normalize(raw)

    def _normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        observed_at = now_ms()
        geometry = {
            "type": "Point",
            "coordinates": [raw["lon"], raw["lat"]],
        }
        raw_for_hash = json.dumps(raw, sort_keys=True, default=str)
        return {
            "observation_id": generate_ulid(),
            "event_type": "sensor_reading",
            "phenomenon": raw["phenomenon"],
            "value": float(raw["value"]),
            "unit": raw["unit"],
            "geometry": geometry,
            "geometry_uncertainty": 0.0,
            "observed_at": observed_at,
            "valid_from": observed_at,
            "valid_until": None,
            "received_at": now_ms(),
            "source_id": f"mock:{self._device_id}",
            "source_type": SourceType.sensor.value,
            "collection_method": "mock_sensor",
            "source_reliability": 0.9,
            "freshness": 1.0,
            "corroboration_state": CorroborationState.uncorroborated.value,
            "model_uncertainty": None,
            "quality_flags": {"calibration": True},
            "access_policy": AccessPolicy.internal.value,
            "provenance_chain": build_sensor_provenance(
                "mock",
                self._device_id,
                sample_index=self._index - 1,
            ),
            "raw_data_hash": "sha256:" + hashlib.sha256(
                raw_for_hash.encode("utf-8")
            ).hexdigest(),
            "model_version": None,
            "supersedes": None,
            "duplicate_group": None,
            "org_id": self._org_id,
            "incident_id": self._incident_id,
        }


def telemetry_to_calibration_samples(
    source: CalibrationSensorSource,
) -> list[dict[str, Any]]:
    """Convert sensor telemetry into calibration samples ({X, y} format).

    Reads all available telemetry from the SensorSource and maps each
    reading to a calibration sample:
      X = [water_level, lat, lon]  — features for the regression model
      y = ground-truth flood depth  — deterministic linear function of
          the features plus small deterministic noise

    The y target is a linear function of X so that LinearRegression (the
    ConformalCalibrator's default estimator) can fit it well, leaving
    conformal residuals that produce meaningful prediction intervals.
    """
    samples: list[dict[str, Any]] = []
    while True:
        try:
            tel = source.read_telemetry()
        except StopIteration:
            break
        value = tel["value"]
        coords = tel["geometry"]["coordinates"]
        lon, lat = coords[0], coords[1]
        X = [value, lat, lon]
        # Deterministic ground-truth: linear in features + small noise
        noise = 0.05 * ((len(samples) % 7) - 3)
        y = 1.5 * value + 0.1 * lat + 0.05 * lon + noise
        samples.append({"X": X, "y": round(y, 6)})
    return samples


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


def test_sensor_source_protocol_compliance() -> None:
    """CalibrationSensorSource satisfies the SensorSource protocol."""
    source = CalibrationSensorSource()
    assert isinstance(source, SensorSource)
    assert source.device_id == DEVICE_ID
    assert source.org_id == ORG_ID
    assert source.incident_id == INCIDENT_ID


def test_sensor_telemetry_provenance_not_simulated() -> None:
    """Sensor telemetry provenance_chain must not mark data as simulated."""
    source = CalibrationSensorSource()
    tel = source.read_telemetry()
    chain = tel["provenance_chain"]
    assert chain.get("simulated") is not True
    assert chain.get("source") == "mock"
    assert chain.get("device_id") == DEVICE_ID


def test_sensor_telemetry_to_calibration_samples() -> None:
    """telemetry_to_samples produces N_SAMPLES valid {X, y} dicts."""
    source = CalibrationSensorSource()
    samples = telemetry_to_calibration_samples(source)
    assert len(samples) == N_SAMPLES
    for s in samples:
        assert "X" in s and "y" in s
        assert isinstance(s["X"], list) and len(s["X"]) == 3
        assert isinstance(s["y"], float)


def test_sensor_telemetry_ingest_and_fit_round_trip() -> None:
    """Full round-trip: sensor telemetry -> ingest -> fit -> intervals.

    1. CalibrationSensorSource produces 50 deterministic water-level readings
    2. telemetry_to_samples() converts to {X, y} calibration format
    3. POST /api/incidents/{id}/calibration/data stores samples -> 201
    4. POST /api/incidents/{id}/calibration/fit fits ConformalCalibrator
       -> 200 with prediction intervals + Brier/ECE/coverage metrics
    5. Coverage is within [0.7, 1.0] — reasonable for alpha=0.1 with 50
       samples (wider than the 200-sample fixture test's [0.85, 0.95]
       band because the prediction set is smaller: ~15 vs ~60 samples)
    """
    source = CalibrationSensorSource()
    samples = telemetry_to_calibration_samples(source)
    assert len(samples) == N_SAMPLES

    with TestClient(app) as client:
        admin_token = _login(client, "admin@demo.disaster")
        inc_resp = client.post(
            "/api/incidents",
            json={"title": "Sensor Calibration Ingest", "disaster_type": "flood"},
            headers=_auth_header(admin_token),
        )
        assert inc_resp.status_code == 201
        incident_id = inc_resp.json()["id"]

        # Step 3: ingest calibration data via API
        payload = {
            "model_id": "sensor-water-level-v1",
            "h3_zone": "zone_calib",
            "samples": samples,
        }
        store_resp = client.post(
            f"/api/incidents/{incident_id}/calibration/data",
            json=payload,
            headers=_auth_header(admin_token),
        )
        assert store_resp.status_code == 201, f"store failed: {store_resp.text}"
        store_body = store_resp.json()
        assert store_body["stored"] == N_SAMPLES
        assert store_body["incident_id"] == incident_id
        assert store_body["model_id"] == "sensor-water-level-v1"

        # Step 4: fit calibrator
        fit_resp = client.post(
            f"/api/incidents/{incident_id}/calibration/fit",
            json={"alpha": 0.1, "model_id": "sensor-water-level-v1"},
            headers=_auth_header(admin_token),
        )
        assert fit_resp.status_code == 200, f"fit failed: {fit_resp.text}"
        body = fit_resp.json()

        assert body["alpha"] == 0.1
        assert body["n_samples"] == N_SAMPLES
        assert body["n_fit"] > 0
        assert body["n_predict"] > 0

        intervals = body["intervals"]
        for key in ("prediction", "interval_lower", "interval_upper", "interval_width"):
            assert key in intervals, f"missing interval key: {key}"
            assert len(intervals[key]) == body["n_predict"]

        metrics = body["metrics"]
        for key in ("conformal_coverage", "interval_width", "brier_score", "ece"):
            assert key in metrics, f"missing metric: {key}"

        # Step 5: coverage within reasonable range for alpha=0.1
        coverage = metrics["conformal_coverage"]
        assert 0.7 <= coverage <= 1.0, (
            f"coverage {coverage} outside [0.7, 1.0] for alpha=0.1 "
            f"with {body['n_predict']} prediction samples"
        )

        print(
            f"\nSensor telemetry calibration: n={body['n_samples']}, "
            f"fit={body['n_fit']}, predict={body['n_predict']}, "
            f"coverage={coverage:.4f}, brier={metrics['brier_score']:.4f}, "
            f"ece={metrics['ece']:.4f}"
        )


def test_sensor_telemetry_ingest_requires_auth() -> None:
    """POST /calibration/data without auth -> 401."""
    source = CalibrationSensorSource()
    samples = telemetry_to_calibration_samples(source)

    with TestClient(app) as client:
        admin_token = _login(client, "admin@demo.disaster")
        inc_resp = client.post(
            "/api/incidents",
            json={"title": "Auth Test Ingest", "disaster_type": "flood"},
            headers=_auth_header(admin_token),
        )
        incident_id = inc_resp.json()["id"]

        resp = client.post(
            f"/api/incidents/{incident_id}/calibration/data",
            json={
                "model_id": "sensor-water-level-v1",
                "samples": samples,
            },
        )
        assert resp.status_code == 401
