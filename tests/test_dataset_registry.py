from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.validate_dataset_registry import (
    JsonValue,
    ValidationOptions,
    validate_registry,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/datasets/registry.json"
PREREQUISITES = ROOT / "evidence/sota/prerequisites.json"


def _load_manifest() -> dict[str, JsonValue]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_registry_catalog_is_valid_with_required_contracts() -> None:
    report = validate_registry(
        MANIFEST,
        PREREQUISITES,
        ValidationOptions(
            require_license=True,
            require_hashes=True,
            require_split_metadata=True,
            require_claim_classes=True,
        ),
    )

    assert report.status == "PASS"
    assert report.errors == ()


def test_missing_license_is_deferred_as_not_permitted() -> None:
    report = validate_registry(
        ROOT / "tests/fixtures/registry-missing-license.json",
        ROOT / "tests/fixtures/prerequisites-expired.json",
        ValidationOptions(),
    )

    assert report.status == "DEFERRED_EXTERNAL"
    assert report.exit_code == 2
    assert report.deferred_reason == "license_not_permitted"


def test_revoked_dataset_fails_closed(tmp_path: Path) -> None:
    manifest = _load_manifest()
    datasets = manifest["datasets"]
    assert isinstance(datasets, list)
    revoked = copy.deepcopy(datasets[0])
    assert isinstance(revoked, dict)
    revoked["status"] = "REVOKED"
    revoked["revoked_at"] = "2026-08-01T00:00:00Z"
    manifest["datasets"] = [revoked]
    manifest_path = tmp_path / "revoked.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_registry(manifest_path, PREREQUISITES, ValidationOptions())

    assert report.status == "FAIL"
    assert report.exit_code == 1
    assert any("revoked" in error for error in report.errors)


def test_immutable_id_cannot_change_artifact_hash(tmp_path: Path) -> None:
    manifest = _load_manifest()
    datasets = manifest["datasets"]
    assert isinstance(datasets, list)
    first = copy.deepcopy(datasets[0])
    assert isinstance(first, dict)
    first["artifact_available"] = True
    first["artifact_sha256"] = "a" * 64
    second = copy.deepcopy(first)
    second["dataset_id"] = "same-id-different-record"
    second["artifact_sha256"] = "b" * 64
    manifest["datasets"] = [first, second]
    manifest_path = tmp_path / "immutable.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_registry(manifest_path, PREREQUISITES, ValidationOptions())

    assert report.status == "FAIL"
    assert any("immutable_id" in error and "hash" in error for error in report.errors)


def test_gated_data_has_no_silent_artifact_substitution() -> None:
    manifest = _load_manifest()
    datasets = manifest["datasets"]
    assert isinstance(datasets, list)
    gated = [
        dataset
        for dataset in datasets
        if isinstance(dataset, dict) and dataset["gating"]["mode"] != "public"
    ]

    assert gated
    assert all(dataset["artifact_available"] is False for dataset in gated)
    assert all(dataset["artifact_sha256"] is None for dataset in gated)
