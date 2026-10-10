# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""Execute an F3 command and write a normative evidence capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
STATUSES: Final = {"PASS", "FAIL", "DEFERRED_EXTERNAL"}
REPORT_OPTIONS: Final = {"--report", "--report-file"}


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _revision(cwd: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _status(exit_code: int) -> str:
    if exit_code == 0:
        return "PASS"
    if exit_code == 2:
        return "DEFERRED_EXTERNAL"
    return "FAIL"


def _command_text(command: list[str]) -> str:
    return command[0] if len(command) == 1 else shlex.join(command)


def _candidate(token: str, cwd: Path) -> Path | None:
    cleaned = token.strip("'\"`;,()")
    if not cleaned or cleaned.startswith("-") or "=" in cleaned and cleaned.split("=", 1)[0].startswith("-"):
        return None
    path = Path(cleaned)
    resolved = path if path.is_absolute() else cwd / path
    return resolved.resolve() if resolved.is_file() else None


def _input_paths(command_text: str, cwd: Path, report_path: Path) -> list[Path]:
    tokens = shlex.split(command_text)
    paths: list[Path] = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token in REPORT_OPTIONS:
            skip_next = True
            continue
        if any(token.startswith(f"{option}=") for option in REPORT_OPTIONS):
            continue
        path = _candidate(token, cwd)
        if path is not None and path != report_path.resolve() and path not in paths:
            paths.append(path)

    known_groups: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "run_production_parity.sh",
            (
                "config/production-parity.json",
                "docker-compose.production-parity.yml",
                "deploy/production-parity/haproxy.cfg",
                "docs/PRODUCTION_PARITY_RUNBOOK.md",
                "scripts/run_production_parity.sh",
            ),
        ),
        (
            "run_shadow_replay.py",
            (
                "scripts/run_shadow_replay.py",
                "scripts/shadow_replay_contract.py",
                "tests/fixtures/shadow-incident.ndjson",
                "config/shadow-baseline-v1.json",
                "evidence/sota/prerequisites.json",
            ),
        ),
        (
            "check_optional_dependencies.py",
            ("scripts/check_optional_dependencies.py", "config/validators.lock"),
        ),
    )
    for marker, names in known_groups:
        if marker in command_text:
            for name in names:
                path = (cwd / name).resolve()
                if path.is_file() and path != report_path.resolve() and path not in paths:
                    paths.append(path)
    if "npm run" in command_text or "npx playwright" in command_text:
        for name in ("package.json", "package-lock.json"):
            path = (cwd / name).resolve()
            if path.is_file() and path not in paths:
                paths.append(path)
    if "npx playwright" in command_text:
        for pattern in ("playwright.config.*", "tests/*.spec.*"):
            for path in sorted(cwd.glob(pattern)):
                if path.is_file() and path not in paths:
                    paths.append(path.resolve())
    return paths


def _display_path(path: Path, cwd: Path) -> str:
    try:
        return str(path.relative_to(cwd))
    except ValueError:
        return str(path)


