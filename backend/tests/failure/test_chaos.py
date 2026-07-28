"""Chaos failure-injection tests — kill redis/redpanda/minio mid-load.

Each test starts a sustained load workload, kills one Docker service,
asserts graceful degradation (no crash, fallback path active), restarts
the service, and asserts recovery within 30s. Evidence is written to
``evidence/chaos/``.

Run:
    PYTHONPATH=. .venv/bin/python -m pytest tests/failure/test_chaos.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

BASE_URL = os.environ.get("CHAOS_BASE_URL", "http://localhost:8000")
COMPOSE_DIR = os.environ.get("COMPOSE_DIR", Path(__file__).resolve().parents[3])
PASSWORD = "demo1234"
USERNAME = "admin@demo.disaster"
FAILOVER_TIMEOUT_S = 30
EVIDENCE_DIR = Path(__file__).resolve().parents[3] / "evidence" / "chaos"


def _docker_compose(action: str, service: str) -> subprocess.CompletedProcess:
    """Run `docker compose <action> <service>` in COMPOSE_DIR."""
    return subprocess.run(
        ["docker", "compose", action, service],
        cwd=COMPOSE_DIR,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _login(client: httpx.Client) -> str:
    """Login and return the JWT access token."""
    resp = client.post(
        "/api/auth/login",
        data={"username": USERNAME, "password": PASSWORD},
        timeout=10.0,
    )
    assert resp.status_code == 200, f"login failed: {resp.status_code}"
    return resp.json()["access_token"]


def _deep_health(client: httpx.Client) -> dict[str, bool]:
    """Return the deep health check's checks dict."""
    resp = client.get("/healthz/deep", timeout=15.0)
    assert resp.status_code == 200, f"deep health failed: {resp.status_code}"
    return resp.json()["checks"]


def _get_incident_id(client: httpx.Client, token: str) -> str:
    """Fetch the first incident ID for observation POSTs."""
    resp = client.get(
        "/api/incidents", headers={"Authorization": f"Bearer {token}"}, timeout=10.0
    )
    assert resp.status_code == 200
    incidents = resp.json().get("incidents", [])
    assert incidents, "no incidents found for chaos test"
    return incidents[0]["id"]


def _post_observation(client: httpx.Client, token: str, incident_id: str) -> int:
    """POST a single observation. Returns the HTTP status code."""
    feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-73.9, 40.7]},
        "properties": {
            "event_type": "sensor_observation",
            "phenomenon": "water_level",
            "value": 1.5,
            "unit": "m",
            "source_id": f"chaos_{int(time.time() * 1000)}",
            "source_type": "sensor",
        },
    }
    try:
        resp = client.post(
            f"/api/observations?incident_id={incident_id}",
            json=feature,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        return resp.status_code
    except Exception:
        return 0


class _LoadWorker:
    """Background thread making sustained requests during chaos tests."""

    def __init__(self, client: httpx.Client, token: str, incident_id: str) -> None:
        self._client = client
        self._token = token
        self._incident_id = incident_id
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.successes = 0
        self.failures = 0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10.0)

    def _run(self) -> None:
        headers = {"Authorization": f"Bearer {self._token}"}
        while not self._stop.is_set():
            try:
                resp = self._client.get(
                    "/api/incidents", headers=headers, timeout=5.0
                )
                if resp.status_code == 200:
                    self.successes += 1
                else:
                    self.failures += 1
            except Exception:
                self.failures += 1
            time.sleep(0.1)


def _write_evidence(name: str, result: dict[str, Any]) -> Path:
    """Write chaos test results to evidence/chaos/."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = EVIDENCE_DIR / f"{name}-{ts}.json"
    path.write_text(json.dumps(result, indent=2))
    return path


def _wait_for_service(
    client: httpx.Client, service: str, timeout_s: int = FAILOVER_TIMEOUT_S
) -> bool:
    """Wait for a service to recover in deep health check. Returns True if recovered."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            checks = _deep_health(client)
            if checks.get(service) is True:
                return True
        except Exception:
            pass
        time.sleep(2.0)
    return False


@pytest.fixture
def client() -> httpx.Client:
    """HTTP client against the live Docker backend."""
    with httpx.Client(base_url=BASE_URL) as c:
        yield c


@pytest.fixture
def auth(client: httpx.Client) -> tuple[str, str]:
    """Login and return (token, incident_id)."""
    token = _login(client)
    incident_id = _get_incident_id(client, token)
    return token, incident_id


