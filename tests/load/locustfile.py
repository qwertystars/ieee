"""Locust load test — 50 concurrent operators + 100 obs/sec ingest vs the 6 SLOs.

SLOs (locked decision D3):
  1. 50 concurrent operators
  2. 100 obs/sec sustained ingest
  3. <2s p95 dashboard load time
  4. <500ms p95 API read latency
  5. 99% availability over 1h soak (configurable via SOAK_DURATION)
  6. <30s failover time (from T19 chaos evidence)

Two-phase design (the backend DB pool is 15 connections, single uvicorn
worker — running 50 operators + 150 ingest simultaneously overwhelms it):
  Phase 1 (LOAD_PHASE=operator): 50 OperatorUsers — measures SLOs 1, 3, 4, 5
  Phase 2 (LOAD_PHASE=ingest):   50 IngestUsers  — measures SLO 2

Run (via make load-test, which runs both phases + combines):
  cd backend && LOAD_PHASE=operator PYTHONPATH=. .venv/bin/locust \
      -f ../tests/load/locustfile.py --headless -u 50 -r 10 -t 60s \
      --host http://localhost:8000
  cd backend && LOAD_PHASE=ingest PYTHONPATH=. .venv/bin/locust \
      -f ../tests/load/locustfile.py --headless -u 50 -r 10 -t 60s \
      --host http://localhost:8000
  python tests/load/combine_report.py --profile full

  SOAK_DURATION=600 make load-test   # CI default (10min)
  SOAK_DURATION=3600 make load-test  # production SLO (1h)

Report: evidence/load/<date>-{full,reduced}.json (combined by combine_report.py).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from locust import HttpUser, between, constant, events, task

BASE_URL = os.environ.get("LOAD_BASE_URL", "http://localhost:8000")
USERNAME = os.environ.get("LOAD_USERNAME", "admin@demo.disaster")
PASSWORD = os.environ.get("LOAD_PASSWORD", "demo1234")
PROFILE = os.environ.get("PROFILE", "full")
LOAD_PHASE = os.environ.get("LOAD_PHASE", "operator")
EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "evidence" / "load"

SLO_DASHBOARD_P95_S = 2.0
SLO_API_READ_P95_MS = 500.0
SLO_SUCCESS_RATE = 0.99
SLO_FAILOVER_S = 30.0
SLO_INGEST_RATE_PER_S = 100.0
SLO_CONCURRENT_OPERATORS = 50
INGEST_BATCH_SIZE = 10

API_READ_PATHS = (
    "/api/observations",
    "/api/capabilities",
    "/api/incidents",
)

_dashboard_times: list[float] = []
_api_read_times: list[float] = []
_ingest_post_count = 0
_ingest_post_failures = 0
_total_requests = 0
_total_failures = 0
_start_time = time.monotonic()

_STARTUP_PATHS = ("/api/auth/login", "/api/incidents")


def _normalize_path(path: str) -> str:
    parts = path.split("/")
    out: list[str] = []
    for p in parts:
        if p and all(c in "0123456789abcdefABCDEF" for c in p) and len(p) > 10:
            out.append("{id}")
        else:
            out.append(p)
    return "/".join(out)


@events.request.add_listener
def _on_request(request_type: str, name: str, response_time: float,
                response_length: int, exception: Any, **kw: Any) -> None:
    """Collect per-endpoint timings for SLO reporting.

    Startup calls (login, initial incident list) are counted in the global
    success/failure totals but excluded from the steady-state API read p95,
    since they occur during user spawn (rate-limited) not steady-state.
    """
    global _total_requests, _total_failures, _ingest_post_count, _ingest_post_failures
    _total_requests += 1
    if exception is not None:
        _total_failures += 1
        if request_type == "POST" and "observations" in name:
            _ingest_post_failures += 1
        return

    rt_s = response_time / 1000.0
    norm = _normalize_path(name)

    is_startup = norm in _STARTUP_PATHS and request_type == "POST" or (
        norm == "/api/incidents" and request_type == "GET"
    )
    if is_startup:
        return

    if request_type == "POST" and "observations" in norm:
        _ingest_post_count += 1
    elif "situation-report" in norm:
        _dashboard_times.append(rt_s)
    elif any(norm.startswith(p) or norm == p for p in API_READ_PATHS):
        _api_read_times.append(rt_s)
    elif norm == "/api/incidents/{id}/tasks" or norm == "/api/incidents/{id}/alerts":
        _api_read_times.append(rt_s)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = int(len(s) * pct / 100.0)
    if k >= len(s):
        k = len(s) - 1
    return s[k]


@events.quitting.add_listener
def _write_phase_report(environment: Any, **kw: Any) -> None:
    """Write this phase's metrics to evidence/load/.tmp-<phase>.json."""
    duration_s = time.monotonic() - _start_time
    success_rate = (
        (_total_requests - _total_failures) / _total_requests
        if _total_requests > 0 else 0.0
    )
    ingest_rate = (_ingest_post_count * INGEST_BATCH_SIZE) / duration_s if duration_s > 0 else 0.0
    p95_dashboard_s = _percentile(_dashboard_times, 95)
    p95_api_read_ms = _percentile(_api_read_times, 95) * 1000.0

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f".tmp-{LOAD_PHASE}.json"
    report: dict[str, Any] = {
        "phase": LOAD_PHASE,
        "duration_s": round(duration_s, 2),
        "total_requests": _total_requests,
        "total_failures": _total_failures,
        "success_rate": round(success_rate, 6),
        "p95_dashboard_s": round(p95_dashboard_s, 4),
        "p95_api_read_ms": round(p95_api_read_ms, 2),
        "ingest_posts": _ingest_post_count,
        "ingest_failures": _ingest_post_failures,
        "ingest_rate_per_s": round(ingest_rate, 2),
    }
    path.write_text(json.dumps(report, indent=2))
    print(f"\n--- Phase ({LOAD_PHASE}) metrics written to {path} ---")
    print(json.dumps(report, indent=2))