def _write(path: Path, report: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run(args: argparse.Namespace) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        raise SystemExit("a command is required after --")
    if args.expect_exit is None or args.expect_status is None:
        raise SystemExit("--expect-exit and --expect-status are required for a command capture")
    cwd = Path(args.cwd).resolve()
    report_path = Path(args.report_file).resolve()
    command_text = _command_text(command)
    tool_dir = next((path for path in (cwd / ".venv/bin", cwd / "backend/.venv/bin", cwd.parent / "backend/.venv/bin") if path.is_dir()), cwd / ".venv/bin")
    execution_text = f"export PATH={shlex.quote(str(tool_dir))}:$PATH; {command_text}" if tool_dir.is_dir() else command_text
    started_at = _timestamp()
    result = subprocess.run(
        ["bash", "-o", "pipefail", "-lc", execution_text],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    normalized_exit_code = result.returncode if result.returncode in {0, 1, 2} else 1
    actual_status = _status(normalized_exit_code)
    pair_match = normalized_exit_code == args.expect_exit and actual_status == args.expect_status
    inputs = _input_paths(command_text, cwd, report_path)
    hashes = {_display_path(path, cwd): _sha256(path) for path in inputs}
    hashes["command_sha256"] = hashlib.sha256(command_text.encode("utf-8")).hexdigest()
    report: JsonObject = {
        "task_id": f"resqnet-sota-roadmap-F3-{report_path.stem}",
        "command": command_text,
        "cwd": str(cwd),
        "inputs": [_display_path(path, cwd) for path in inputs] or ["<command>"],
        "code_revision": _revision(cwd),
        "started_at": started_at,
        "finished_at": _timestamp(),
        "exit_code": normalized_exit_code,
        "status": actual_status,
        "metrics": {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "observed_exit_code": result.returncode,
            "expected_exit_code": args.expect_exit,
            "expected_status": args.expect_status,
            "expected_pair_match": pair_match,
        },
        "hashes": hashes,
        "failure_assertion": "The observed exit/status pair must match the exact F3 expectation; expected DEFERRED_EXTERNAL is accepted only for the declared external preflight.",
        "cleanup": "Command output was captured; no external validators, data, participants, credentials, or production state were created or modified by the wrapper.",
    }
    _write(report_path, report)
    print(f"{actual_status}: {command_text} (observed exit {result.returncode})")
    return 0 if pair_match else 1


def _load_report(path: Path) -> JsonObject:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path}: report must be an object")
    return value


def _validator_boundary(cwd: Path) -> tuple[JsonObject, str | None]:
    path = cwd / ".omo/evidence/resqnet-sota-roadmap/task-20.json"
    if not path.is_file():
        return {"status": "NOT_CAPTURED", "successful_exit_0_conformance_capture": False}, None
    value = _load_report(path)
    metrics = value.get("metrics")
    metrics_object = metrics if isinstance(metrics, dict) else {}
    recorded_exit = value.get("exit_code")
    recorded_status = value.get("status")
    boundary: JsonObject = {
        "evidence": str(path.relative_to(cwd)),
        "recorded_exit_code": recorded_exit,
        "recorded_status": recorded_status,
        "machine_conformance": metrics_object.get("machine_conformance"),
        "external_validator_availability": metrics_object.get("external_validator_availability"),
        "successful_exit_0_conformance_capture": recorded_exit == 0 and recorded_status == "PASS",
    }
    return boundary, _sha256(path)


def _aggregate(args: argparse.Namespace) -> int:
    report_path = Path(args.report_file).resolve()
    raw_paths = [item for value in args.aggregate for item in value.split(",") if item]
    paths = [Path(item).resolve() for item in raw_paths if Path(item).resolve() != report_path]
    if not paths:
        raise SystemExit("aggregate requires at least one individual report")
    reports = [_load_report(path) for path in paths]
    entries: list[JsonObject] = []
    for path, report in zip(paths, reports, strict=True):
        metrics = report.get("metrics")
        pair_match = metrics.get("expected_pair_match") if isinstance(metrics, dict) else False
        entries.append(
            {
                "path": str(path),
                "status": report.get("status"),
                "exit_code": report.get("exit_code"),
                "expected_exit_code": metrics.get("expected_exit_code") if isinstance(metrics, dict) else None,
                "expected_status": metrics.get("expected_status") if isinstance(metrics, dict) else None,
                "expected_pair_match": pair_match is True,
            }
        )
    matching_pairs = sum(item["expected_pair_match"] is True for item in entries)
    all_pairs_match = matching_pairs == len(entries)
    cwd = Path.cwd().resolve()
    validator, validator_hash = _validator_boundary(cwd)
    hashes = {str(path): _sha256(path) for path in paths}
    if validator_hash is not None:
        hashes[".omo/evidence/resqnet-sota-roadmap/task-20.json"] = validator_hash
    report: JsonObject = {
        "task_id": "resqnet-sota-roadmap-F3",
        "command": shlex.join([sys.executable, *sys.argv]),
        "cwd": str(cwd),
        "inputs": [str(path) for path in paths],
        "code_revision": _revision(cwd),
        "started_at": _timestamp(),
        "finished_at": _timestamp(),
        "exit_code": 0 if all_pairs_match else 1,
        "status": "PASS" if all_pairs_match else "FAIL",
        "metrics": {
            "individual_reports": entries,
            "matching_pairs": matching_pairs,
            "required_pairs": len(entries),
            "all_expected_pairs_match": all_pairs_match,
            "aggregate_semantics": "PASS/APPROVE requires every individual report's expected exit/status pair to match; expected DEFERRED_EXTERNAL is a declared boundary, not a fabricated success.",
            "validator_hash_prerequisite": validator,
            "claim_boundaries": {"production": "DEFERRED_EXTERNAL", "shadow": "DEFERRED_EXTERNAL"},
        },
        "hashes": hashes,
        "failure_assertion": "F3 machine approval does not promote unavailable validator artifacts, production traffic, or external shadow evidence; those boundaries remain explicitly deferred.",
        "cleanup": "Aggregate report was generated from captured reports; no external validators, data, participants, credentials, or production state were created or modified.",
        "verdict": "APPROVE" if all_pairs_match else "REJECT",
    }
    _write(report_path, report)
    print(f"VERDICT: {report['verdict']}")
    return int(report["exit_code"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-file", required=True)
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--expect-exit", type=int, choices=(0, 1, 2))
    parser.add_argument("--expect-status", choices=sorted(STATUSES))
    parser.add_argument("--aggregate", nargs="+")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    return _aggregate(args) if args.aggregate else _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
