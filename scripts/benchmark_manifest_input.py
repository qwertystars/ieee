"""Benchmark fixture loading and dataset/record contract checks."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from scripts.benchmark_contract_types import (
    COMMIT_PATTERN,
    HASH_PATTERN,
    PINNED_DATASETS,
    SPLITS,
    JsonObject,
    JsonValue,
)

BenchmarkInputError = ValueError


def is_object(value: JsonValue) -> bool:
    return isinstance(value, dict)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_ids(ids: list[str]) -> str:
    canonical = json.dumps(sorted(ids), separators=(",", ":"), ensure_ascii=True)
    return sha256(canonical)


def read_manifest(path: Path) -> JsonObject:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BenchmarkInputError(f"{path}: invalid JSON: {error}") from error
    if not is_object(parsed):
        raise BenchmarkInputError(f"{path}: top-level value must be an object")
    if not isinstance(parsed.get("source"), str) or not isinstance(parsed.get("mutation"), str):
        return parsed
    source = read_manifest((path.parent / parsed["source"]).resolve())
    records = source.get("records")
    if not isinstance(records, list):
        raise BenchmarkInputError(f"{path}: fixture source records are missing")
    if parsed["mutation"] == "remove dataset xbd-damage":
        source["datasets"] = [dataset for dataset in source.get("datasets", []) if not isinstance(dataset, dict) or dataset.get("dataset_id") != "xbd-damage"]
        return source
    if parsed["mutation"] != "test record sen-test-01 shares incident_id with sen-train-01":
        raise BenchmarkInputError(f"{path}: unsupported or incomplete fixture mutation")
    train = next((record for record in records if isinstance(record, dict) and record.get("record_id") == "sen-train-01"), None)
    test = next((record for record in records if isinstance(record, dict) and record.get("record_id") == "sen-test-01"), None)
    if not isinstance(train, dict) or not isinstance(test, dict):
        raise BenchmarkInputError(f"{path}: fixture mutation records are missing")
    test["incident_id"] = train["incident_id"]
    return source


def text(record: JsonObject, field: str, path: str, findings: list[str]) -> str | None:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        findings.append(f"{path}.{field} must be a non-empty string")
        return None
    return value


def check_datasets(manifest: JsonObject, findings: list[str]) -> None:
    datasets = manifest.get("datasets")
    if not isinstance(datasets, list):
        findings.append("datasets must be an array")
        return
    seen: set[str] = set()
    for index, raw in enumerate(datasets):
        path = f"datasets[{index}]"
        if not is_object(raw):
            findings.append(f"{path} must be an object")
            continue
        dataset_id, immutable_id = text(raw, "dataset_id", path, findings), text(raw, "immutable_id", path, findings)
        if dataset_id is None:
            continue
        if dataset_id in seen:
            findings.append(f"{path}.dataset_id is duplicated")
        seen.add(dataset_id)
        expected = PINNED_DATASETS.get(dataset_id)
        if expected is None:
            findings.append(f"{path}.dataset_id is not an approved benchmark dataset")
        elif immutable_id != expected:
            findings.append(f"{path}.immutable_id is not the exact pinned benchmark commit")
        commit = immutable_id.rsplit("@", 1)[-1] if immutable_id else ""
        if not re.fullmatch(COMMIT_PATTERN, commit):
            findings.append(f"{path}.immutable_id must end in a 40-character commit")
        status, available, artifact_hash = raw.get("status"), raw.get("artifact_available"), raw.get("artifact_sha256")
        if status not in {"AVAILABLE", "DEFERRED_EXTERNAL"}:
            findings.append(f"{path}.status must be AVAILABLE or DEFERRED_EXTERNAL")
        if not isinstance(available, bool):
            findings.append(f"{path}.artifact_available must be boolean")
        if available and (not isinstance(artifact_hash, str) or not re.fullmatch(HASH_PATTERN, artifact_hash)):
            findings.append(f"{path}.available artifact requires a SHA-256 hash")
        if not available and artifact_hash is not None:
            findings.append(f"{path}.unavailable artifact cannot claim an artifact hash")
        reference = raw.get("artifact_reference")
        if isinstance(reference, str) and ("/" in reference or reference in {"main", "master", "latest"}):
            findings.append(f"{path}.artifact_reference must be immutable, not a mutable path")
        for field in ("source_url", "license_name", "license_authority", "preprocessing_version", "crs", "resolution"):
            text(raw, field, path, findings)
        if status == "DEFERRED_EXTERNAL" and raw.get("pending_reason") in {None, ""}:
            findings.append(f"{path}.pending_reason is required for unavailable external data")


def check_policy(manifest: JsonObject, findings: list[str]) -> None:
    policy = manifest.get("split_policy")
    expected = {"unit": "incident", "temporal_cutoff": "2024-01-01T00:00:00Z", "h3_resolution": 8, "spatial_buffer_km": 10, "assignment_seed": 2025}
    if not is_object(policy):
        findings.append("split_policy must be an object")
        return
    for field, value in expected.items():
        if policy.get(field) != value:
            findings.append(f"split_policy.{field} must be {value!r}")
    if policy.get("spatial_distance_method") != "geodesic_haversine":
        findings.append("split_policy.spatial_distance_method must be geodesic_haversine")
    if policy.get("calibration_examples_per_group") != 200:
        findings.append("split_policy.calibration_examples_per_group must be 200")


def check_records(manifest: JsonObject, findings: list[str]) -> list[JsonObject]:
    raw_records = manifest.get("records")
    if not isinstance(raw_records, list):
        findings.append("records must be an array")
        return []
    records: list[JsonObject] = []
    seen: set[str] = set()
    fields = ("dataset_id", "incident_id", "event_id", "parent_incident_id", "source_id", "source_asset_id", "tile_id")
    for index, raw in enumerate(raw_records):
        path = f"records[{index}]"
        if not is_object(raw):
            findings.append(f"{path} must be an object")
            continue
        record_id, split = text(raw, "record_id", path, findings), text(raw, "split", path, findings)
        for field in fields:
            text(raw, field, path, findings)
        digest, phash, timestamp = text(raw, "sha256", path, findings), text(raw, "phash", path, findings), text(raw, "acquired_at", path, findings)
        if digest is not None and not re.fullmatch(HASH_PATTERN, digest):
            findings.append(f"{path}.sha256 must be a lowercase SHA-256 digest")
        if phash is not None and not re.fullmatch(r"^[0-9a-f]{16}$", phash):
            findings.append(f"{path}.phash must be a 64-bit hexadecimal pHash")
        if timestamp is not None:
            try:
                parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError
            except ValueError:
                findings.append(f"{path}.acquired_at must be timezone-aware ISO-8601")
        for field in ("latitude", "longitude"):
            value = raw.get(field)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                findings.append(f"{path}.{field} must be numeric")
        if split not in SPLITS:
            findings.append(f"{path}.split must be train, calibration, or test")
        if record_id is not None:
            if record_id in seen:
                findings.append(f"{path}.record_id is duplicated")
            seen.add(record_id)
        records.append(raw)
    return records
