from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/reproduce_sota_report.py"
MANIFEST = ROOT / "evidence/sota/release-manifest.json"
TAMPERED = ROOT / "tests/fixtures/tampered-release-manifest.json"


def test_clean_room_reports_machine_pass_without_external_sota_claim(tmp_path: Path) -> None:
    report = tmp_path / "task-19.json"
    result = subprocess.run(
        [
            "backend/.venv/bin/python",
            str(SCRIPT),
            "--manifest",
            str(MANIFEST),
            "--clean-room",
            "--report",
            str(report),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert result.stdout.strip() == "status=DEFERRED_EXTERNAL"
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "DEFERRED_EXTERNAL"
    assert payload["exit_code"] == 2
    assert payload["metrics"]["machine_gate_status"] == "PASS"
    assert payload["metrics"]["research_claim_status"] == "DEFERRED_EXTERNAL"
    assert payload["metrics"]["sota_claim"] is False


def test_tampered_release_manifest_fails_verification() -> None:
    result = subprocess.run(
        [
            "backend/.venv/bin/python",
            str(SCRIPT),
            "--manifest",
            str(TAMPERED),
            "--verify",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout.startswith("status=FAIL")
    assert "manifest integrity" in result.stdout
