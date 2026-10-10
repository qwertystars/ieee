"""Benchmark split hashes and preprocessing-fit checks."""

from __future__ import annotations

import re

from scripts.benchmark_contract_types import HASH_PATTERN, SPLITS, JsonObject
from scripts.benchmark_manifest_input import hash_ids, is_object


def check_hashes(manifest: JsonObject, records: list[JsonObject], findings: list[str]) -> dict[str, str]:
    splits = manifest.get("splits")
    if not is_object(splits):
        findings.append("splits must be an object")
        return {}
    records_by_id = {record.get("record_id"): record for record in records}
    computed: dict[str, str] = {}
    for split in SPLITS:
        raw_ids = splits.get(split)
        if not isinstance(raw_ids, list) or not raw_ids or not all(isinstance(item, str) for item in raw_ids):
            findings.append(f"splits.{split} must be a non-empty string array")
            continue
        ids = [item for item in raw_ids if isinstance(item, str)]
        if len(set(ids)) != len(ids):
            findings.append(f"splits.{split} contains duplicate record IDs")
        if sorted(set(ids) - set(records_by_id)):
            findings.append(f"splits.{split} references missing records")
        if set(ids) != {record.get("record_id") for record in records if record.get("split") == split}:
            findings.append(f"splits.{split} does not match each record's declared split")
        computed[split] = hash_ids(ids)
        expected_hash = splits.get(f"{split}_sha256")
        if not isinstance(expected_hash, str) or not re.fullmatch(HASH_PATTERN, expected_hash):
            findings.append(f"splits.{split}_sha256 must be an immutable SHA-256 hash")
        elif expected_hash != computed[split]:
            findings.append(f"splits.{split}_sha256 does not match canonical record IDs")
    final_hash = manifest.get("final_test_sha256")
    if not isinstance(final_hash, str) or not re.fullmatch(HASH_PATTERN, final_hash):
        findings.append("final_test_sha256 must be an immutable SHA-256 hash")
    elif computed.get("test") != final_hash:
        findings.append("final_test_sha256 does not match the test split")
    pairs = (("train", "calibration"), ("train", "test"), ("calibration", "test"))
    if any(set(splits.get(first, [])) & set(splits.get(second, [])) for first, second in pairs):
        findings.append("split membership is not immutable and disjoint")
    return computed


def check_dataset_hashes(manifest: JsonObject, records: list[JsonObject], findings: list[str]) -> None:
    datasets = manifest.get("datasets")
    if not isinstance(datasets, list):
        return
    for index, raw in enumerate(datasets):
        if not is_object(raw):
            continue
        dataset_id, split_hashes = raw.get("dataset_id"), raw.get("split_hashes")
        if not isinstance(dataset_id, str) or not is_object(split_hashes):
            findings.append(f"datasets[{index}].split_hashes must contain train/calibration/test hashes")
            continue
        for split in SPLITS:
            ids = [record["record_id"] for record in records if record.get("dataset_id") == dataset_id and record.get("split") == split and isinstance(record.get("record_id"), str)]
            expected = split_hashes.get(split)
            if not isinstance(expected, str) or not re.fullmatch(HASH_PATTERN, expected):
                findings.append(f"datasets[{index}].split_hashes.{split} is absent or not SHA-256")
            elif expected != hash_ids(ids):
                findings.append(f"datasets[{index}].split_hashes.{split} does not match its records")


def check_preprocessing(manifest: JsonObject, findings: list[str]) -> None:
    preprocessing, fit_rules = manifest.get("preprocessing"), manifest.get("fit_partitions")
    if not is_object(preprocessing):
        findings.append("preprocessing must be an object")
    else:
        for name, raw in preprocessing.items():
            partition = raw.get("fit_partition") if is_object(raw) else None
            if partition == "test":
                findings.append(f"preprocessing.{name} is fit on test")
            elif partition not in {"train", "calibration", "none"}:
                findings.append(f"preprocessing.{name}.fit_partition is invalid")
    if not is_object(fit_rules):
        findings.append("fit_partitions must be an object")
    else:
        for name, partition in fit_rules.items():
            if partition == "test":
                findings.append(f"fit_partitions.{name} is fit on test")
            elif partition not in {"train", "calibration", "none"}:
                findings.append(f"fit_partitions.{name} is invalid")
