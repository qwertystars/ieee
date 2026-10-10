from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate_interoperability.py"
PROFILE = ROOT / "config/cap-profile-v1.2.yaml"
LOCK = ROOT / "config/validators.lock"
VALID = ROOT / "tests/fixtures/interoperability/valid"
INVALID = ROOT / "tests/fixtures/interoperability/invalid"
OFFLINE = ROOT / "tests/fixtures/interoperability/offline"
TAMPERED = ROOT / "tests/fixtures/validators-tampered.lock"


def _run(fixtures: Path, lock: Path = LOCK, offline: bool = False) -> subprocess.CompletedProcess[str]:
    command = ["backend/.venv/bin/python", str(SCRIPT), "--profile", str(PROFILE), "--lock", str(lock), "--fixtures", str(fixtures)]
    if offline:
        command.append("--offline")
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)


def test_valid_fixture_has_machine_pass_and_truthful_external_deferral() -> None:
    result = _run(VALID)

    assert result.returncode == 2
    assert "status=DEFERRED_EXTERNAL" in result.stdout
    assert "machine_conformance=PASS" in result.stdout
    assert "operational_interoperability=DEFERRED_EXTERNAL" in result.stdout


def test_invalid_fixture_fails_before_external_deferral() -> None:
    result = _run(INVALID, TAMPERED, offline=True)

    assert result.returncode == 1
    assert "status=FAIL" in result.stdout
    assert "validator lock integrity digest mismatch" in result.stdout


def test_invalid_fixture_rejects_contract_payloads_even_when_offline() -> None:
    result = _run(INVALID, offline=True)

    assert result.returncode == 1
    assert "status=FAIL" in result.stdout
    assert "missing or stale CAP message" in result.stdout


def test_offline_fixture_defers_without_network_access() -> None:
    result = _run(OFFLINE, offline=True)

    assert result.returncode == 2
    assert result.stdout.startswith("status=DEFERRED_EXTERNAL")
    assert "machine_conformance=PASS" in result.stdout
