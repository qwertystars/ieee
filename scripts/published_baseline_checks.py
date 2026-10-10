"""Field-level checks for pinned published-baseline registry rows."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import TypeGuard

from scripts.published_baseline_types import (
    COMMIT_PATTERN,
    EXPECTED_COMMANDS,
    EXPECTED_COMMITS,
    EXPECTED_PRIMARY_METRICS,
    HASH_PATTERN,
    REQUIRED_VARIANT_KINDS,
    ROOT,
    SYNTHETIC_ALIASES,
    JsonObject,
    JsonValue,
    RegistryInputError,
)


def is_object(value: JsonValue) -> TypeGuard[JsonObject]:
    return isinstance(value, dict)


def read_registry(path: Path) -> JsonObject:
    """Parse a registry path at the trust boundary."""
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryInputError(f"{path}: invalid JSON: {error}") from error
    if not is_object(parsed):
        raise RegistryInputError(f"{path}: top-level value must be an object")
    return parsed


def text(record: JsonObject, field: str, path: str, findings: list[str]) -> str | None:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        findings.append(f"{path}.{field} must be a non-empty string")
        return None
    return value


def nested_object(record: JsonObject, field: str, path: str, findings: list[str]) -> JsonObject | None:
    value = record.get(field)
    if not is_object(value):
        findings.append(f"{path}.{field} must be an object")
        return None
    return value


def url(record: JsonObject, field: str, path: str, findings: list[str]) -> None:
    value = text(record, field, path, findings)
    if value is not None and not value.startswith(("https://", "http://")):
        findings.append(f"{path}.{field} must be an HTTP(S) URL")


def check_policy(registry: JsonObject, findings: list[str]) -> None:
    policy = nested_object(registry, "policy", "registry", findings)
    if policy is None:
        return
    expected: dict[str, JsonValue] = {
        "confidence_level": 0.95,
        "bootstrap_resamples": 10_000,
        "bootstrap_unit": "incident",
        "holm_correction": "holm",
        "superiority_threshold": 0.02,
        "final_test_tuning": False,
    }
    for field, value in expected.items():
        if policy.get(field) != value:
            findings.append(f"registry.policy.{field} must be {value!r}")
    if policy.get("seeds") != [1, 2, 3, 4, 5]:
        findings.append("registry.policy.seeds must be exactly [1, 2, 3, 4, 5]")
    metrics = policy.get("required_metrics")
    if not isinstance(metrics, list) or not metrics or not all(isinstance(item, str) for item in metrics):
        findings.append("registry.policy.required_metrics must be a non-empty string array")


def check_command(record: JsonObject, task: str, path: str, findings: list[str]) -> None:
    command = text(record, "command", path, findings)
    if command is None:
        return
    if command != EXPECTED_COMMANDS[task]:
        findings.append(f"{path}.command is not the immutable command pinned for {task}")
    if any(token in command for token in (";", "|", "&", ">", "<", "$")):
        findings.append(f"{path}.command contains shell control syntax")
        return
    try:
        tokens = shlex.split(command)
    except ValueError as error:
        findings.append(f"{path}.command is not shell-tokenizable: {error}")
        return
    if len(tokens) != 4 or tokens[0] != "python" or tokens[1] != "scripts/run_baseline.py" or tokens[2] != "--config":
        findings.append(f"{path}.command must invoke scripts/run_baseline.py with --config")
        return
    if not (ROOT / tokens[3]).is_file():
        findings.append(f"{path}.command config path is unresolved: {tokens[3]}")
    if record.get("config_path") != tokens[3]:
        findings.append(f"{path}.config_path must match the command config path")


def check_artifact(record: JsonObject, path: str, findings: list[str]) -> None:
    artifact = nested_object(record, "artifact", path, findings)
    if artifact is None:
        return
    available, digest, status = artifact.get("available"), artifact.get("sha256"), record.get("status")
    if not isinstance(available, bool):
        findings.append(f"{path}.artifact.available must be boolean")
    if digest is not None and (not isinstance(digest, str) or not re.fullmatch(HASH_PATTERN, digest)):
        findings.append(f"{path}.artifact.sha256 must be a lowercase SHA-256 digest or null")
    if available and (not isinstance(digest, str) or not re.fullmatch(HASH_PATTERN, digest)):
        findings.append(f"{path}.available artifact requires an immutable SHA-256 digest")
    if status == "AVAILABLE" and not available:
        findings.append(f"{path}.AVAILABLE baseline requires an available artifact")
    reference = artifact.get("reference")
    if not isinstance(reference, str) or not reference.strip():
        findings.append(f"{path}.artifact.reference must be an immutable reference")
    elif any(marker in reference.lower() for marker in ("/main", "/master", "/latest", ":latest")):
        findings.append(f"{path}.artifact.reference must not use a mutable tag")


def check_repository(record: JsonObject, task: str, path: str, findings: list[str]) -> None:
    repository = nested_object(record, "repository", path, findings)
    if repository is None:
        return
    url(repository, "url", f"{path}.repository", findings)
    commit = text(repository, "commit", f"{path}.repository", findings)
    if task != "incident-nlp" and (commit is None or commit != EXPECTED_COMMITS[task]):
        findings.append(f"{path}.repository.commit is not the exact pinned commit for {task}")
    if task != "incident-nlp" and (commit is None or not re.fullmatch(COMMIT_PATTERN, commit)):
        findings.append(f"{path}.repository.commit must be a 40-character immutable commit")


def check_license(record: JsonObject, path: str, findings: list[str]) -> None:
    license_info = nested_object(record, "license", path, findings)
    if license_info is None:
        return
    for field in ("name", "authority", "allowed_use_status"):
        text(license_info, field, f"{path}.license", findings)
    if license_info.get("allowed_use_status") not in {"ALLOWED", "PENDING_AUTHORIZATION", "NOT_PERMITTED"}:
        findings.append(f"{path}.license.allowed_use_status must be explicit")


def check_metrics(record: JsonObject, task: str, path: str, findings: list[str]) -> None:
    protocol = nested_object(record, "metric_protocol", path, findings)
    if protocol is None:
        return
    primary = text(protocol, "primary_metric", f"{path}.metric_protocol", findings)
    if primary != EXPECTED_PRIMARY_METRICS[task]:
        findings.append(f"{path}.metric_protocol.primary_metric must be {EXPECTED_PRIMARY_METRICS[task]}")
    if protocol.get("direction") != "higher_is_better":
        findings.append(f"{path}.metric_protocol.direction must be higher_is_better")
    for field in ("required_metrics", "per_class_metrics", "per_event_metrics"):
        value = protocol.get(field)
        if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
            findings.append(f"{path}.metric_protocol.{field} must be a non-empty string array")
        elif any(any(alias in item.lower() for alias in SYNTHETIC_ALIASES) for item in value):
            findings.append(f"{path}.metric_protocol.{field} contains a synthetic metric alias")


def check_variants(record: JsonObject, path: str, findings: list[str]) -> None:
    variants = record.get("variants")
    if not isinstance(variants, list) or not variants:
        findings.append(f"{path}.variants must be a non-empty array")
        return
    kinds: set[str] = set()
    for index, raw in enumerate(variants):
        variant_path = f"{path}.variants[{index}]"
        if not is_object(raw):
            findings.append(f"{variant_path} must be an object")
            continue
        text(raw, "variant_id", variant_path, findings)
        kind = text(raw, "kind", variant_path, findings)
        if kind is not None:
            kinds.add(kind)
        modalities = raw.get("modalities")
        if not isinstance(modalities, list) or not modalities or not all(isinstance(item, str) for item in modalities):
            findings.append(f"{variant_path}.modalities must be a non-empty string array")
    if not REQUIRED_VARIANT_KINDS <= kinds:
        findings.append(f"{path}.variants must cover modality_only and fusion variants")
