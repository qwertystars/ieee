from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_exercise.py"
MACHINE = ROOT / "tests/fixtures/tabletop-machine-v1.yaml"
FAILURES = ROOT / "tests/fixtures/tabletop-machine-failures.yaml"
EXTERNAL = ROOT / "tests/fixtures/tabletop-external.yaml"
PREREQUISITES = ROOT / "evidence/sota/prerequisites.json"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["backend/.venv/bin/python", str(SCRIPT), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_machine_replay_passes_without_promoting_human_gate(tmp_path: Path) -> None:
    report = tmp_path / "machine.json"
    result = _run("--scenario", str(MACHINE), "--replay", "--report", str(report))

    assert result.returncode == 0
    assert result.stdout.strip() == "status=PASS"
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["metrics"]["machine_conformance"] == "PASS"
    assert payload["metrics"]["participant_tabletop"] == "DEFERRED_EXTERNAL"
    assert payload["metrics"]["interoperability"]["operational_interoperability"] == "DEFERRED_EXTERNAL"


def test_unsafe_machine_fixture_fails_closed() -> None:
    result = _run("--scenario", str(FAILURES), "--replay", "--assert-fail-closed")

    assert result.returncode == 1
    assert result.stdout.startswith("status=FAIL")
    assert "fail-closed" in result.stdout


def test_participant_tabletop_is_deferred_with_machine_boundary() -> None:
    result = _run(
        "--scenario",
        str(EXTERNAL),
        "--prerequisites",
        str(PREREQUISITES),
        "--expect-deferred",
        "participant-tabletop",
    )

    assert result.returncode == 2
    assert result.stdout.strip() == "status=DEFERRED_EXTERNAL"


def test_tabletop_report_has_exact_deferred_fields() -> None:
    report = json.loads((ROOT / "evidence/sota/tabletop-report.json").read_text(encoding="utf-8"))

    assert report["status"] == "DEFERRED_EXTERNAL"
    assert report["machine_pass_satisfies_participant_gate"] is False
    assert report["authorized_participants"] is None
    assert report["agency_roles"] is None
    assert report["scoring"] is None
    assert report["unresolved_risk_severity"] is None
    assert report["after_action_owners"] is None
    assert report["retest_dates"] is None
