"""Profile the ingest API (POST /api/observations) to identify the primary bottleneck.

Profiling approach:
  Client-side timing with time.perf_counter() measures total round-trip per
  request. Server internals (observation construction, db.add+commit, confidence
  vector, hypothesis update, audit write, broadcast) cannot be instrumented from
  the client without modifying source code. Instead we:

  1. Measure auth token acquisition time (once at start).
  2. Run 100 sequential POST /api/observations, measuring total round-trip and
     client-side payload construction time per request.
  3. Run 100 sequential GET /api/observations as a baseline (auth + middleware +
     simple DB list query, no ingest pipeline).
  4. Compare POST vs GET to isolate the ingest-specific processing overhead.
  5. Analyze the server-side code path (from observations.py POST handler) to
     identify which internal sections are the top bottlenecks based on DB
     operation count and computational complexity.

Run:  cd backend && .venv/bin/python tests/load/profile_ingest.py
"""

from __future__ import annotations

import sys
import time
from typing import Any

import requests

BASE_URL = "http://localhost:8000"
USERNAME = "admin@demo.disaster"
PASSWORD = "demo1234"
INCIDENT_ID = "01K0KF2EG0XC8KE3AD81HK0VEW"
NUM_REQUESTS = 100
TIMEOUT_S = 30.0


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Compute the pct-th percentile (0-100) from a pre-sorted list."""
    if not sorted_vals:
        return 0.0
    k = int(len(sorted_vals) * pct / 100.0)
    if k >= len(sorted_vals):
        k = len(sorted_vals) - 1
    return sorted_vals[k]


def _stats(ms_vals: list[float]) -> dict[str, float]:
    """Compute min/mean/p50/p95/p99/max from a list of millisecond values."""
    s = sorted(ms_vals)
    n = len(s)
    return {
        "min_ms": s[0] if s else 0.0,
        "mean_ms": sum(s) / n if n else 0.0,
        "p50_ms": _percentile(s, 50),
        "p95_ms": _percentile(s, 95),
        "p99_ms": _percentile(s, 99),
        "max_ms": s[-1] if s else 0.0,
    }


def _login(session: requests.Session) -> tuple[str, float]:
    """POST /api/auth/login, return (token, elapsed_ms)."""
    t0 = time.perf_counter()
    resp = session.post(
        f"{BASE_URL}/api/auth/login",
        data={"username": USERNAME, "password": PASSWORD},
        timeout=TIMEOUT_S,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    resp.raise_for_status()
    return resp.json()["access_token"], elapsed_ms


def _build_payload(seq: int) -> dict[str, Any]:
    """Build a valid GeoJSON Point observation payload with unique coords."""
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [-73.9857 + seq * 0.0001, 40.7484 + seq * 0.0001],
        },
        "properties": {
            "event_type": "sensor_observation",
            "phenomenon": "water_level",
            "value": round(2.5 + (seq % 10) * 0.1, 1),
            "unit": "m",
            "source_id": f"prof_src_{seq}",
            "source_type": "sensor",
        },
    }


def _run_posts(
    session: requests.Session, token: str, n: int
) -> tuple[list[float], list[float], int]:
    """Run n sequential POST /api/observations.

    Returns (round_trip_ms, construct_ms, failure_count).
    """
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/api/observations?incident_id={INCIDENT_ID}"
    round_trip: list[float] = []
    construct: list[float] = []
    failures = 0
    for i in range(n):
        tc = time.perf_counter()
        payload = _build_payload(i)
        construct.append((time.perf_counter() - tc) * 1000.0)

        t0 = time.perf_counter()
        try:
            resp = session.post(url, json=payload, headers=headers, timeout=TIMEOUT_S)
            elapsed = (time.perf_counter() - t0) * 1000.0
            if resp.status_code != 201:
                failures += 1
                print(f"  POST {i}: HTTP {resp.status_code}", file=sys.stderr)
            else:
                round_trip.append(elapsed)
        except requests.RequestException as exc:
            failures += 1
            print(f"  POST {i}: {exc}", file=sys.stderr)
    return round_trip, construct, failures


def _run_gets(
    session: requests.Session, token: str, n: int
) -> tuple[list[float], int]:
    """Run n sequential GET /api/observations (baseline).

    Returns (round_trip_ms, failure_count).
    """
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/api/observations"
    params = {"incident_id": INCIDENT_ID, "limit": 20}
    round_trip: list[float] = []
    failures = 0
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            resp = session.get(url, headers=headers, params=params, timeout=TIMEOUT_S)
            elapsed = (time.perf_counter() - t0) * 1000.0
            if resp.status_code != 200:
                failures += 1
            else:
                round_trip.append(elapsed)
        except requests.RequestException as exc:
            failures += 1
            print(f"  GET: {exc}", file=sys.stderr)
    return round_trip, failures


def _print_table(title: str, rows: list[dict[str, Any]]) -> None:
    """Print a formatted timing breakdown table."""
    print(f"\n{'=' * 90}")
    print(f" {title}")
    print(f"{'=' * 90}")
    fmt = "{:<28} {:>8} {:>8} {:>8} {:>8} {:>8} {:>8}"
    print(fmt.format("section", "min_ms", "mean_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms"))
    print("-" * 90)
    for r in rows:
        print(fmt.format(r["section"], f"{r['min_ms']:.2f}", f"{r['mean_ms']:.2f}",
                         f"{r['p50_ms']:.2f}", f"{r['p95_ms']:.2f}",
                         f"{r['p99_ms']:.2f}", f"{r['max_ms']:.2f}"))


def _server_analysis(post_mean: float, get_mean: float) -> None:
    """Print server-side code path analysis from observations.py POST handler."""
    overhead = post_mean - get_mean
    print(f"\n{'=' * 90}")
    print(" Server-side code path analysis (from observations.py POST handler)")
    print(f"{'=' * 90}")
    print(f"  GET baseline (auth + middleware + list query):  {get_mean:.2f} ms")
    print(f"  POST ingest total:                              {post_mean:.2f} ms")
    print(f"  Ingest pipeline overhead (POST - GET):          {overhead:.2f} ms")
    print()
    print("  Server-internal sections (estimated from code path):")
    print()
    sections = [
        ("auth",
         "JWT decode + user lookup + role check",
         "1 SELECT", "low (included in baseline)"),
        ("observation_construction",
         "ULID + ORM build + ST_GeomFromGeoJSON",
         "0 DB ops", "low (in-memory)"),
        ("db_add_commit",
         "db.add + db.commit + db.refresh",
         "1 INSERT + 1 SELECT", "medium (PostGIS geo conversion)"),
        ("confidence_vector",
         "compute_vector + attach + commit + refresh",
         "1+ SELECT + 1 UPDATE + 1 SELECT", "HIGH (corroboration + 2nd commit)"),
        ("hypothesis_update",
         "update_hypotheses_for_observation",
         "1+ SELECT + 1+ INSERT", "medium-high (hypothesis recompute)"),
        ("audit_write",
         "write_audit (hash-chained: read prev_hash + insert)",
         "1 SELECT + 1 INSERT", "medium (hash chain I/O)"),
        ("broadcast",
         "fetch_feature + schedule_broadcast (WebSocket)",
         "1 SELECT + WS I/O", "low-medium (async fire-and-forget)"),
    ]
    for name, desc, db_ops, cost in sections:
        print(f"    {name:<26} {db_ops:<34} {cost}")
    print()
    print("  Top 2 likely bottlenecks (by DB ops + computational complexity):")
    print("    1. confidence_vector  - corroboration DB query + second commit + refresh")
    print("    2. db_add_commit      - PostGIS ST_GeomFromGeoJSON + INSERT + refresh")
    print()
    print("  NOTE: Server internals are estimated from the code path in")
    print("  observations.py:68-196. For precise per-section timing, add")
    print("  OpenTelemetry spans or perf_counter instrumentation in the handler.")


def main() -> None:
    """Run the profiling script."""
    print(f"Profiling POST /api/observations  ({NUM_REQUESTS} sequential requests)")
    print(f"Backend: {BASE_URL}  Incident: {INCIDENT_ID}")

    try:
        health = requests.get(f"{BASE_URL}/healthz", timeout=5.0)
        health.raise_for_status()
    except requests.RequestException as exc:
        print(f"\nERROR: Backend not reachable at {BASE_URL}: {exc}")
        print("Start the backend first:  cd backend && uvicorn app.main:app --reload")
        sys.exit(1)

    session = requests.Session()

    print("\n[1/3] Acquiring auth token...")
    try:
        token, auth_ms = _login(session)
    except requests.RequestException as exc:
        print(f"ERROR: Login failed: {exc}")
        sys.exit(1)
    print(f"  auth_login: {auth_ms:.2f} ms")

    print(f"\n[2/3] Running {NUM_REQUESTS} sequential POST /api/observations...")
    post_ms, construct_ms, post_fail = _run_posts(session, token, NUM_REQUESTS)
    print(f"  {len(post_ms)} ok, {post_fail} failed")

    print(f"\n[3/3] Running {NUM_REQUESTS} sequential GET /api/observations (baseline)...")
    get_ms, get_fail = _run_gets(session, token, NUM_REQUESTS)
    print(f"  {len(get_ms)} ok, {get_fail} failed")

    if not post_ms:
        print("\nERROR: All POST requests failed. Cannot profile.")
        sys.exit(1)

    auth_row = {"section": "auth_login", "min_ms": auth_ms, "mean_ms": auth_ms,
                "p50_ms": auth_ms, "p95_ms": auth_ms, "p99_ms": auth_ms, "max_ms": auth_ms}
    construct_row = {"section": "payload_construction", **_stats(construct_ms)}
    post_row = {"section": "post_ingest_round_trip", **_stats(post_ms)}
    get_row = {"section": "get_baseline_round_trip", **_stats(get_ms)} if get_ms else None

    rows = [auth_row, construct_row, post_row]
    if get_row:
        rows.append(get_row)
    _print_table("Client-side timing breakdown (100 sequential requests)", rows)

    _server_analysis(post_row["mean_ms"], get_row["mean_ms"] if get_row else 0.0)

    print(f"\n{'=' * 90}")
    print(" Top 2 bottlenecks (by mean round-trip time)")
    print(f"{'=' * 90}")
    ranked = sorted(
        [("post_ingest_round_trip", post_row["mean_ms"]),
         ("get_baseline_round_trip", get_row["mean_ms"] if get_row else 0.0),
         ("auth_login", auth_ms),
         ("payload_construction", construct_row["mean_ms"])],
        key=lambda x: x[1], reverse=True,
    )[:2]
    for i, (name, ms) in enumerate(ranked, 1):
        print(f"  {i}. {name}: {ms:.2f} ms mean")
    print()

    session.close()


if __name__ == "__main__":
    main()
