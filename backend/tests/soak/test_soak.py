"""Soak test — sustained concurrent load against the live Docker backend.

Runs a configurable-duration soak (default 600s for CI; override via
``SOAK_DURATION`` env var, production SLO is 3600s). Simulates 50 concurrent
operators performing: login, poll dashboard (GET /api/incidents), fetch
observations (GET /api/observations). Asserts >=99% success rate and records
p95 latency. Results are written to ``evidence/soak/``.

Run:
    SOAK_DURATION=60 PYTHONPATH=. .venv/bin/python -m pytest tests/soak/test_soak.py -v
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

BASE_URL = os.environ.get("SOAK_BASE_URL", "http://localhost:8000")
PASSWORD = "demo1234"
USERNAME = "admin@demo.disaster"
CONCURRENCY = int(os.environ.get("SOAK_CONCURRENCY", "50"))
DURATION_S = int(os.environ.get("SOAK_DURATION", "600"))
SUCCESS_THRESHOLD = 0.99
EVIDENCE_DIR = Path(__file__).resolve().parents[3] / "evidence" / "soak"


async def _login(client: httpx.AsyncClient) -> str | None:
    """Login and return the JWT access token, or None on failure."""
    try:
        resp = await client.post(
            "/api/auth/login",
            data={"username": USERNAME, "password": PASSWORD},
            timeout=10.0,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
    except Exception:
        pass
    return None


async def _operator(
    client: httpx.AsyncClient,
    token: str,
    stop_time: float,
    stats: dict[str, list[float]],
    stats_lock: asyncio.Lock,
) -> None:
    """One operator loop: poll dashboard + fetch observations until stop_time."""
    headers = {"Authorization": f"Bearer {token}"}
    while time.monotonic() < stop_time:
        t0 = time.monotonic()
        try:
            resp = await client.get("/api/incidents", headers=headers, timeout=10.0)
            ok = resp.status_code == 200
        except Exception:
            ok = False
        elapsed = time.monotonic() - t0
        async with stats_lock:
            stats["dashboard"].append(elapsed)
            if not ok:
                stats["failures"] += 1  # type: ignore[operator]
            else:
                stats["successes"] += 1  # type: ignore[operator]

        t0 = time.monotonic()
        try:
            resp = await client.get(
                "/api/observations", headers=headers, params={"limit": 20}, timeout=10.0
            )
            ok = resp.status_code == 200
        except Exception:
            ok = False
        elapsed = time.monotonic() - t0
        async with stats_lock:
            stats["observations"].append(elapsed)
            if not ok:
                stats["failures"] += 1  # type: ignore[operator]
            else:
                stats["successes"] += 1  # type: ignore[operator]


def _percentile(values: list[float], pct: float) -> float:
    """Compute the pct-th percentile (0-100) of a list of floats."""
    if not values:
        return 0.0
    s = sorted(values)
    k = int(len(s) * pct / 100.0)
    if k >= len(s):
        k = len(s) - 1
    return s[k]


def _write_evidence(result: dict[str, Any]) -> Path:
    """Write soak results to evidence/soak/ and return the file path."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = EVIDENCE_DIR / f"soak-{ts}.json"
    path.write_text(json.dumps(result, indent=2))
    return path


@pytest.mark.asyncio
async def test_soak_sustained_load() -> None:
    """Soak test: 50 concurrent operators for SOAK_DURATION seconds.

    Asserts >=99% success rate. Records p95 latency for dashboard and
    observations endpoints. Writes results to evidence/soak/.
    """
    stats: dict[str, Any] = {
        "dashboard": [],
        "observations": [],
        "successes": 0,
        "failures": 0,
    }
    stats_lock = asyncio.Lock()

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Login all operators first.
        tokens: list[str] = []
        for _ in range(CONCURRENCY):
            tok = await _login(client)
            if tok:
                tokens.append(tok)
        assert len(tokens) >= CONCURRENCY * 0.9, (
            f"Failed to login >=90% of operators: {len(tokens)}/{CONCURRENCY}"
        )

        # Pad tokens to CONCURRENCY (reuse if some logins failed).
        while len(tokens) < CONCURRENCY:
            tokens.append(tokens[0] if tokens else "")

        stop_time = time.monotonic() + DURATION_S
        start = time.monotonic()

        tasks = [
            asyncio.create_task(
                _operator(client, tok, stop_time, stats, stats_lock)
            )
            for tok in tokens
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.monotonic() - start

    total = stats["successes"] + stats["failures"]
    success_rate = stats["successes"] / total if total > 0 else 0.0
    p95_dashboard = _percentile(stats["dashboard"], 95)
    p95_observations = _percentile(stats["observations"], 95)

    result = {
        "duration_s": round(elapsed, 2),
        "configured_duration_s": DURATION_S,
        "concurrency": CONCURRENCY,
        "total_requests": total,
        "successes": stats["successes"],
        "failures": stats["failures"],
        "success_rate": round(success_rate, 6),
        "p95_dashboard_s": round(p95_dashboard, 4),
        "p95_observations_s": round(p95_observations, 4),
        "base_url": BASE_URL,
    }
    path = _write_evidence(result)

    print(f"\n--- Soak Results (evidence: {path}) ---")
    print(json.dumps(result, indent=2))

    assert success_rate >= SUCCESS_THRESHOLD, (
        f"Success rate {success_rate:.4f} below threshold {SUCCESS_THRESHOLD}"
    )
    assert total > 0, "No requests were made during the soak period"
