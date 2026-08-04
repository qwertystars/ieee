#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, TypeAlias, TypeGuard

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

DATASET_STATUSES: Final = {"AVAILABLE", "DEFERRED_EXTERNAL", "REVOKED"}
PREREQUISITE_STATUSES: Final = {"NOT_ATTEMPTED", "AVAILABLE", "PASSED", "FAILED", "DEFERRED_EXTERNAL", "REVOKED"}
CLAIM_CLASSES: Final = {"research", "production", "shadow", "field"}
GOVERNANCE_STATUSES: Final = {"NOT_REQUIRED", "PENDING", "PASSED", "FAILED"}
HASH_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
DATASET_FIELDS: Final = ("dataset_id", "dataset_type", "immutable_id", "version", "preprocessing_version", "artifact_sha256", "artifact_available", "source_authority", "source_url", "license_name", "license_version", "license_authority", "allowed_use_status", "status", "geography", "events", "label_schema", "crs", "split_metadata", "consent_status", "irb_status", "geographic_privacy", "claim_classes", "expires_at", "revoked_at", "gating", "prerequisite_id")
PREREQUISITE_FIELDS: Final = {"id", "owner", "authority", "status", "evidence_type", "evidence_hash", "hash_algorithm", "source_url", "recorded_at", "expires_at", "depends_on", "deferred_reason", "claim_classes"}
EVIDENCE_TYPE_FIELDS: Final = {"kind", "consent_status", "IRB_status", "geographic_privacy_status", "validator_status", "key_custody_status"}


@dataclass(frozen=True, slots=True)
class ValidationOptions:
    require_license: bool = False
    require_hashes: bool = False
    require_split_metadata: bool = False
    require_claim_classes: bool = False


@dataclass(frozen=True, slots=True)
class ValidationReport:
    status: str
    exit_code: int
    errors: tuple[str, ...]
    deferred_reason: str | None


class RegistryInputError(ValueError):
    pass


def _is_object(value: JsonValue) -> TypeGuard[JsonObject]:
    return isinstance(value, dict)


def _read_json(path: Path) -> JsonValue:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryInputError(f"{path}: invalid JSON: {error}") from error
    if not isinstance(value, (dict, list)):
        raise RegistryInputError(f"{path}: top-level JSON value must be an object or array")
    return value


def _objects(value: JsonValue, path: str, errors: list[str]) -> list[JsonObject]:
    if not isinstance(value, list):
        errors.append(f"{path} must be an array")
        return []
    result: list[JsonObject] = []
    for index, item in enumerate(value):
        if _is_object(item):
            result.append(item)
        else:
            errors.append(f"{path}[{index}] must be an object")
    return result


def _text(record: JsonObject, field: str, path: str, errors: list[str], *, nullable: bool = False) -> str | None:
    value = record.get(field)
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}.{field} must be a non-empty string")
        return None
    return value


