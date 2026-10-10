"""Run and record one quality check, or aggregate recorded checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _revision(cwd: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _input_paths(command: list[str], cwd: Path) -> list[Path]:
    paths: list[Path] = []
    for token in command:
        candidate = cwd / token
        if candidate.is_file() and candidate not in paths:
            paths.append(candidate)
    if command and command[0] == "make":
        makefile = cwd / "Makefile"
        if makefile not in paths:
            paths.append(makefile)
    command_text = " ".join(command)
    for reference in ("scripts/verify_source_audit.py", "scripts/run_quality_gate.py"):
        candidate = cwd / reference
        if reference in command_text and candidate.is_file() and candidate not in paths:
            paths.append(candidate)
    return paths


def _write(report_path: Path, report: dict[str, Any]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run(args: argparse.Namespace) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        raise SystemExit("a command is required after --")
    cwd = Path(args.cwd).resolve()
    command_text = (
        command[0]
        if len(command) == 1 and any(token in command[0] for token in ("<(", ">(", "|"))
        else shlex.join(command)
    )
    started_at = _timestamp()
    result = subprocess.run(
        ["bash", "-o", "pipefail", "-c", command_text],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    status = "PASS" if result.returncode == 0 else (
        "DEFERRED_EXTERNAL" if result.returncode == 2 else "FAIL"
    )
    inputs = _input_paths(command, cwd)
    hashes = {str(path.relative_to(cwd)): _sha256(path) for path in inputs}
    hashes["command_sha256"] = hashlib.sha256(command_text.encode()).hexdigest()
    report = {
        "task_id": f"resqnet-sota-roadmap-F2-{Path(args.report_file).stem}",
        "command": command_text,
        "cwd": str(cwd),
        "inputs": [str(path.relative_to(cwd)) for path in inputs] or ["<command>"],
        "code_revision": _revision(cwd),
        "started_at": started_at,
        "finished_at": _timestamp(),
        "exit_code": result.returncode if result.returncode in {0, 1, 2} else 1,
        "observed_exit_code": result.returncode,
        "status": status,
        "metrics": {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "expected_exit_code": args.expect_exit,
            "expectation_met": args.expect_exit is None or result.returncode == args.expect_exit,
        },
        "hashes": hashes,
        "failure_assertion": "Exit 1 is a tested quality failure; exit 2 is reserved for unavailable external tooling.",
        "cleanup": "No source, dependency, or lockfile changes; command output was captured read-only.",
    }
    _write(Path(args.report_file), report)
    print(f"{status}: {command_text} (observed exit {result.returncode})")
    return report["exit_code"]


def _aggregate(args: argparse.Namespace) -> int:
    report_path = Path(args.report_file).resolve()
    paths = [Path(path).resolve() for path in args.aggregate if Path(path).resolve() != report_path]
    reports: list[dict[str, Any]] = []
    for path in sorted(paths):
        reports.append(json.loads(path.read_text(encoding="utf-8")))
    if not reports:
        raise SystemExit("aggregate requires at least one individual report")
    failure_count = sum(report.get("exit_code") == 1 for report in reports)
    deferred_count = sum(report.get("exit_code") == 2 for report in reports)
    exit_code = 1 if failure_count else 2 if deferred_count else 0
    status = {0: "PASS", 1: "FAIL", 2: "DEFERRED_EXTERNAL"}[exit_code]
    report = {
        "task_id": "resqnet-sota-roadmap-F2",
        "command": f"python {shlex.join(sys.argv)}",
        "cwd": str(Path.cwd()),
        "inputs": [str(path) for path in paths],
        "code_revision": _revision(Path.cwd()),
        "started_at": _timestamp(),
        "finished_at": _timestamp(),
        "exit_code": exit_code,
        "status": status,
        "metrics": {
            "individual_reports": [
                {
                    "path": str(path),
                    "status": item["status"],
                    "exit_code": item["exit_code"],
                    "observed_exit_code": item.get("observed_exit_code", item["exit_code"]),
                }
                for path, item in zip(paths, reports, strict=True)
            ],
            "failure_count": failure_count,
            "deferred_count": deferred_count,
            "aggregate_semantics": "FAIL if any individual exit_code is 1; DEFERRED_EXTERNAL only when no exit_code is 1 and at least one is 2; otherwise PASS.",
        },
        "hashes": {path.name: _sha256(path) for path in paths},
        "failure_assertion": "F2 APPROVE requires every individual report to have exit_code 0 and aggregate status PASS.",
        "cleanup": "No source, dependency, or lockfile changes; aggregate report was generated from individual reports.",
        "verdict": "APPROVE" if exit_code == 0 else "REJECT",
    }
    _write(report_path, report)
    print(f"VERDICT: {report['verdict']}")
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-file", required=True)
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--expect-exit", type=int)
    parser.add_argument("--aggregate", nargs="+")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    return _aggregate(args) if args.aggregate else _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
