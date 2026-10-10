from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_field_exercise_harness.py"
MACHINE = ROOT / "tests/fixtures/field-machine-v1.yaml"
FAILURES = ROOT / "tests/fixtures/field-machine-failures.yaml"
EXTERNAL = ROOT / "tests/fixtures/field-external.yaml"
PREREQUISITES = ROOT / "evidence/sota/prerequisites.json"
FIELD_REPORT = ROOT / "evidence/sota/field-trial-report.json"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["backend/.venv/bin/python", str(SCRIPT), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_machine_fixture_passes_fixed_thresholds_and_replay(tmp_path: Path) -> None:
    report = tmp_path / "task-26-machine.json"
    result = _run(
        "--scenario",
        str(MACHINE),
        "--replay",
        "--report",
        str(report),
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "status=PASS"
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["task_id"] == "26"
    assert payload["metrics"]["machine_gate_status"] == "PASS"
    assert payload["metrics"]["signed_log"]["integrity"] == "PASS"
    assert payload["metrics"]["replay"]["deterministic"] is True
    assert payload["metrics"]["no_actuation"] is True
    assert payload["metrics"]["external_field_claim"] == "DEFERRED_EXTERNAL"


def test_unsafe_machine_fixture_fails_closed_with_remediation() -> None:
    result = _run(
        "--scenario",
        str(FAILURES),
        "--assert-safe-degradation",
    )

    assert result.returncode == 1
    assert result.stdout.startswith("status=FAIL")
    assert "finding=" in result.stdout
    assert "remediation=" in result.stdout
    assert "actuation" in result.stdout


def test_external_field_trial_remains_deferred_without_fabrication() -> None:
    result = _run(
        "--scenario",
        str(EXTERNAL),
        "--prerequisites",
        str(PREREQUISITES),
        "--require-agency-hardware",
        "--expect-deferred",
    )

    assert result.returncode == 2
    assert result.stdout.strip() == "status=DEFERRED_EXTERNAL"


def test_field_report_is_hashed_deferred_schema_artifact() -> None:
    report = json.loads(FIELD_REPORT.read_text(encoding="utf-8"))

    assert report["status"] == "DEFERRED_EXTERNAL"
    assert report["machine_pass_satisfies_field_gate"] is False
    assert report["agency_authorization"] is None
    assert report["ethics_irb"] is None
    assert report["training"] is None
    assert report["insurance_safety_review"] is None
    assert report["device_inventory"] is None
    assert report["consent"] is None
    assert report["stop_authority"] is None
    assert report["sample_hazard_minimums"]["minimum_incidents"] == 100
    assert report["sample_hazard_minimums"]["minimum_hazard_types"] == 3
    assert report["sample_hazard_minimums"]["observed_incidents"] is None
    assert report["blinding"] is None
    assert report["missing_data_rules"] is None