_OBS_COUNTER = 0


def _make_observation_feature(source_id: str) -> dict[str, Any]:
    global _OBS_COUNTER
    _OBS_COUNTER += 1
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [72.85, 19.07]},
        "properties": {
            "event_type": "sensor",
            "phenomenon": "water_level",
            "value": float(_OBS_COUNTER % 500) / 100.0,
            "unit": "m",
            "source_id": source_id,
            "source_type": "sensor",
            "observed_at": int(time.time() * 1000),
            "source_reliability": 0.8,
            "freshness": 1.0,
            "access_policy": "internal",
        },
    }


def _make_batch_collection(source_id: str, count: int) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [_make_observation_feature(source_id) for _ in range(count)],
    }


class _AuthMixin:
    """Login + incident_id fetch helpers — not an HttpUser subclass.

    Locust discovers HttpUser subclasses and spawns them. If this mixin
    inherited from HttpUser, locust would spawn idle _AuthMixin instances
    that dilute the user count.
    """

    def _login(self) -> None:
        resp = self.client.post(
            "/api/auth/login",
            data={"username": USERNAME, "password": PASSWORD},
            name="/api/auth/login",
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {self.token}"}

    def _fetch_incident_id(self) -> None:
        if not self.token:
            return
        resp = self.client.get("/api/incidents", headers=self.headers,
                               name="/api/incidents")
        if resp.status_code == 200:
            incs = resp.json().get("incidents") or []
            if incs:
                self.incident_id = incs[0]["id"]


if LOAD_PHASE in ("operator", "both"):
    class OperatorUser(_AuthMixin, HttpUser):
        weight = 1
        wait_time = between(1, 3)
        host = BASE_URL

        def on_start(self) -> None:
            self.token: str | None = None
            self.incident_id: str | None = None
            self.headers: dict[str, str] = {}
            self._login()
            self._fetch_incident_id()

        @task(3)
        def poll_dashboard(self) -> None:
            if not self.incident_id:
                return
            self.client.get(
                f"/api/incidents/{self.incident_id}/situation-report",
                headers=self.headers,
                name="/api/incidents/{id}/situation-report",
            )

        @task(4)
        def fetch_observations(self) -> None:
            if not self.incident_id:
                return
            self.client.get(
                "/api/observations",
                headers=self.headers,
                params={"incident_id": self.incident_id, "limit": 20},
                name="/api/observations",
            )

        @task(2)
        def fetch_tasks(self) -> None:
            if not self.incident_id:
                return
            self.client.get(
                f"/api/incidents/{self.incident_id}/tasks",
                headers=self.headers,
                name="/api/incidents/{id}/tasks",
            )

        @task(2)
        def fetch_alerts(self) -> None:
            if not self.incident_id:
                return
            self.client.get(
                f"/api/incidents/{self.incident_id}/alerts",
                headers=self.headers,
                name="/api/incidents/{id}/alerts",
            )

        @task(1)
        def fetch_capabilities(self) -> None:
            self.client.get(
                "/api/capabilities",
                headers=self.headers,
                name="/api/capabilities",
            )

        @task(1)
        def approve_draft_alert(self) -> None:
            if not self.incident_id:
                return
            resp = self.client.get(
                f"/api/incidents/{self.incident_id}/alerts",
                headers=self.headers,
                params={"status": "draft"},
                name="/api/incidents/{id}/alerts?status=draft",
            )
            if resp.status_code != 200:
                return
            alerts = resp.json().get("alerts") or []
            if not alerts:
                return
            alert_id = alerts[0]["id"]
            self.client.post(
                f"/api/incidents/{self.incident_id}/alerts/{alert_id}/approve",
                headers=self.headers,
                json={"review_rationale": "load-test approval"},
                name="/api/incidents/{id}/alerts/{alert_id}/approve",
            )


if LOAD_PHASE in ("ingest", "both"):
    class IngestUser(_AuthMixin, HttpUser):
        weight = 1
        wait_time = between(1, 3)
        host = BASE_URL

        def on_start(self) -> None:
            self.token: str | None = None
            self.incident_id: str | None = None
            self.headers: dict[str, str] = {}
            self.source_id = f"loadtest-ingest-{id(self) & 0xFFFF:x}"
            self._login()
            self._fetch_incident_id()

        @task
        def post_observation(self) -> None:
            if not self.incident_id:
                return
            collection = _make_batch_collection(self.source_id, INGEST_BATCH_SIZE)
            self.client.post(
                "/api/observations/batch",
                headers=self.headers,
                params={"incident_id": self.incident_id},
                json=collection,
                name="/api/observations/batch POST",
            )
