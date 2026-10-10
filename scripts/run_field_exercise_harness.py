#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

# --- How to run ---
# Machine: backend/.venv/bin/python scripts/run_field_exercise_harness.py --scenario tests/fixtures/field-machine-v1.yaml --replay --report evidence/sota/task-26-machine.json
# Unsafe: backend/.venv/bin/python scripts/run_field_exercise_harness.py --scenario tests/fixtures/field-machine-failures.yaml --assert-safe-degradation
# External: backend/.venv/bin/python scripts/run_field_exercise_harness.py --scenario tests/fixtures/field-external.yaml --prerequisites evidence/sota/prerequisites.json --require-agency-hardware --expect-deferred
# -------------------

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.field_exercise_contract import (
    HarnessInputError,
    JsonObject,
    evaluate_machine,
    load_scenario,
    validate_external,
)


def _remediation(findings: list[str]) -> list[str]:
    return [f"Remediate failed gate before field promotion: {finding}" for finding in findings]


def _write_report(path: Path, command: str, status: str, exit_code: int, metrics: JsonObject, inputs: tuple[Path, ...], started_at: str) -> None:
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "unavailable"
    payload: JsonObject = {
        "task_id": "26", "claim_class": "field_machine", "command": command, "cwd": str(Path.cwd()), "inputs": [str(item) for item in inputs],
        "code_revision": revision, "started_at": started_at, "finished_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "exit_code": exit_code, "status": status, "metrics": metrics, "hashes": {str(item): hashlib.sha256(item.read_bytes()).hexdigest() for item in inputs if item.is_file()},
        "failure_assertion": "fixed degraded-mode thresholds, signed-log integrity, deterministic replay, and no-actuation controls passed" if exit_code == 0 else "; ".join(str(item) for item in metrics.get("findings", [])),
        "cleanup": "Read-only local fixture validation; no agency, participant, hardware, dispatch, public warning, resource commitment, network, database, queue, credential, or production state was invoked or modified.",
        "external_limitations": ["Machine fixture replay does not establish agency authorization, IRB/ethics, training, insurance/safety, device inventory, consent, human workload, physical measurements, or field readiness."],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--assert-safe-degradation", action="store_true")
    parser.add_argument("--prerequisites", type=Path)
    parser.add_argument("--require-agency-hardware", action="store_true")
    parser.add_argument("--expect-deferred", action="store_true")
    args = parser.parse_args(argv)
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    try:
        scenario = load_scenario(args.scenario)
        if args.replay or args.assert_safe_degradation:
            exit_code, status, metrics = evaluate_machine(scenario)
            if args.assert_safe_degradation and exit_code == 0:
                exit_code, status = 1, "FAIL"
                metrics["findings"] = [*metrics.get("findings", []), "assert-safe-degradation expected an unsafe fixture to fail"]
            inputs = (args.scenario, Path("scripts/run_field_exercise_harness.py"), Path("scripts/field_exercise_contract.py"))
        else:
            if args.prerequisites is None or not args.require_agency_hardware or not args.expect_deferred:
                raise HarnessInputError("external mode requires --prerequisites, --require-agency-hardware, and --expect-deferred")
            exit_code, status, metrics = validate_external(scenario, args.prerequisites)
            inputs = (args.scenario, args.prerequisites, Path("evidence/sota/field-trial-report.json"), Path("scripts/run_field_exercise_harness.py"), Path("scripts/field_exercise_contract.py"))
    except (HarnessInputError, OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        exit_code, status, metrics = 1, "FAIL", {"findings": [str(error)], "external_field_claim": "DEFERRED_EXTERNAL"}
        inputs = (args.scenario, Path("scripts/run_field_exercise_harness.py"), Path("scripts/field_exercise_contract.py"))
    findings = metrics.get("findings", [])
    metrics["remediation"] = _remediation([str(item) for item in findings]) if isinstance(findings, list) else []
    print(f"status={status}")
    for finding in findings if isinstance(findings, list) else []:
        print(f"finding={finding}")
    for remediation in metrics["remediation"] if isinstance(metrics["remediation"], list) else []:
        print(f"remediation={remediation}")
    if args.report is not None:
        _write_report(args.report, " ".join(sys.argv), status, exit_code, metrics, inputs, started_at)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
