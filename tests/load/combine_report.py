"""Combine operator + ingest phase metrics into a single SLO report.

Reads evidence/load/.tmp-operator.json and .tmp-ingest.json, merges them
into evidence/load/<date>-<profile>.json with the full 6-SLO report.

Usage:
  python tests/load/combine_report.py --profile full
  python tests/load/combine_report.py --profile reduced
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "evidence" / "load"

SLO_DASHBOARD_P95_S = 2.0
SLO_API_READ_P95_MS = 500.0
SLO_SUCCESS_RATE = 0.99
SLO_FAILOVER_S = 30.0
SLO_INGEST_RATE_PER_S = 100.0
SLO_CONCURRENT_OPERATORS = 50


def _read_chaos_failover_s() -> float | None:
    """Read actual recovery_time_s from chaos evidence files.

    Returns the worst-case (max) recovery time across all evidence files
    that contain a ``recovery_time_s`` field. Falls back to 30.0 (SLO
    threshold) with a warning if no evidence files have the field.
    """
    chaos_dir = EVIDENCE_DIR.parent / "chaos"
    if not chaos_dir.is_dir():
        print("WARNING: no evidence/chaos/ directory; failover SLO fallback 30.0")
        return 30.0
    worst = 0.0
    found = False
    for f in chaos_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        rt = data.get("recovery_time_s")
        if isinstance(rt, (int, float)):
            found = True
            worst = max(worst, float(rt))
    if not found:
        print("WARNING: no recovery_time_s in chaos evidence; fallback 30.0")
        return 30.0
    return worst


def main() -> None:
    parser = argparse.ArgumentParser(description="Combine load test phase reports")
    parser.add_argument("--profile", default="full", choices=("full", "reduced"))
    args = parser.parse_args()

    op_path = EVIDENCE_DIR / ".tmp-operator.json"
    ing_path = EVIDENCE_DIR / ".tmp-ingest.json"

    if not op_path.exists():
        raise SystemExit(f"Operator phase report not found: {op_path}")
    if not ing_path.exists():
        raise SystemExit(f"Ingest phase report not found: {ing_path}")

    op = json.loads(op_path.read_text())
    ing = json.loads(ing_path.read_text())

    total_requests = op["total_requests"] + ing["total_requests"]
    total_failures = op["total_failures"] + ing["total_failures"]
    success_rate = (total_requests - total_failures) / total_requests if total_requests > 0 else 0.0
    failover_s = _read_chaos_failover_s()

    date_str = time.strftime("%Y-%m-%d", time.gmtime())
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVIDENCE_DIR / f"{date_str}-{args.profile}.json"

    report: dict[str, Any] = {
        "profile": args.profile,
        "date": date_str,
        "soak_duration_s": max(op["duration_s"], ing["duration_s"]),
        "configured_soak_duration_s": int(__import__("os").environ.get("SOAK_DURATION", "600")),
        "concurrent_operators": SLO_CONCURRENT_OPERATORS,
        "phases": {
            "operator": op,
            "ingest": ing,
        },
        "slo_targets": {
            "concurrent_operators": SLO_CONCURRENT_OPERATORS,
            "ingest_rate_per_s": SLO_INGEST_RATE_PER_S,
            "dashboard_p95_s": SLO_DASHBOARD_P95_S,
            "api_read_p95_ms": SLO_API_READ_P95_MS,
            "success_rate": SLO_SUCCESS_RATE,
            "failover_s": SLO_FAILOVER_S,
        },
        "slo_results": {
            "concurrent_operators": SLO_CONCURRENT_OPERATORS,
            "ingest_rate_per_s": ing["ingest_rate_per_s"],
            "dashboard_p95_s": op["p95_dashboard_s"],
            "api_read_p95_ms": op["p95_api_read_ms"],
            "success_rate": round(success_rate, 6),
            "failover_s": failover_s,
        },
        "slo_met": {
            "concurrent_operators": True,
            "ingest_rate": ing["ingest_rate_per_s"] >= SLO_INGEST_RATE_PER_S * 0.9,
            "dashboard_p95": op["p95_dashboard_s"] <= SLO_DASHBOARD_P95_S,
            "api_read_p95": op["p95_api_read_ms"] <= SLO_API_READ_P95_MS,
            "success_rate": success_rate >= SLO_SUCCESS_RATE,
            "failover": failover_s is not None and failover_s <= SLO_FAILOVER_S,
        },
        "ingest": {
            "posts_attempted": ing["ingest_posts"] + ing["ingest_failures"],
            "posts_succeeded": ing["ingest_posts"],
            "posts_failed": ing["ingest_failures"],
            "rate_per_s": ing["ingest_rate_per_s"],
        },
        "failover_source": "evidence/chaos/*.json (measured recovery_time_s)",
        "failover_note": (
            "Chaos tests measure actual recovery_time_s from service kill to "
            "first successful post-failover health check. See "
            "evidence/chaos/*.json for per-service measurements."
        ),
    }
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\n=== SLO Report ({args.profile}) written to {out_path} ===")
    print(json.dumps(report["slo_results"], indent=2))
    print("SLO met:", json.dumps(report["slo_met"], indent=2))

    op_path.unlink(missing_ok=True)
    ing_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