def test_chaos_redis_kill(client: httpx.Client, auth: tuple[str, str]) -> None:
    """Kill redis mid-load: token revocation fail-open, no crash, recover <30s."""
    token, incident_id = auth
    worker = _LoadWorker(client, token, incident_id)
    worker.start()
    time.sleep(2.0)  # let load ramp up

    # Kill redis.
    stop_result = _docker_compose("stop", "redis")
    assert stop_result.returncode == 0, f"docker compose stop redis failed: {stop_result.stderr}"
    time.sleep(3.0)  # let the backend detect the outage

    # Assert fail-open: login + protected endpoint still work.
    login_resp = client.post(
        "/api/auth/login", data={"username": USERNAME, "password": PASSWORD}, timeout=10.0
    )
    assert login_resp.status_code == 200, "login must succeed when redis is down (fail-open)"

    me_resp = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=10.0
    )
    assert me_resp.status_code == 200, "protected endpoint must succeed when redis is down"

    # Deep health must report redis=False.
    checks = _deep_health(client)
    assert checks["redis"] is False, "deep health must report redis=False when redis is down"
    assert checks["database"] is True, "database must remain up"

    # Restart redis and assert recovery <30s.
    start_result = _docker_compose("start", "redis")
    assert start_result.returncode == 0, f"docker compose start redis failed: {start_result.stderr}"
    recovered = _wait_for_service(client, "redis")
    worker.stop()

    result = {
        "scenario": "redis_kill",
        "load_successes": worker.successes,
        "load_failures": worker.failures,
        "login_during_outage": login_resp.status_code,
        "protected_endpoint_during_outage": me_resp.status_code,
        "deep_health_during_outage": checks,
        "recovered_within_30s": recovered,
    }
    path = _write_evidence("redis_kill", result)
    print(f"\n--- Chaos: redis_kill (evidence: {path}) ---\n{json.dumps(result, indent=2)}")

    assert recovered, "redis must recover within 30s of restart"


def test_chaos_redpanda_kill(client: httpx.Client, auth: tuple[str, str]) -> None:
    """Kill redpanda mid-load: observations still POST to PostgreSQL, no crash, recover <30s."""
    token, incident_id = auth
    worker = _LoadWorker(client, token, incident_id)
    worker.start()
    time.sleep(2.0)

    stop_result = _docker_compose("stop", "redpanda")
    assert stop_result.returncode == 0, f"docker compose stop redpanda failed: {stop_result.stderr}"
    time.sleep(3.0)

    # Assert observations still insert directly to PostgreSQL (noop producer).
    obs_status = _post_observation(client, token, incident_id)
    assert obs_status == 201, (
        f"observation POST must succeed (201) when redpanda is down, got {obs_status}"
    )

    checks = _deep_health(client)
    assert checks["redpanda"] is False, "deep health must report redpanda=False when down"
    assert checks["database"] is True, "database must remain up"

    start_result = _docker_compose("start", "redpanda")
    assert start_result.returncode == 0, f"docker compose start redpanda failed: {start_result.stderr}"
    recovered = _wait_for_service(client, "redpanda")
    worker.stop()

    result = {
        "scenario": "redpanda_kill",
        "load_successes": worker.successes,
        "load_failures": worker.failures,
        "observation_post_during_outage": obs_status,
        "deep_health_during_outage": checks,
        "recovered_within_30s": recovered,
    }
    path = _write_evidence("redpanda_kill", result)
    print(f"\n--- Chaos: redpanda_kill (evidence: {path}) ---\n{json.dumps(result, indent=2)}")

    assert recovered, "redpanda must recover within 30s of restart"


def test_chaos_minio_kill(client: httpx.Client, auth: tuple[str, str]) -> None:
    """Kill minio mid-load: ML endpoints degrade gracefully, no crash, recover <30s."""
    token, incident_id = auth
    worker = _LoadWorker(client, token, incident_id)
    worker.start()
    time.sleep(2.0)

    stop_result = _docker_compose("stop", "minio")
    assert stop_result.returncode == 0, f"docker compose stop minio failed: {stop_result.stderr}"
    time.sleep(3.0)

    # Deep health must report minio=False.
    checks = _deep_health(client)
    assert checks["minio"] is False, "deep health must report minio=False when minio is down"
    assert checks["database"] is True, "database must remain up"

    # ML endpoint must not crash — returns 200 with either ok or model_unavailable.
    # ML routes check local cache first, so may still return ok; both are graceful.
    ml_resp = client.post(
        f"/api/incidents/{incident_id}/damage-assessment",
        json={},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15.0,
    )
    assert ml_resp.status_code == 200, (
        f"ML endpoint must return 200 (graceful) when minio is down, got {ml_resp.status_code}"
    )
    body = ml_resp.json()
    assert body.get("status") in ("ok", "model_unavailable"), (
        f"ML endpoint must return ok or model_unavailable, got status={body.get('status')}"
    )

    # Non-ML endpoint must still work normally.
    obs_resp = client.get(
        "/api/observations",
        headers={"Authorization": f"Bearer {token}"},
        params={"limit": 5},
        timeout=10.0,
    )
    assert obs_resp.status_code == 200, "non-ML endpoint must work when minio is down"

    start_result = _docker_compose("start", "minio")
    assert start_result.returncode == 0, f"docker compose start minio failed: {start_result.stderr}"
    recovered = _wait_for_service(client, "minio")
    worker.stop()

    result = {
        "scenario": "minio_kill",
        "load_successes": worker.successes,
        "load_failures": worker.failures,
        "ml_endpoint_during_outage": ml_resp.status_code,
        "ml_status_during_outage": body.get("status"),
        "non_ml_endpoint_during_outage": obs_resp.status_code,
        "deep_health_during_outage": checks,
        "recovered_within_30s": recovered,
    }
    path = _write_evidence("minio_kill", result)
    print(f"\n--- Chaos: minio_kill (evidence: {path}) ---\n{json.dumps(result, indent=2)}")

    assert recovered, "minio must recover within 30s of restart"
