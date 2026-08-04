#!/usr/bin/env python3
"""Run the authenticated, non-actuating shadow replay CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.shadow_replay_contract import (
    JsonObject,
    ReplayInputError,
    ReplayRequest,
    evaluate_replay,
    load_baseline,
    load_fixture,
    load_prerequisites,
)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_report(path: Path, command: str, status: str, exit_code: int, metrics: JsonObject, inputs: tuple[Path, ...], started_at: str) -> None:
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "unavailable"
    payload: JsonObject = {
        "task_id": "23", "claim_class": "shadow_machine", "command": command, "cwd": str(Path.cwd()),
        "inputs": [str(item) for item in inputs], "code_revision": revision, "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"), "exit_code": exit_code,
        "status": status, "metrics": metrics, "hashes": {str(item): _hash(item) for item in inputs if item.is_file()},
        "failure_assertion": "all shadow thresholds and no-actuation assertions passed" if exit_code == 0 else "shadow replay failed closed: " + "; ".join(str(item) for item in metrics.get("findings", [])),
        "cleanup": "No API route, database row, queue message, resource commitment, public warning, network egress, external dataset, operator, or agency system was invoked or modified.",
        "external_limitations": ["Synthetic fixture is validation-only; operator feedback, trusted external baseline data, and 30-day field evidence remain DEFERRED_EXTERNAL."],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Run the CLI boundary and return a machine-readable exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=Path("config/shadow-baseline-v1.json"))
    parser.add_argument("--min-incidents", type=int, default=100)
    parser.add_argument("--min-window-days", type=int, default=30)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--assert-no-actuation", action="store_true")
    parser.add_argument("--machine-only", action="store_true")
    args = parser.parse_args(argv)
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    prerequisites = ROOT / "evidence/sota/prerequisites.json"
    inputs = (args.fixture, args.baseline, Path("evidence/sota/prerequisites.json"), Path("scripts/run_shadow_replay.py"), Path("scripts/shadow_replay_contract.py"))
    try:
        baseline = load_baseline(args.baseline)
        manifest, records = load_fixture(args.fixture)
        request = ReplayRequest(baseline, manifest, records, load_prerequisites(prerequisites), args.min_incidents, args.min_window_days)
        exit_code, status, metrics = evaluate_replay(request)
    except (OSError, ReplayInputError, TypeError, ValueError) as error:
        exit_code, status = 1, "FAIL"
        metrics = {"findings": [str(error)], "external_shadow_claim": "DEFERRED_EXTERNAL"}
    print(f"status={status}")
    for finding in metrics.get("findings", []):
        print(f"finding={finding}")
    if args.report is not None:
        _write_report(args.report, " ".join(sys.argv), status, exit_code, metrics, inputs, started_at)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
