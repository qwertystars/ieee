#!/usr/bin/env python3
"""CLI for the leakage-safe ResQNet benchmark contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.benchmark_contract import (
    BenchmarkInputError,
    JsonObject,
    JsonValue,
    ValidationReport,
    validate_benchmark,
)
from scripts.published_baseline_contract import RegistryInputError
from scripts.published_benchmark import build_published_report

__all__ = ["JsonValue", "ValidationReport", "main", "validate_benchmark"]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_report(
    path: Path,
    manifest_path: Path,
    report: ValidationReport,
    command: str,
    *,
    task_id: str,
    extra_inputs: tuple[str, ...] = (),
) -> None:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "unavailable"
    input_names = (
        str(manifest_path),
        "scripts/run_benchmark.py",
        "scripts/benchmark_contract.py",
        "scripts/benchmark_leakage.py",
        *extra_inputs,
    )
    input_paths = tuple(dict.fromkeys(Path(item) for item in input_names))
    hashes = {
        str(input_path): _sha256(input_path.read_text(encoding="utf-8"))
        for input_path in input_paths
        if input_path.is_file()
    }
    payload: JsonObject = {
        "task_id": task_id,
        "command": command,
        "cwd": str(Path.cwd()),
        "inputs": [str(manifest_path), "scripts/run_benchmark.py", "scripts/benchmark_contract.py", "scripts/benchmark_leakage.py", *extra_inputs],
        "code_revision": revision,
        "started_at": now,
        "finished_at": now,
        "exit_code": report.exit_code,
        "status": report.status,
        "metrics": report.metrics,
        "hashes": hashes,
        "failure_assertion": "; ".join(report.findings) if report.findings else "all benchmark and published-baseline invariants passed",
        "cleanup": "No external datasets downloaded; offline validation only.",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the leakage-safe ResQNet benchmark manifest")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--check-leakage", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--baselines", type=Path)
    parser.add_argument("--seeds", default="1,2,3,4,5")
    parser.add_argument("--require-published-baselines", action="store_true")
    parser.add_argument("--require-commands", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = validate_benchmark(args.manifest, args.check_leakage)
        baseline_path = args.baselines
        if baseline_path is None and (args.require_published_baselines or args.require_commands):
            baseline_path = Path("config/published-baselines-v1.json")
        if baseline_path is not None:
            try:
                seeds = tuple(int(seed.strip()) for seed in args.seeds.split(",") if seed.strip())
            except ValueError as error:
                raise BenchmarkInputError(f"--seeds must be comma-separated integers: {error}") from error
            if seeds != (1, 2, 3, 4, 5):
                raise BenchmarkInputError("--seeds must be exactly 1,2,3,4,5")
            baseline_exit, baseline_findings, baseline_metrics = build_published_report(
                args.manifest,
                baseline_path,
                seeds=seeds,
                require_published_baselines=args.require_published_baselines,
                require_commands=args.require_commands,
            )
            merged_metrics = dict(report.metrics)
            merged_metrics["published_baselines"] = baseline_metrics
            report = replace(
                report,
                status="FAIL" if report.findings or baseline_findings else "PASS",
                exit_code=max(report.exit_code, baseline_exit),
                findings=report.findings + baseline_findings,
                metrics=merged_metrics,
            )
    except (BenchmarkInputError, RegistryInputError) as error:
        print(f"status=FAIL\nerror={error}")
        return 1
    print(f"status={report.status}")
    for finding in report.findings:
        print(f"finding={finding}")
    if args.report is not None:
        task_id = "17" if args.baselines is not None or args.require_published_baselines or args.require_commands else "14"
        extra_inputs = (
            str(args.baselines or Path("config/published-baselines-v1.json")),
            "scripts/published_benchmark.py",
            "scripts/benchmark_statistics.py",
            "scripts/published_baseline_contract.py",
            "scripts/published_baseline_checks.py",
            "scripts/published_baseline_types.py",
            "scripts/published_baseline_rows.py",
            "scripts/run_baseline.py",
            "scripts/benchmark_manifest_input.py",
            "scripts/benchmark_manifest_splits.py",
        ) if task_id == "17" else ()
        _write_report(args.report, args.manifest, report, " ".join(sys.argv), task_id=task_id, extra_inputs=extra_inputs)
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
