"""Machine and external contract checks for the field-exercise harness."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from pathlib import Path
from typing import Final, TypeAlias

import yaml

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
ZERO_HASH: Final = "0" * 64
REQUIRED_PREREQUISITE_FIELD_ORDER: Final = (
    "id", "owner", "authority", "status", "evidence_type", "evidence_hash",
    "hash_algorithm", "source_url", "recorded_at", "expires_at", "depends_on",
    "deferred_reason", "claim_classes",
)
REQUIRED_PREREQUISITE_FIELDS: Final = frozenset(REQUIRED_PREREQUISITE_FIELD_ORDER)
REQUIRED_EVENTS: Final = (
    "degraded_connectivity", "power_loss", "device_loss", "stale_map", "competing_incidents",
    "alert_latency", "loss_duplicates", "offline_duration", "sync_conflict", "authorization_failure",
    "audit_completeness", "no_actuation",
)
ACTUATION_KEYS: Final = ("dispatch", "public_warning", "resource_commitment", "device_command", "network_egress")
EXTERNAL_RESULT_FIELDS: Final = (
    "agency_authorization", "ethics_irb", "training", "insurance_safety_review", "device_inventory",
    "consent", "stop_authority", "blinding", "missing_data_rules",
)


class HarnessInputError(ValueError):
    """Raised when a field-exercise fixture is not a supported input."""


def _object(value: JsonValue | None, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise HarnessInputError(f"{label} must be an object")
    return value


def _text(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HarnessInputError(f"{label} must be a non-empty string")
    return value


def _integer(value: JsonValue | None, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise HarnessInputError(f"{label} must be an integer")
    return value


def _number(value: JsonValue | None, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HarnessInputError(f"{label} must be numeric")
    return float(value)


def _canonical(value: JsonValue) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: JsonValue) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def load_scenario(path: Path) -> JsonObject:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise HarnessInputError(f"{path}: invalid YAML: {error}") from error
    return _object(value, str(path))


def _load_json(path: Path) -> JsonValue:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HarnessInputError(f"{path}: invalid JSON: {error}") from error


def _numbers(value: JsonValue | None, label: str, findings: list[str]) -> list[float]:
    if not isinstance(value, list) or not value:
        findings.append(f"{label} must be a non-empty numeric array")
        return []
    numbers: list[float] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            findings.append(f"{label}[{index}] must be numeric")
        else:
            numbers.append(float(item))
    return numbers


def _check_signed_log(scenario: JsonObject, findings: list[str]) -> JsonObject:
    signed = _object(scenario.get("signed_log"), "signed_log")
    if signed.get("algorithm") != "HMAC-SHA256":
        findings.append("signed log algorithm must be HMAC-SHA256")
    key = _text(signed.get("fixture_key"), "signed_log.fixture_key").encode()
    events_value = scenario.get("event_log")
    if not isinstance(events_value, list) or not events_value:
        findings.append("event_log must be non-empty")
        return {"integrity": "FAIL", "chain_head": ZERO_HASH, "deterministic": False}
    previous = ZERO_HASH
    hashes: list[str] = []
    event_types: set[str] = set()
    for position, value in enumerate(events_value, 1):
        event = _object(value, f"event_log[{position}]")
        if event.get("sequence") != position:
            findings.append(f"event_log[{position}] sequence is not contiguous")
        event_type = event.get("event_type")
        if isinstance(event_type, str):
            event_types.add(event_type)
        unsigned: JsonObject = {name: event.get(name) for name in ("sequence", "event_id", "event_type", "payload")}
        expected_hash = hashlib.sha256((previous + _canonical(unsigned).decode()).encode()).hexdigest()
        if event.get("prev_hash") != previous or event.get("hash") != expected_hash:
            findings.append(f"event_log[{position}] hash chain verification failed")
        expected_signature = hmac.new(key, expected_hash.encode(), hashlib.sha256).hexdigest()
        if event.get("signature") != expected_signature:
            findings.append(f"event_log[{position}] signature verification failed")
        actual_hash = event.get("hash")
        if isinstance(actual_hash, str):
            previous = actual_hash
            hashes.append(actual_hash)
    missing = sorted(set(REQUIRED_EVENTS) - event_types)
    findings.extend(f"signed log missing event type {event_type}" for event_type in missing)
    replay_digest = hashlib.sha256("".join(hashes).encode()).hexdigest()
    if signed.get("expected_chain_head") != previous:
        findings.append("signed log chain head does not match the fixture")
    if signed.get("expected_replay_digest") != replay_digest:
        findings.append("replay digest does not match the fixture")
    return {"algorithm": signed.get("algorithm"), "integrity": "PASS" if not findings else "FAIL", "event_count": len(events_value), "chain_head": previous, "replay_digest": replay_digest, "event_types": sorted(event_types)}


def evaluate_machine(scenario: JsonObject) -> tuple[int, str, JsonObject]:
    findings: list[str] = []
    required = {"schema_version", "exercise_id", "mode", "claim_class", "security", "thresholds", "measurements", "signed_log", "event_log"}
    findings.extend(f"scenario missing {name}" for name in sorted(required - set(scenario)))
    if scenario.get("schema_version") != "resqnet.field-machine.v1" or scenario.get("mode") != "machine_replay" or scenario.get("claim_class") != "field_machine":
        findings.append("scenario must be a field machine replay fixture")
    security = _object(scenario.get("security"), "security")
    for name, expected in {"fail_closed": True, "no_actuation": True, "network_access": "none", "replay_protection": True}.items():
        if security.get(name) != expected:
            findings.append(f"security control {name} is not fail-closed")
    controls = scenario.get("required_controls")
    if not isinstance(controls, list) or {str(item) for item in controls} != set(REQUIRED_EVENTS):
        findings.append("required_controls must enumerate every degraded-mode event")
    thresholds = _object(scenario.get("thresholds"), "thresholds")
    measurements = _object(scenario.get("measurements"), "measurements")
    latencies = _numbers(measurements.get("alert_latency_ms"), "measurements.alert_latency_ms", findings)
    sent = _integer(measurements.get("sent_events"), "measurements.sent_events")
    lost = _integer(measurements.get("lost_events"), "measurements.lost_events")
    duplicates = _integer(measurements.get("duplicate_events"), "measurements.duplicate_events")
    if sent <= 0:
        findings.append("sent_events must be positive")
    loss_rate = lost / sent if sent > 0 else 1.0
    duplicate_rate = duplicates / sent if sent > 0 else 1.0
    p95_latency = sorted(latencies)[max(0, math.ceil(len(latencies) * 0.95) - 1)] if latencies else float("inf")
    sync = measurements.get("sync_conflicts")
    unresolved_sync = sum(isinstance(item, dict) and item.get("unresolved") is True for item in sync) if isinstance(sync, list) else -1
    if not isinstance(sync, list):
        findings.append("sync_conflicts must be an array")
    auth = measurements.get("authorization_failures")
    auth_side_effects = sum(_integer(item.get("side_effects"), "authorization side_effects") for item in auth if isinstance(item, dict)) if isinstance(auth, list) else -1
    if not isinstance(auth, list):
        findings.append("authorization_failures must be an array")
    audit = _object(measurements.get("audit"), "measurements.audit")
    expected_audit = _integer(audit.get("expected_events"), "audit.expected_events")
    complete_audit = _integer(audit.get("complete_events"), "audit.complete_events")
    stale_maps = measurements.get("stale_maps")
    stale_map_age = max((_number(item.get("age_s"), "stale map age") for item in stale_maps if isinstance(item, dict)), default=0.0) if isinstance(stale_maps, list) else 0.0
    if not isinstance(stale_maps, list):
        findings.append("stale_maps must be an array")
    actuation = _object(measurements.get("actuation"), "measurements.actuation")
    no_actuation = all(actuation.get(name) is False for name in ACTUATION_KEYS)
    if not no_actuation:
        findings.append("life-safety actuation or an external side effect is enabled")
    checks = (
        (p95_latency <= _number(thresholds.get("alert_latency_p95_ms_max"), "thresholds.alert_latency_p95_ms_max"), "alert latency threshold failed"),
        (loss_rate <= _number(thresholds.get("loss_rate_max"), "thresholds.loss_rate_max"), "loss threshold failed"),
        (duplicate_rate <= _number(thresholds.get("duplicate_rate_max"), "thresholds.duplicate_rate_max"), "duplicate threshold failed"),
        (_number(measurements.get("offline_duration_s"), "offline_duration_s") >= _number(thresholds.get("offline_duration_min_s"), "thresholds.offline_duration_min_s"), "offline duration minimum not exercised"),
        (unresolved_sync <= _integer(thresholds.get("sync_conflicts_unresolved_max"), "thresholds.sync_conflicts_unresolved_max"), "unresolved sync conflict threshold failed"),
        (complete_audit / expected_audit >= _number(thresholds.get("audit_completeness_min"), "thresholds.audit_completeness_min") if expected_audit > 0 else False, "audit completeness threshold failed"),
        (len(auth) >= _integer(thresholds.get("authorization_failures_min"), "thresholds.authorization_failures_min") and auth_side_effects == 0, "authorization failure handling failed"),
        (stale_map_age >= _number(thresholds.get("stale_map_age_min_s"), "thresholds.stale_map_age_min_s") and all(isinstance(item, dict) and item.get("action") == "block_critical_action" for item in stale_maps), "stale map was not blocked"),
        (_integer(measurements.get("power_loss_events"), "power_loss_events") >= _integer(thresholds.get("power_loss_events_min"), "thresholds.power_loss_events_min"), "power-loss behavior not exercised"),
        (_integer(measurements.get("device_loss_events"), "device_loss_events") >= _integer(thresholds.get("device_loss_events_min"), "thresholds.device_loss_events_min"), "device-loss behavior not exercised"),
        (_integer(measurements.get("intermittent_link_events"), "intermittent_link_events") >= _integer(thresholds.get("intermittent_link_events_min"), "thresholds.intermittent_link_events_min"), "intermittent-link behavior not exercised"),
        (_integer(measurements.get("competing_incidents"), "competing_incidents") >= _integer(thresholds.get("competing_incidents_min"), "thresholds.competing_incidents_min"), "competing incidents not exercised"),
    )
    findings.extend(message for passed, message in checks if not passed)
    signed_log = _check_signed_log(scenario, findings)
    metrics: JsonObject = {
        "machine_gate_status": "PASS" if not findings else "FAIL", "claim_class": "field_machine", "alert_latency_p95_ms": p95_latency,
        "loss_rate": round(loss_rate, 6), "duplicate_rate": round(duplicate_rate, 6), "offline_duration_s": measurements.get("offline_duration_s"),
        "sync_conflicts_unresolved": unresolved_sync, "authorization_failures": len(auth) if isinstance(auth, list) else 0,
        "audit_completeness": complete_audit / expected_audit if expected_audit > 0 else 0.0, "stale_map_age_s": stale_map_age,
        "power_loss_events": measurements.get("power_loss_events"), "device_loss_events": measurements.get("device_loss_events"),
        "intermittent_link_events": measurements.get("intermittent_link_events"), "competing_incidents": measurements.get("competing_incidents"),
        "signed_log": signed_log, "replay": {"deterministic": not any("replay" in finding or "hash chain" in finding or "signature" in finding for finding in findings)},
        "no_actuation": no_actuation, "external_field_claim": "DEFERRED_EXTERNAL", "findings": findings,
    }
    return (1, "FAIL", metrics) if findings else (0, "PASS", metrics)


def validate_external(scenario: JsonObject, prerequisites_path: Path) -> tuple[int, str, JsonObject]:
    findings: list[str] = []
    if scenario.get("schema_version") != "resqnet.field-external.v1" or scenario.get("mode") != "external_field_trial":
        findings.append("external scenario schema or mode is invalid")
    records_value = _load_json(prerequisites_path)
    records = records_value if isinstance(records_value, list) else []
    if not isinstance(records_value, list):
        findings.append("prerequisite register must be an array")
    selected = {str(item.get("id")): item for item in records if isinstance(item, dict)}
    required_ids = scenario.get("prerequisite_ids")
    ids = [str(item) for item in required_ids] if isinstance(required_ids, list) else []
    for identifier in ids:
        record = selected.get(identifier)
        if record is None or set(record) != REQUIRED_PREREQUISITE_FIELDS:
            findings.append(f"prerequisite {identifier} does not contain exactly 13 fields")
        elif record.get("status") != "DEFERRED_EXTERNAL" or record.get("evidence_hash") is not None:
            findings.append(f"prerequisite {identifier} contains external evidence that is not deferred")
    report_path = Path(_text(scenario.get("report"), "external.report"))
    if not report_path.is_absolute():
        report_path = Path(__file__).resolve().parents[1] / report_path
    report = _object(_load_json(report_path), str(report_path))
    required_report = {"schema_version", "status", "claim_class", "machine_pass_satisfies_field_gate", "required_report_fields", "prerequisite_linkage", "hash_algorithm", "hash", "deferred_reason", *EXTERNAL_RESULT_FIELDS, "sample_hazard_minimums"}
    findings.extend(f"field report missing {name}" for name in sorted(required_report - set(report)))
    if report.get("status") != "DEFERRED_EXTERNAL" or report.get("claim_class") != "field_external" or report.get("machine_pass_satisfies_field_gate") is not False:
        findings.append("field report does not preserve the external deferred boundary")
    if report.get("hash_algorithm") != "SHA-256":
        findings.append("field report hash algorithm is not SHA-256")
    report_copy = dict(report)
    report_copy["hash"] = None
    if report.get("hash") != _digest(report_copy):
        findings.append("field report hash does not verify")
    for field in EXTERNAL_RESULT_FIELDS:
        if report.get(field) is not None:
            findings.append(f"field report fabricates external value {field}")
    sample = _object(report.get("sample_hazard_minimums"), "sample_hazard_minimums")
    if sample.get("minimum_incidents") != 100 or sample.get("minimum_hazard_types") != 3 or sample.get("observed_incidents") is not None or sample.get("observed_hazard_types") is not None:
        findings.append("field report sample or hazard minimums are incomplete or fabricated")
    linkage = _object(report.get("prerequisite_linkage"), "prerequisite_linkage")
    if linkage.get("ids") != ids or linkage.get("required_record_fields") != list(REQUIRED_PREREQUISITE_FIELD_ORDER):
        findings.append("field report prerequisite linkage is incomplete")
    metrics: JsonObject = {"field_claim": "DEFERRED_EXTERNAL", "machine_pass_satisfies_field_gate": False, "missing_external_values": list(EXTERNAL_RESULT_FIELDS), "prerequisite_ids": ids, "report": str(report_path), "findings": findings}
    return (1, "FAIL", metrics) if findings else (2, "DEFERRED_EXTERNAL", metrics)
