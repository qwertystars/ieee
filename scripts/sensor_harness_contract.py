"""Protocol controls for signed, sequence-ordered sensor telemetry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from scripts.sensor_harness_input import JsonObject, integer, verify_signature

MAX_SEQUENCE: Final = 2**64 - 1
PHYSICAL_IDS: Final = {
    "secure_boot": "hardware.secure-boot",
    "physical_calibration": "sensor.physical-calibration",
    "environmental_limits": "hardware.environmental-limits",
    "real_key_custody": "security.real-key-custody",
}


def _manifest(manifest: JsonObject) -> tuple[dict[str, JsonObject], list[str]]:
    findings: list[str] = []
    required = {
        "schema_version",
        "org_id",
        "incident_id",
        "device_id",
        "source_id",
        "provisioned",
        "clock",
        "replay_window_ms",
        "expected_sequences",
        "calibration_provenance",
        "keys",
    }
    findings.extend(
        f"manifest missing {field}" for field in sorted(required - set(manifest))
    )
    if manifest.get("schema_version") != "resqnet.sensor-harness.v1":
        findings.append("manifest schema_version is invalid")
    if manifest.get("provisioned") is not True:
        findings.append("device provisioning is not active")
    if manifest.get("source_id") != manifest.get("device_id"):
        findings.append("source_id is not bound to device identity")
    calibration = manifest.get("calibration_provenance")
    if not isinstance(calibration, dict):
        findings.append("calibration provenance is missing")
    else:
        for field in (
            "calibration_id",
            "calibration_version",
            "certificate_id",
            "traceability",
        ):
            if (
                not isinstance(calibration.get(field), str)
                or not calibration[field].strip()
            ):
                findings.append(f"calibration provenance missing {field}")
    clock = manifest.get("clock")
    if not isinstance(clock, dict) or clock.get("source") not in {
        "gnss",
        "gnss+rtc",
        "rtc",
    }:
        findings.append("clock source is not declared")
    if integer(manifest.get("replay_window_ms"), "replay_window_ms") <= 0:
        findings.append("replay window must be positive")
    raw_keys = manifest.get("keys")
    if not isinstance(raw_keys, list) or not raw_keys:
        findings.append("device key registry is empty")
        return {}, findings
    keys: dict[str, JsonObject] = {}
    for index, raw_key in enumerate(raw_keys):
        if not isinstance(raw_key, dict):
            findings.append(f"keys[{index}] must be an object")
            continue
        key_id = raw_key.get("key_id")
        if not isinstance(key_id, str) or not key_id:
            findings.append(f"keys[{index}].key_id is missing")
            continue
        if key_id in keys:
            findings.append(f"duplicate key registry entry {key_id}")
        keys[key_id] = raw_key
    active = [
        key
        for key in keys.values()
        if key.get("status") == "active" and key.get("revoked_at_ms") is None
    ]
    if len(active) != 1:
        findings.append("device key registry must have exactly one active key")
    return keys, findings


def evaluate(
    manifest: JsonObject, records: list[JsonObject]
) -> tuple[int, str, JsonObject]:
    """Evaluate protocol controls and return exit code, status, and metrics."""
    findings: list[str] = []
    quarantined: list[JsonObject] = []
    keys, manifest_findings = _manifest(manifest)
    findings.extend(manifest_findings)
    device_id = str(manifest.get("device_id"))
    org_id = str(manifest.get("org_id"))
    incident_id = str(manifest.get("incident_id"))
    expected = manifest.get("expected_sequences")
    expected_sequences = (
        {integer(value, "expected_sequences item") for value in expected}
        if isinstance(expected, list)
        else set()
    )
    seen_sequences: set[int] = set()
    seen_external: set[str] = set()
    previous = 0
    accepted = 0
    reference_time = integer(manifest.get("reference_time_ms"), "reference_time_ms")
    clock = manifest.get("clock")
    max_skew = (
        integer(clock.get("max_skew_ms"), "clock.max_skew_ms")
        if isinstance(clock, dict)
        else 0
    )
    replay_window = integer(manifest.get("replay_window_ms"), "replay_window_ms")
    calibration = manifest.get("calibration_provenance")
    calibration_version = (
        calibration.get("calibration_version")
        if isinstance(calibration, dict)
        else None
    )
    for index, record in enumerate(records, 1):
        record_findings: list[str] = []
        sequence = record.get("sequence")
        if (
            not isinstance(sequence, int)
            or isinstance(sequence, bool)
            or not 1 <= sequence <= MAX_SEQUENCE
        ):
            record_findings.append("sequence is outside 1..2^64-1")
            sequence = 0
        elif sequence in seen_sequences:
            record_findings.append("duplicate sequence")
        elif sequence <= previous:
            record_findings.append("sequence is not strictly increasing")
        if previous == MAX_SEQUENCE and sequence == 1:
            record_findings.append("sequence wrap is forbidden")
        if sequence:
            seen_sequences.add(sequence)
            previous = max(previous, sequence)
        external_id = record.get("external_id")
        if not isinstance(external_id, str) or not external_id:
            record_findings.append("external_id is missing")
        elif external_id in seen_external:
            record_findings.append("duplicate external_id")
        else:
            seen_external.add(external_id)
        bindings = (
            ("device_id", device_id),
            ("org_id", org_id),
            ("incident_id", incident_id),
            ("source_id", device_id),
        )
        if any(record.get(field) != value for field, value in bindings):
            record_findings.append("device identity or organization binding failed")
        observed_at = record.get("observed_at_ms")
        if not isinstance(observed_at, int) or isinstance(observed_at, bool):
            record_findings.append("observed_at_ms is not an integer")
        elif (
            reference_time - observed_at > replay_window
            or observed_at - reference_time > max_skew
        ):
            record_findings.append("clock skew or replay window exceeded")
        if record.get("calibration_version") != calibration_version:
            record_findings.append("calibration provenance version mismatch")
        signature_finding = verify_signature(record, keys)
        if signature_finding is not None:
            record_findings.append(signature_finding)
        if record_findings:
            quarantined.append(
                {
                    "line": index + 1,
                    "external_id": external_id,
                    "reasons": record_findings,
                }
            )
        else:
            accepted += 1
    missing = sorted(expected_sequences - seen_sequences)
    if missing:
        findings.append(f"lost sequence(s): {missing}")
    findings.extend(
        f"quarantined line {item['line']}: {', '.join(item['reasons'])}"
        for item in quarantined
    )
    if not expected_sequences:
        findings.append("expected sequence set is empty")
    status = "PASS" if not findings else "FAIL"
    metrics: JsonObject = {
        "protocol_contract": status,
        "accepted_records": accepted,
        "quarantined_records": len(quarantined),
        "expected_records": len(expected_sequences),
        "observed_sequences": sorted(seen_sequences),
        "quarantine": quarantined,
        "controls": [
            "provisioning",
            "Ed25519",
            "tenant_binding",
            "sequence_order",
            "loss_duplicate_replay_quarantine",
            "calibration_provenance",
            "key_rotation_revocation",
            "clock_source_skew",
            "replay_window",
            "sequence_wrap",
        ],
        "physical_claim": "DEFERRED_EXTERNAL",
        "findings": findings,
    }
    return (1, "FAIL", metrics) if findings else (0, "PASS", metrics)


def physical_missing(path: Path) -> list[str]:
    """Return physical prerequisite names without promoting absent evidence."""
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return list(PHYSICAL_IDS)
    if not isinstance(records, list):
        return list(PHYSICAL_IDS)
    statuses = {
        str(item.get("id")): item.get("status")
        for item in records
        if isinstance(item, dict)
    }
    return [
        name
        for name, identifier in PHYSICAL_IDS.items()
        if statuses.get(identifier) not in {"AVAILABLE", "PASSED"}
    ]
