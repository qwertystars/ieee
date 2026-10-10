#!/usr/bin/env python3
"""Verify signed rescue-ball telemetry without claiming physical evidence."""

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
sys.path.insert(0, str(ROOT / "backend"))
from scripts.sensor_harness_contract import (
    evaluate,
    physical_missing,
)
from scripts.sensor_harness_input import HarnessInputError, JsonObject, load_fixture


def _write_report(
    path: Path,
    command: str,
    status: str,
    exit_code: int,
    metrics: JsonObject,
    inputs: tuple[Path, ...],
    started_at: str,
) -> None:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "unavailable"
    payload: JsonObject = {
        "task_id": "25",
        "claim_class": "sensor_protocol_machine",
        "command": command,
        "cwd": str(Path.cwd()),
        "inputs": [str(item) for item in inputs],
        "code_revision": revision,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "exit_code": exit_code,
        "status": status,
        "metrics": metrics,
        "hashes": {
            str(item): hashlib.sha256(item.read_bytes()).hexdigest()
            for item in inputs
            if item.is_file()
        },
        "failure_assertion": "all signed protocol records accepted and unsafe records quarantined"
        if exit_code == 0
        else "; ".join(str(item) for item in metrics.get("findings", [])),
        "cleanup": "Read-only local fixture validation; no hardware, production keys, network, queue, database, or runtime state was modified.",
        "external_limitations": [
            "Secure boot, physical calibration, environmental limits, and real key custody are not established by fixture replay.",
            "No real sensing, rescue-ball detection, human detection, field, agency, or operational readiness claim is made.",
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    """Run the fixture harness at the CLI boundary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--verify-signature", action="store_true")
    parser.add_argument("--verify-sequence", action="store_true")
    parser.add_argument("--assert-quarantine", action="store_true")
    parser.add_argument("--prerequisites", type=Path)
    parser.add_argument("--require-physical", action="store_true")
    parser.add_argument("--expect-deferred", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    inputs = (args.fixture, Path("scripts/run_sensor_harness.py"))
    try:
        manifest, records = load_fixture(args.fixture)
        exit_code, status, metrics = evaluate(manifest, records)
        if args.assert_quarantine and metrics["quarantined_records"] == 0:
            exit_code, status = 1, "FAIL"
            metrics["findings"] = [
                *metrics["findings"],
                "assert-quarantine requested but no record was quarantined",
            ]
        if args.require_physical:
            if args.prerequisites is None or not args.expect_deferred:
                raise HarnessInputError(
                    "--require-physical requires --prerequisites and --expect-deferred"
                )
            missing = physical_missing(args.prerequisites)
            metrics["missing_physical_evidence"] = missing
            if exit_code == 0 and missing:
                exit_code, status = 2, "DEFERRED_EXTERNAL"
            elif not missing:
                metrics["physical_claim"] = "PASS"
    except (
        HarnessInputError,
        OSError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as error:
        exit_code, status, metrics = (
            1,
            "FAIL",
            {
                "findings": [str(error)],
                "protocol_contract": "FAIL",
                "physical_claim": "DEFERRED_EXTERNAL",
            },
        )
    print(f"status={status}")
    for finding in metrics.get("findings", []):
        print(f"finding={finding}")
    if args.report is not None:
        _write_report(
            args.report,
            " ".join(sys.argv),
            status,
            exit_code,
            metrics,
            inputs,
            started_at,
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
