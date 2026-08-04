"""Validate model-specific calibration contracts without fitting on final test."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.benchmark_contract_types import JsonObject
from scripts.calibration_contract import (
    CalibrationInputError,
    CalibrationReport,
    evaluate_calibration,
)


def _write_report(path: Path, manifest_path: Path, models_path: Path | None, report: CalibrationReport, command: str) -> None:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "unavailable"
    hashes = {
        str(manifest_path): hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "scripts/evaluate_calibration.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scripts/calibration_contract.py": hashlib.sha256(
            Path(__file__).with_name("calibration_contract.py").read_bytes()
        ).hexdigest(),
        "scripts/calibration_contract_validation.py": hashlib.sha256(
            Path(__file__).with_name("calibration_contract_validation.py").read_bytes()
        ).hexdigest(),
    }
    inputs = [
        str(manifest_path),
        "scripts/evaluate_calibration.py",
        "scripts/calibration_contract.py",
        "scripts/calibration_contract_validation.py",
    ]
    if models_path is not None:
        hashes[str(models_path)] = hashlib.sha256(models_path.read_bytes()).hexdigest()
        inputs.append(str(models_path))
    payload: JsonObject = {
        "task_id": "16", "command": command, "cwd": str(Path.cwd()), "inputs": inputs,
        "code_revision": revision, "started_at": now, "finished_at": now,
        "exit_code": report.exit_code, "status": report.status, "metrics": report.metrics,
        "models": report.model_reports, "hashes": hashes,
        "failure_assertion": "; ".join(report.findings) if report.findings else "all calibration contracts and thresholds passed",
        "external_limitations": [
            "No gated dataset or model calibration artifact was downloaded.",
            "DEFERRED_EXTERNAL model contracts remain abstain-only until their artifact, version, and hash are registered.",
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate leakage-safe model calibration contracts")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--models", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce-no-test-tuning", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = evaluate_calibration(args.manifest, args.models, args.enforce_no_test_tuning)
    except CalibrationInputError as error:
        print(f"status=FAIL\nerror={error}")
        return 1
    print(f"status={report.status}")
    for finding in report.findings:
        print(f"finding={finding}")
    if args.report is not None:
        _write_report(args.report, args.manifest, args.models, report, " ".join(sys.argv))
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
