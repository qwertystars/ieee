from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "scripts" / "run_and_capture.py"
OPTIONAL = ROOT / "scripts" / "check_optional_dependencies.py"


def _run_capture(report: Path, cwd: Path, expected_exit: int, expected_status: str, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(CAPTURE),
            "--report-file",
            str(report),
            "--cwd",
            str(cwd),
            "--expect-exit",
            str(expected_exit),
            "--expect-status",
            expected_status,
            "--",
            command,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_capture_honors_explicit_cwd_and_shell_pipeline(tmp_path: Path) -> None:
    report = tmp_path / "capture.json"
    result = _run_capture(report, tmp_path, 0, "PASS", "printf 'ok\\n' | tr a-z A-Z")

    assert result.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["cwd"] == str(tmp_path)
    assert payload["exit_code"] == 0
    assert payload["status"] == "PASS"
    assert payload["metrics"]["stdout"] == "OK\n"
    assert payload["metrics"]["expected_pair_match"] is True
    assert payload["hashes"]["command_sha256"]


def test_capture_reports_unexpected_deferred_status_as_wrapper_failure(tmp_path: Path) -> None:
    report = tmp_path / "capture.json"
    result = _run_capture(report, tmp_path, 0, "PASS", "exit 2")

    assert result.returncode == 1
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["exit_code"] == 2
    assert payload["status"] == "DEFERRED_EXTERNAL"
    assert payload["metrics"]["expected_pair_match"] is False


def test_aggregate_accepts_only_matching_pairs(tmp_path: Path) -> None:
    first = tmp_path / "01.json"
    second = tmp_path / "02.json"
    aggregate = tmp_path / "report.json"
    assert _run_capture(first, tmp_path, 0, "PASS", "true").returncode == 0
    assert _run_capture(second, tmp_path, 2, "DEFERRED_EXTERNAL", "exit 2").returncode == 0

    result = subprocess.run(
        [
            sys.executable,
            str(CAPTURE),
            "--aggregate",
            f"{first},{second}",
            "--report-file",
            str(aggregate),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(aggregate.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["verdict"] == "APPROVE"
    assert payload["metrics"]["all_expected_pairs_match"] is True


def test_optional_dependency_simulation_is_truthfully_deferred() -> None:
    result = subprocess.run(
        [sys.executable, str(OPTIONAL), "--simulate-missing"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "status=DEFERRED_EXTERNAL" in result.stdout
    assert "simulated_missing" in result.stdout
