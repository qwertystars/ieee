from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_sensor_harness.py"
VALID = ROOT / "tests/fixtures/sensor-valid.ndjson"
FAILURES = ROOT / "tests/fixtures/sensor-failures.ndjson"
PHYSICAL = ROOT / "tests/fixtures/sensor-physical-required.ndjson"
PREREQUISITES = ROOT / "evidence/sota/prerequisites.json"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["backend/.venv/bin/python", str(SCRIPT), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_valid_signed_sequence_fixture_passes_protocol_gate(tmp_path: Path) -> None:
    report = tmp_path / "task-25-machine.json"
    result = _run(
        "--fixture",
        str(VALID),
        "--verify-signature",
        "--verify-sequence",
        "--report",
        str(report),
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "status=PASS"
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["task_id"] == "25"
    assert payload["metrics"]["protocol_contract"] == "PASS"
    assert payload["metrics"]["accepted_records"] == 6
    assert payload["metrics"]["quarantined_records"] == 0
    assert payload["metrics"]["physical_claim"] == "DEFERRED_EXTERNAL"


def test_unsafe_fixture_quarantines_records_and_fails_closed() -> None:
    result = _run("--fixture", str(FAILURES), "--assert-quarantine")

    assert result.returncode == 1
    assert result.stdout.startswith("status=FAIL")
    assert "quarantine" in result.stdout


def test_physical_prerequisites_remain_deferred(tmp_path: Path) -> None:
    report = tmp_path / "physical.json"
    result = _run(
        "--fixture",
        str(PHYSICAL),
        "--prerequisites",
        str(PREREQUISITES),
        "--require-physical",
        "--expect-deferred",
        "--report",
        str(report),
    )

    assert result.returncode == 2
    assert result.stdout.strip() == "status=DEFERRED_EXTERNAL"
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["metrics"]["protocol_contract"] == "PASS"
    assert payload["metrics"]["physical_claim"] == "DEFERRED_EXTERNAL"
    assert set(payload["metrics"]["missing_physical_evidence"]) == {
        "secure_boot",
        "physical_calibration",
        "environmental_limits",
        "real_key_custody",
    }


def test_invalid_signature_is_not_counted_as_accepted() -> None:
    result = _run("--fixture", str(FAILURES), "--verify-signature")

    assert result.returncode == 1
    assert "signature" in result.stdout
