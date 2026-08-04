from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_benchmark import JsonValue, validate_benchmark

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/datasets/benchmark-v1.json"
FIXTURE = ROOT / "tests/fixtures/benchmark-duplicate-incident.json"
SCRIPT = ROOT / "scripts/run_benchmark.py"


def _load() -> dict[str, JsonValue]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_happy_manifest_verifies_immutable_hashes_and_pending_external_data() -> None:
    report = validate_benchmark(MANIFEST, check_leakage=True)

    assert report.status == "PASS"
    assert report.exit_code == 0
    assert report.metrics["final_test_hash_verified"] is True
    assert report.metrics["external_datasets_pending"] == 3
    assert report.metrics["real_data_execution"] == "DEFERRED_EXTERNAL"


def test_missing_split_hash_fails_closed(tmp_path: Path) -> None:
    manifest = _load()
    splits = manifest["splits"]
    assert isinstance(splits, dict)
    del splits["test_sha256"]
    path = tmp_path / "missing-hash.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_benchmark(path, check_leakage=False)

    assert report.status == "FAIL"
    assert any("test_sha256" in finding for finding in report.findings)


def test_preprocessing_fit_on_test_fails_closed(tmp_path: Path) -> None:
    manifest = _load()
    preprocessing = manifest["preprocessing"]
    assert isinstance(preprocessing, dict)
    normalization = preprocessing["normalization"]
    assert isinstance(normalization, dict)
    normalization["fit_partition"] = "test"
    path = tmp_path / "test-fit.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_benchmark(path, check_leakage=False)

    assert report.status == "FAIL"
    assert any("fit on test" in finding for finding in report.findings)


def test_duplicate_incident_failure_is_named_and_nonzero() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--manifest", str(FIXTURE), "--check-leakage"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "incident-hierarchy leakage" in result.stdout