def _iso(value: JsonValue, path: str, errors: list[str], *, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        errors.append(f"{path} must be an ISO-8601 timestamp")
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{path} must be an ISO-8601 timestamp")
        return None
    if timestamp.tzinfo is None:
        errors.append(f"{path} must include a timezone")
        return None
    return timestamp


def _hash(value: JsonValue, path: str, errors: list[str], *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        errors.append(f"{path} must be a lowercase SHA-256 hex digest")
        return None
    return value


def _claims(value: JsonValue, path: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        errors.append(f"{path} must be a non-empty string array")
        return
    invalid = set(value) - CLAIM_CLASSES
    if invalid:
        errors.append(f"{path} contains unknown claim classes: {sorted(invalid)}")


def _validate_dataset(record: JsonObject, index: int, options: ValidationOptions, errors: list[str], deferred: list[str], seen: dict[str, tuple[str | None, str]]) -> None:
    path = f"datasets[{index}]"
    missing = set(DATASET_FIELDS) - set(record)
    errors.extend(f"{path} missing required field {field}" for field in sorted(missing))
    _text(record, "dataset_id", path, errors)
    immutable_id = _text(record, "immutable_id", path, errors)
    version = _text(record, "version", path, errors)
    _text(record, "dataset_type", path, errors)
    _text(record, "preprocessing_version", path, errors)
    _text(record, "source_url", path, errors)
    status = record.get("status")
    allowed = record.get("allowed_use_status")
    artifact_available = record.get("artifact_available")
    artifact_hash = _hash(record.get("artifact_sha256"), path + ".artifact_sha256", errors, nullable=True)
    if not isinstance(artifact_available, bool):
        errors.append(f"{path}.artifact_available must be boolean")
        artifact_available = False
    if artifact_available and artifact_hash is None: errors.append(f"{path} available artifacts require artifact_sha256")
    if not artifact_available and artifact_hash is not None: errors.append(f"{path} unavailable artifacts cannot claim artifact_sha256")
    if status not in DATASET_STATUSES:
        errors.append(f"{path}.status is not a supported dataset status")
    if not isinstance(allowed, str) or allowed not in {"ALLOWED", "PENDING_AUTHORIZATION", "NOT_PERMITTED", "UNKNOWN", "REVOKED"}:
        errors.append(f"{path}.allowed_use_status is not explicit")
    if status == "REVOKED": errors.append(f"{path} is revoked and cannot execute")
    if status == "AVAILABLE" and (not artifact_available or allowed != "ALLOWED"): errors.append(f"{path} available status requires an artifact and permitted license")
    if allowed == "NOT_PERMITTED" and (artifact_available or status == "AVAILABLE"): errors.append(f"{path} is not permitted for execution")
    if status == "DEFERRED_EXTERNAL" and allowed in {"NOT_PERMITTED", "PENDING_AUTHORIZATION"}:
        deferred.append("license_not_permitted")
    for field in ("source_authority", "license_name", "license_authority"):
        _text(record, field, path, errors, nullable=False)
    for field in ("geography", "label_schema", "split_metadata", "geographic_privacy", "gating"):
        if not _is_object(record.get(field)):
            errors.append(f"{path}.{field} must be an object")
    if not isinstance(record.get("events"), list):
        errors.append(f"{path}.events must be an array")
    _text(record, "crs", path, errors)
    for field in ("consent_status", "irb_status"):
        if record.get(field) not in GOVERNANCE_STATUSES:
            errors.append(f"{path}.{field} is not a supported governance status")
    privacy = record.get("geographic_privacy")
    if _is_object(privacy) and (privacy.get("status") not in GOVERNANCE_STATUSES or not isinstance(privacy.get("method"), str)):
        errors.append(f"{path}.geographic_privacy must declare status and method")
    split = record.get("split_metadata")
    if _is_object(split):
        split_hash = _hash(split.get("hash"), path + ".split_metadata.hash", errors, nullable=True)
        if options.require_split_metadata and split.get("status") != "UNAVAILABLE" and split_hash is None:
            errors.append(f"{path}.split_metadata requires an immutable hash")
        if artifact_available and split_hash is None:
            errors.append(f"{path} available artifacts require split metadata hash")
    _claims(record.get("claim_classes"), path + ".claim_classes", errors)
    _iso(record.get("expires_at"), path + ".expires_at", errors, nullable=True)
    revoked_at = _iso(record.get("revoked_at"), path + ".revoked_at", errors, nullable=True)
    if status != "REVOKED" and revoked_at is not None:
        errors.append(f"{path}.revoked_at requires REVOKED status")
    if immutable_id is not None and version is not None:
        prior = seen.get(immutable_id)
        if prior is not None and prior != (artifact_hash, version):
            errors.append(f"{path} immutable_id changed artifact hash or version")
        seen[immutable_id] = (artifact_hash, version)


def _validate_prerequisite(record: JsonObject, index: int, errors: list[str], deferred: list[str], now: datetime) -> str | None:
    path = f"prerequisites[{index}]"
    if set(record) != PREREQUISITE_FIELDS:
        errors.append(f"{path} must contain exactly the 13 prerequisite fields")
    identifier = _text(record, "id", path, errors)
    for field in ("owner", "authority", "hash_algorithm", "source_url"):
        _text(record, field, path, errors)
    status = record.get("status")
    if status not in PREREQUISITE_STATUSES:
        errors.append(f"{path}.status is not supported")
    evidence = record.get("evidence_type")
    if not _is_object(evidence) or set(evidence) != EVIDENCE_TYPE_FIELDS:
        errors.append(f"{path}.evidence_type must contain exactly six typed fields")
    elif evidence.get("kind") is not None and not isinstance(evidence.get("kind"), str): errors.append(f"{path}.evidence_type.kind must be a string")
    if _is_object(evidence):
        for field in EVIDENCE_TYPE_FIELDS - {"kind"}:
            if evidence.get(field) not in GOVERNANCE_STATUSES:
                errors.append(f"{path}.evidence_type.{field} is not supported")
    if record.get("hash_algorithm") != "SHA-256":
        errors.append(f"{path}.hash_algorithm must be SHA-256")
    evidence_hash = _hash(record.get("evidence_hash"), path + ".evidence_hash", errors, nullable=True)
    if status in {"AVAILABLE", "PASSED"} and evidence_hash is None:
        errors.append(f"{path} available or passed evidence requires evidence_hash")
    if status in {"REVOKED", "FAILED"}: errors.append(f"{path} status {status} blocks execution")
    _iso(record.get("recorded_at"), path + ".recorded_at", errors)
    expires_at = _iso(record.get("expires_at"), path + ".expires_at", errors, nullable=True)
    if expires_at is not None and expires_at <= now:
        errors.append(f"{path} evidence is expired")
        deferred.append("prerequisite_expired")
    if status == "DEFERRED_EXTERNAL":
        reason = record.get("deferred_reason")
        if not isinstance(reason, str) or not reason:
            errors.append(f"{path}.deferred_reason is required for DEFERRED_EXTERNAL")
        elif reason == "license_not_permitted":
            deferred.append(reason)
    elif record.get("deferred_reason") is not None:
        errors.append(f"{path}.deferred_reason must be null unless deferred")
    if not isinstance(record.get("depends_on"), list) or not all(isinstance(item, str) for item in record["depends_on"]):
        errors.append(f"{path}.depends_on must be a string array")
    _claims(record.get("claim_classes"), path + ".claim_classes", errors)
    return identifier


def validate_registry(manifest_path: Path, prerequisites_path: Path, options: ValidationOptions) -> ValidationReport:
    errors: list[str] = []
    deferred: list[str] = []
    manifest = _read_json(manifest_path)
    prerequisites = _read_json(prerequisites_path)
    if not _is_object(manifest):
        errors.append("manifest must be an object")
        datasets: list[JsonObject] = []
    else:
        datasets = _objects(manifest.get("datasets"), "datasets", errors)
    if _is_object(prerequisites):
        prerequisite_value = prerequisites.get("prerequisites")
    else:
        prerequisite_value = prerequisites
    prerequisite_records = _objects(prerequisite_value, "prerequisites", errors)
    seen: dict[str, tuple[str | None, str]] = {}
    for index, record in enumerate(datasets):
        _validate_dataset(record, index, options, errors, deferred, seen)
    now = datetime.now(timezone.utc)
    prerequisite_ids = {identifier for index, record in enumerate(prerequisite_records) if (identifier := _validate_prerequisite(record, index, errors, deferred, now)) is not None}
    for index, record in enumerate(datasets):
        prerequisite_id = record.get("prerequisite_id")
        if isinstance(prerequisite_id, str) and prerequisite_id not in prerequisite_ids:
            errors.append(f"datasets[{index}].prerequisite_id is not registered")
    blocked = any("revoked" in error or "not permitted for execution" in error or "status FAILED" in error or "status REVOKED" in error or "immutable_id changed" in error for error in errors)
    if blocked:
        return ValidationReport("FAIL", 1, tuple(errors), None)
    if errors and deferred:
        reason = "license_not_permitted" if "license_not_permitted" in deferred else deferred[0]
        return ValidationReport("DEFERRED_EXTERNAL", 2, tuple(errors), reason)
    if errors:
        return ValidationReport("FAIL", 1, tuple(errors), None)
    return ValidationReport("PASS", 0, (), None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate ResQNet dataset licenses and provenance")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--prerequisites", type=Path, required=True)
    parser.add_argument("--require-license", action="store_true")
    parser.add_argument("--require-hashes", action="store_true")
    parser.add_argument("--require-split-metadata", action="store_true")
    parser.add_argument("--require-claim-classes", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = validate_registry(
            args.manifest,
            args.prerequisites,
            ValidationOptions(args.require_license, args.require_hashes, args.require_split_metadata, args.require_claim_classes),
        )
    except RegistryInputError as error:
        print(f"status=FAIL\nerror={error}")
        return 1
    print(f"status={report.status}")
    if report.deferred_reason is not None:
        print(f"deferred_reason={report.deferred_reason}")
    for error in report.errors:
        print(f"error={error}")
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
