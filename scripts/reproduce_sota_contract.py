"""Typed boundary helpers for the reproducibility release contract."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

ROOT: Final = Path(__file__).resolve().parents[1]
HASH_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
CLAIMS: Final = ("research", "production", "shadow", "field")
PREREQUISITE_STATUSES: Final = {"NOT_ATTEMPTED", "AVAILABLE", "PASSED", "FAILED", "DEFERRED_EXTERNAL", "REVOKED"}


class ManifestInputError(ValueError):
    """Identifies a malformed, expired, or tampered release package."""


def read_json(path: Path) -> JsonValue:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestInputError(f"{path}: invalid JSON: {error}") from error


def as_object(value: JsonValue, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ManifestInputError(f"{label} must be a JSON object")
    return value


def text(value: JsonValue, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestInputError(f"{label} must be a non-empty string")
    return value


def digest(value: JsonValue, label: str) -> str:
    value_text = text(value, label)
    if HASH_PATTERN.fullmatch(value_text) is None:
        raise ManifestInputError(f"{label} must be a lowercase SHA-256 digest")
    return value_text


def timestamp(value: JsonValue, label: str, *, future: bool = False) -> datetime:
    value_text = text(value, label)
    if not value_text.endswith("Z"):
        raise ManifestInputError(f"{label} must be a UTC ISO-8601 timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value_text[:-1] + "+00:00")
    except ValueError as error:
        raise ManifestInputError(f"{label} must be a UTC ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ManifestInputError(f"{label} must be UTC")
    if future and parsed <= datetime.now(timezone.utc):
        raise ManifestInputError(f"{label} is expired")
    return parsed


def canonical(value: JsonValue) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ManifestInputError(f"missing or unreadable input {path}: {error}") from error


def relative_path(value: JsonValue, label: str) -> Path:
    value_text = text(value, label)
    path = Path(value_text)
    if path.is_absolute() or ".." in path.parts:
        raise ManifestInputError(f"{label} must be a repository-relative path")
    return path


def validate_prerequisites(source: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    value = read_json(source)
    records = value if isinstance(value, list) else as_object(value, "prerequisite register").get("prerequisites")
    if not isinstance(records, list):
        raise ManifestInputError("prerequisite register must be an array")
    required = {"id", "owner", "authority", "status", "evidence_type", "evidence_hash", "hash_algorithm", "source_url", "recorded_at", "expires_at", "depends_on", "deferred_reason", "claim_classes"}
    evidence_fields = {"kind", "consent_status", "IRB_status", "geographic_privacy_status", "validator_status", "key_custody_status"}
    governance = {"NOT_REQUIRED", "PENDING", "PASSED", "FAILED"}
    statuses: dict[str, str] = {}
    claims: dict[str, list[str]] = {claim: [] for claim in CLAIMS}
    for index, item in enumerate(records):
        record = as_object(item, f"prerequisites[{index}]")
        if set(record) != required:
            raise ManifestInputError(f"prerequisites[{index}] must contain exactly the 13 prerequisite fields")
        identifier = text(record.get("id"), f"prerequisites[{index}].id")
        status = text(record.get("status"), f"prerequisites[{index}].status")
        if status not in PREREQUISITE_STATUSES:
            raise ManifestInputError(f"prerequisites[{index}].status is unsupported")
        evidence = as_object(record.get("evidence_type"), f"prerequisites[{index}].evidence_type")
        if set(evidence) != evidence_fields or any(evidence.get(field) not in governance for field in evidence_fields - {"kind"}):
            raise ManifestInputError(f"prerequisites[{index}].evidence_type is invalid")
        text(evidence.get("kind"), f"prerequisites[{index}].evidence_type.kind")
        timestamp(record.get("recorded_at"), f"prerequisites[{index}].recorded_at")
        expiry = record.get("expires_at")
        if expiry is not None:
            timestamp(expiry, f"prerequisites[{index}].expires_at", future=True)
        if record.get("hash_algorithm") != "SHA-256":
            raise ManifestInputError(f"prerequisites[{index}].hash_algorithm must be SHA-256")
        if status in {"AVAILABLE", "PASSED"} or record.get("evidence_hash") is not None:
            digest(record.get("evidence_hash"), f"prerequisites[{index}].evidence_hash")
        if status == "DEFERRED_EXTERNAL":
            text(record.get("deferred_reason"), f"prerequisites[{index}].deferred_reason")
        elif record.get("deferred_reason") is not None:
            raise ManifestInputError(f"prerequisites[{index}].deferred_reason must be null unless deferred")
        dependencies = record.get("depends_on")
        claim_values = record.get("claim_classes")
        if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
            raise ManifestInputError(f"prerequisites[{index}].depends_on must be a string array")
        if not isinstance(claim_values, list) or not claim_values or not all(isinstance(item, str) and item in CLAIMS for item in claim_values):
            raise ManifestInputError(f"prerequisites[{index}].claim_classes is invalid")
        statuses[identifier] = status
        for claim in claim_values:
            claims[claim].append(identifier)
    return statuses, claims


def validate_files(package: JsonObject) -> tuple[dict[str, str], list[str]]:
    files = as_object(package.get("file_hashes"), "package.file_hashes")
    flattened: dict[str, str] = {}
    findings: list[str] = []
    for category, values in files.items():
        category_files = as_object(values, f"package.file_hashes.{category}")
        for raw_path, expected in category_files.items():
            path = relative_path(raw_path, f"package.file_hashes.{category}")
            expected_digest = digest(expected, f"package.file_hashes.{category}.{raw_path}")
            flattened[str(path)] = expected_digest
            if sha256_file(ROOT / path) != expected_digest:
                findings.append(f"hash mismatch for {path}")
    return flattened, findings
