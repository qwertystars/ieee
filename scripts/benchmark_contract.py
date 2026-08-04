"""Public facade for the leakage-safe Todo 14 benchmark contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.benchmark_contract_types import SPLITS, JsonObject, JsonValue
from scripts.benchmark_leakage import check_leakage as run_leakage_check
from scripts.benchmark_leakage import partition_records
from scripts.benchmark_manifest_input import (
    BenchmarkInputError,
    check_datasets,
    check_policy,
    check_records,
    is_object,
    read_manifest,
)
from scripts.benchmark_manifest_splits import (
    check_dataset_hashes,
    check_hashes,
    check_preprocessing,
)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    status: str
    exit_code: int
    findings: tuple[str, ...]
    metrics: JsonObject


def validate_benchmark(manifest_path: Path, check_leakage: bool) -> ValidationReport:
    """Validate the immutable split, preprocessing, and leakage contract."""
    manifest = read_manifest(manifest_path)
    findings: list[str] = []
    if manifest.get("schema_version") != "resqnet.benchmark-manifest.v1":
        findings.append("schema_version must be resqnet.benchmark-manifest.v1")
    if manifest.get("claim_policy") != "real-data execution requires artifact availability; offline fixture is validation-only":
        findings.append("claim_policy must forbid real-data claims from unavailable artifacts")
    check_datasets(manifest, findings)
    check_policy(manifest, findings)
    records = check_records(manifest, findings)
    computed = check_hashes(manifest, records, findings)
    check_dataset_hashes(manifest, records, findings)
    check_preprocessing(manifest, findings)
    if check_leakage:
        run_leakage_check(records, findings)
    datasets = manifest.get("datasets")
    pending = sum(1 for dataset in datasets if is_object(dataset) and dataset.get("status") == "DEFERRED_EXTERNAL") if isinstance(datasets, list) else 0
    metrics: JsonObject = {
        "records": len(records),
        "split_counts": {split: len(partition_records(records, split)) for split in SPLITS},
        "computed_split_hashes": computed,
        "final_test_hash_verified": not any("final_test_sha256" in finding for finding in findings),
        "real_data_execution": "DEFERRED_EXTERNAL" if pending else "AVAILABLE",
        "external_datasets_pending": pending,
        "synthetic_fixture_claim": "validation-only",
    }
    return ValidationReport("FAIL", 1, tuple(findings), metrics) if findings else ValidationReport("PASS", 0, (), metrics)


__all__ = ["BenchmarkInputError", "JsonObject", "JsonValue", "ValidationReport", "validate_benchmark"]
