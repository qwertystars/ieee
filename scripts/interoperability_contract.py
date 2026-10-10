"""Shared boundaries and lock validation for interoperability contracts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, TypeAlias

import yaml

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
ROOT: Final = Path(__file__).resolve().parents[1]
HASH_RE: Final = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """The local machine gate and external validator state."""

    status: str
    exit_code: int
    findings: tuple[str, ...]
    metrics: JsonObject


class ContractInputError(ValueError):
    """Raised when a contract or lock input cannot be parsed."""


def canonical(value: JsonValue) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def read_json(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractInputError(f"{path}: invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ContractInputError(f"{path}: top-level value must be an object")
    return value


def read_profile(path: Path) -> JsonObject:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ContractInputError(f"{path}: invalid YAML: {error}") from error
    if not isinstance(value, dict):
        raise ContractInputError(f"{path}: profile must be a YAML object")
    return value


def text(value: JsonValue, label: str, findings: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        findings.append(f"{label} must be a non-empty string")
        return None
    return value


def digest(value: JsonValue, label: str, findings: list[str]) -> None:
    if not isinstance(value, str) or HASH_RE.fullmatch(value) is None:
        findings.append(f"{label} must be a SHA-256 digest")


def timestamp(value: JsonValue, label: str, findings: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        findings.append(f"{label} must be a UTC timestamp ending in Z")
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        findings.append(f"{label} must be an ISO-8601 timestamp")
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        findings.append(f"{label} must be UTC")
        return None
    return parsed


def metadata(record: JsonObject, label: str, findings: list[str]) -> None:
    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        findings.append(f"{label}.provenance must be an object")
    else:
        for field in ("org_id", "source_id", "external_id", "receipt_time", "source_time", "sequence"):
            text(provenance.get(field), f"{label}.provenance.{field}", findings)
        digest(provenance.get("raw_data_hash"), f"{label}.provenance.raw_data_hash", findings)
        if provenance.get("simulated") is True:
            findings.append(f"{label}.provenance cannot mark external data as simulated")
    idempotency = record.get("idempotency")
    if not isinstance(idempotency, dict):
        findings.append(f"{label}.idempotency must be an object")
    else:
        for field in ("key", "external_id", "replay_effect"):
            text(idempotency.get(field), f"{label}.idempotency.{field}", findings)
        digest(idempotency.get("canonical_hash"), f"{label}.idempotency.canonical_hash", findings)
        if idempotency.get("replay_effect") != "same_effect":
            findings.append(f"{label}.idempotency.replay_effect must be same_effect")


def profile_findings(profile: JsonObject) -> list[str]:
    findings: list[str] = []
    if profile.get("schema_version") != "resqnet.cap-profile.v1":
        findings.append("CAP profile schema_version is invalid")
    if profile.get("cap_version") != "1.2":
        findings.append("CAP profile must pin version 1.2")
    if profile.get("ipaws_profile_version") != "1.0":
        findings.append("CAP profile must pin FEMA IPAWS Profile 1.0")
    if profile.get("default_crs") != "EPSG:4326":
        findings.append("CAP profile default CRS must be EPSG:4326")
    if profile.get("unit_system") != "UCUM":
        findings.append("CAP profile unit system must be UCUM")
    bindings = profile.get("bindings")
    if not isinstance(bindings, dict) or bindings.get("http") != "HTTPS+JSON" or bindings.get("mqtt") != "3.1.1":
        findings.append("CAP profile bindings must pin HTTPS JSON and MQTT 3.1.1")
    semantics = profile.get("update_cancel")
    if not isinstance(semantics, dict) or semantics.get("reuse_identifier") is not True or semantics.get("reference_fields") != ["sender", "identifier", "sent"]:
        findings.append("CAP update/cancel reference semantics are incomplete")
    return findings


def lock_findings(lock: JsonObject, offline: bool) -> tuple[list[str], list[str], JsonObject]:
    findings: list[str] = []
    deferred: list[str] = []
    if lock.get("schema_version") != "resqnet.validators-lock.v1":
        findings.append("validator lock schema_version is invalid")
    declared = lock.get("lock_sha256")
    copy = dict(lock)
    copy["lock_sha256"] = None
    if not isinstance(declared, str) or hashlib.sha256(canonical(copy)).hexdigest() != declared:
        findings.append("validator lock integrity digest mismatch")
    entries = lock.get("validators")
    if not isinstance(entries, list):
        return [*findings, "validator lock validators must be an array"], deferred, {}
    expected = {"cap-validator": "1.2.0", "ogc-api-features-validator": "1.0.1", "sensorthings-validator": "1.1.0"}
    availability: JsonObject = {}
    for entry in entries:
        if not isinstance(entry, dict):
            findings.append("validator lock entry must be an object")
            continue
        identifier = entry.get("id")
        if identifier not in expected or entry.get("version") != expected.get(identifier):
            findings.append(f"unexpected validator pin: {identifier}")
            continue
        for field in ("source_url", "artifact_filename", "artifact_path", "offline_invocation"):
            text(entry.get(field), f"validator[{identifier}].{field}", findings)
        digest(entry.get("sha256"), f"validator[{identifier}].sha256", findings)
        artifact = entry.get("artifact_path")
        available = False
        if isinstance(artifact, str) and not Path(artifact).is_absolute() and ".." not in Path(artifact).parts and not offline:
            path = ROOT / artifact
            if path.is_file():
                available = hashlib.sha256(path.read_bytes()).hexdigest() == entry.get("sha256")
                if not available:
                    findings.append(f"validator[{identifier}] artifact SHA-256 mismatch")
            else:
                deferred.append(f"validator_unavailable:{identifier}")
        else:
            deferred.append(f"validator_unavailable:{identifier}")
        availability[str(identifier)] = "available" if available else "DEFERRED_EXTERNAL"
    if set(availability) != set(expected):
        findings.append("validator lock must contain exactly the three roadmap pins")
    return findings, deferred, availability


def validate_contracts(fixtures: Path, profile: Path, lock: Path, *, offline: bool, expected_ogc: tuple[str, ...], sensorthings_version: str) -> ValidationReport:
    """Validate local fixtures and report external validator availability."""
    from scripts.interoperability_standards import (
        validate_cap,
        validate_offline,
        validate_ogc,
        validate_sensor_things,
    )

    findings = profile_findings(read_profile(profile))
    lock_errors, deferred, availability = lock_findings(read_json(lock), offline)
    findings.extend(lock_errors)
    if sensorthings_version != "1.1":
        findings.append("SensorThings version must be 1.1")
    if set(expected_ogc) != {"core", "crs", "query"}:
        findings.append("OGC classes must be exactly core,crs,query")
    fixture_count = 0
    for path in sorted(fixtures.iterdir()):
        if path.suffix != ".json":
            continue
        fixture_count += 1
        record = read_json(path)
        kind = record.get("kind")
        if kind == "cap":
            validate_cap(record, findings)
        elif kind == "ogc":
            validate_ogc(record, findings)
        elif kind == "sensorthings":
            validate_sensor_things(record, findings)
        elif kind == "offline":
            validate_offline(record, findings)
        else:
            findings.append(f"{path.name} has an unsupported fixture kind")
    if fixture_count == 0:
        findings.append("fixture directory contains no JSON inputs")
    machine_status = "FAIL" if findings else "PASS"
    status = "FAIL" if findings else ("DEFERRED_EXTERNAL" if deferred else "PASS")
    exit_code = 1 if findings else (2 if deferred else 0)
    metrics: JsonObject = {
        "machine_conformance": machine_status,
        "operational_interoperability": "DEFERRED_EXTERNAL",
        "external_validator_availability": availability,
        "fixture_count": fixture_count,
        "standards": ["CAP 1.2", "FEMA IPAWS CAP Profile 1.0", "OGC API Features 1.0.1 Core/CRS/Query", "SensorThings Sensing 1.1"],
        "bindings": ["EPSG:4326", "UCUM", "HTTPS JSON", "MQTT 3.1.1"],
        "deferred_reasons": deferred,
    }
    return ValidationReport(status, exit_code, tuple(findings), metrics)


__all__ = ["ContractInputError", "JsonObject", "JsonValue", "ValidationReport", "canonical", "digest", "metadata", "profile_findings", "read_json", "text", "timestamp", "validate_contracts"]
