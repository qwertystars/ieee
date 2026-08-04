from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["backend/.venv/bin/python", "scripts/verify_release_gate.py", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_happy_gate_allows_explicit_deferred_claims() -> None:
    result = _run(
        "--manifest",
        "evidence/sota/release-manifest.json",
        "--prerequisites",
        "evidence/sota/prerequisites.json",
        "--require-signed-attestations",
        "--claim-class",
        "research,production",
        "--allow-deferred",
        "research,production,shadow,field",
    )
    assert result.returncode == 0
    assert '"research": "DEFERRED_EXTERNAL"' in result.stdout


def test_unallowed_deferred_production_is_a_failure() -> None:
    result = _run(
        "--manifest",
        "tests/fixtures/release-missing-evidence.json",
        "--claim-class",
        "production",
        "--allow-deferred",
        "none",
    )
    assert result.returncode == 1


def test_allowed_deferred_field_remains_external_status() -> None:
    result = _run(
        "--manifest",
        "tests/fixtures/release-missing-evidence.json",
        "--claim-class",
        "field",
        "--allow-deferred",
        "field",
    )
    assert result.returncode == 2
    assert "DEFERRED_EXTERNAL" in result.stdout


def test_tampered_file_hash_fails_closed(tmp_path: Path) -> None:
    manifest = json.loads((ROOT / "evidence/sota/release-manifest.json").read_text(encoding="utf-8"))
    manifest["claim_classes"]["research"]["package"]["file_hashes"]["code"]["scripts/reproduce_sota_report.py"] = "0" * 64
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = _run(
        "--manifest",
        str(path),
        "--claim-class",
        "research",
        "--allow-deferred",
        "research",
    )
    assert result.returncode == 1
    assert "hash mismatch" in result.stdout
