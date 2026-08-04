# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]
ZERO_HASH = "0" * 64
ACTUATION_KEYS = ("dispatch", "task_mutation", "resource_commitment", "public_warning", "network_egress")


class ReplayInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReplayRequest:
    baseline: JsonObject
    manifest: JsonObject
    records: tuple[JsonObject, ...]
    prerequisites: tuple[JsonObject, ...]
    min_incidents: int
    min_window_days: int


def _object(value: JsonValue, path: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ReplayInputError(f"{path}: must be a JSON object")
    return value


def _required(item: JsonObject, key: str, path: str) -> JsonValue:
    if key not in item:
        raise ReplayInputError(f"{path}.{key}: is required")
    return item[key]


def _text(item: JsonObject, key: str, path: str) -> str:
    value = _required(item, key, path)
    if not isinstance(value, str) or not value:
        raise ReplayInputError(f"{path}.{key}: must be a non-empty string")
    return value


def _flag(item: JsonObject, key: str, path: str) -> bool:
    value = _required(item, key, path)
    if not isinstance(value, bool):
        raise ReplayInputError(f"{path}.{key}: must be boolean")
    return value


def _number(item: JsonObject, key: str, path: str) -> float:
    value = _required(item, key, path)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReplayInputError(f"{path}.{key}: must be numeric")
    return float(value)


def _parse_json(text: str, path: str) -> JsonValue:
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ReplayInputError(f"{path}: invalid JSON at line {error.lineno}") from error


def load_baseline(path: Path) -> JsonObject:
    return _object(_parse_json(path.read_text(encoding="utf-8"), str(path)), str(path))


def load_fixture(path: Path) -> tuple[JsonObject, tuple[JsonObject, ...]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    values = [_parse_json(line, f"{path}:{index}") for index, line in enumerate(lines, 1) if line.strip()]
    if not values:
        raise ReplayInputError(f"{path}: fixture is empty")
    manifest = _object(values[0], f"{path}:1")
    records = tuple(_object(value, f"{path}:{index}") for index, value in enumerate(values[1:], 2))
    return manifest, records


def load_prerequisites(path: Path) -> tuple[JsonObject, ...]:
    value = _parse_json(path.read_text(encoding="utf-8"), str(path))
    if not isinstance(value, list):
        raise ReplayInputError(f"{path}: must contain a JSON array")
    return tuple(_object(item, f"{path}[{index}]") for index, item in enumerate(value))


def _timestamp(value: str, path: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReplayInputError(f"{path}: must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ReplayInputError(f"{path}: must include a timezone")
    return parsed.astimezone(UTC)


def _check_prerequisites(request: ReplayRequest, findings: list[str]) -> None:
    policy = _object(_required(request.baseline, "prerequisites", "baseline"), "baseline.prerequisites")
    ids = _required(policy, "ids", "baseline.prerequisites")
    required_ids = {item for item in ids if isinstance(item, str)} if isinstance(ids, list) else set()
    records = {str(item.get("id")): item for item in request.prerequisites}
    for prerequisite_id in required_ids:
        record = records.get(prerequisite_id)
        if record is None:
            findings.append(f"missing prerequisite {prerequisite_id}")
            continue
        if record.get("status") != "DEFERRED_EXTERNAL":
            findings.append(f"prerequisite {prerequisite_id} must remain DEFERRED_EXTERNAL")
        claims = record.get("claim_classes")
        if not isinstance(claims, list) or "shadow" not in claims:
            findings.append(f"prerequisite {prerequisite_id} lacks the shadow claim class")
        for field in ("owner", "authority", "evidence_hash", "expires_at"):
            if field not in record:
                findings.append(f"prerequisite {prerequisite_id} lacks {field}")


def _ece(records: tuple[JsonObject, ...]) -> float:
    bins: dict[int, list[tuple[float, bool]]] = {index: [] for index in range(10)}
    for record in records:
        probability = _number(record, "shadow_probability", "incident")
        actual = _flag(record, "actual", "incident")
        bucket = min(9, max(0, int(probability * 10)))
        bins[bucket].append((probability, actual))
    total = len(records)
    return sum(
        abs(sum(probability for probability, _ in values) / len(values) - sum(actual for _, actual in values) / len(values))
        * len(values) / total
        for values in bins.values()
        if values
    )


def evaluate_replay(request: ReplayRequest) -> tuple[int, str, JsonObject]:
    findings: list[str] = []
    baseline = request.baseline
    manifest = request.manifest
    if baseline.get("schema_version") != "resqnet.shadow-baseline.v1":
        findings.append("baseline schema_version is invalid")
    if manifest.get("schema_version") != "resqnet.shadow-incident.v1":
        findings.append("fixture schema_version is invalid")
    if baseline.get("status") != "DEFERRED_EXTERNAL":
        findings.append("baseline status must remain DEFERRED_EXTERNAL")
    population = _object(_required(baseline, "population", "baseline"), "baseline.population")
    if int(population.get("minimum_incidents", 0)) < request.min_incidents or int(population.get("minimum_window_days", 0)) < request.min_window_days:
        findings.append("requested population minimums exceed the pinned baseline minimums")
    auth = _object(_required(baseline, "auth_context", "baseline"), "baseline.auth_context")
    expected_auth = {"authenticated": True, "principal_type": "service", "subject": "shadow-replay-service", "audience": "resqnet-service", "org_id": "shadow-lab", "scope": "shadow:replay", "mode": "shadow"}
    if auth != expected_auth:
        findings.append("pinned auth context is not an authenticated shadow service account")
    if manifest.get("auth") != auth:
        findings.append("fixture auth context does not equal the pinned service-account context")
    controls = _object(_required(baseline, "actuation_controls", "baseline"), "baseline.actuation_controls")
    manifest_controls = _object(_required(manifest, "actuation", "fixture"), "fixture.actuation")
    for key in (*ACTUATION_KEYS, "queue_publish"):
        if controls.get(f"{key}_allowed") is not False or manifest_controls.get(key) is not False:
            findings.append(f"actuation control {key} is not disabled")
    blinding = _object(_required(baseline, "blinding", "baseline"), "baseline.blinding")
    if blinding.get("baseline_hidden_during_shadow_evaluation") is not True or blinding.get("baseline_revealed_only_for_comparison") is not True:
        findings.append("baseline blinding is not fixed before comparison")
    feedback_policy = _object(_required(baseline, "feedback", "baseline"), "baseline.feedback")
    allowed_feedback = feedback_policy.get("allowed_statuses")
    if feedback_policy.get("missing_handling") != "exclude_missing_feedback_from_operator_metrics_never_impute" or not isinstance(allowed_feedback, list) or "missing" not in allowed_feedback:
        findings.append("missing-feedback policy is incomplete")
    _check_prerequisites(request, findings)

    sample_count = len(request.records)
    if sample_count < request.min_incidents:
        findings.append(f"sample count {sample_count} is below {request.min_incidents}")
    observed: list[datetime] = []
    latencies: list[float] = []
    false_alerts = 0
    available = 0
    disagreements = 0
    attributed = 0
    overrides = 0
    override_attributed = 0
    feedback_missing = 0
    actuation_attempts = 0
    side_effects = {key: 0 for key in ACTUATION_KEYS}
    previous_hash = ZERO_HASH
    seen_ids: set[str] = set()
    for index, record in enumerate(request.records, 1):
        path = f"incident[{index}]"
        incident_id = _text(record, "id", path)
        if incident_id in seen_ids:
            findings.append(f"{path} repeats an incident id")
        seen_ids.add(incident_id)
        observed.append(_timestamp(_text(record, "observed_at", path), f"{path}.observed_at"))
        baseline_alert = _flag(record, "baseline", path)
        shadow_alert = _flag(record, "shadow", path)
        actual = _flag(record, "actual", path)
        latencies.append(_number(record, "latency_ms", path))
        if shadow_alert and not actual:
            false_alerts += 1
        if _flag(record, "available", path):
            available += 1
        if record.get("auth_ref") != "shadow-auth-v1":
            findings.append(f"{path} is not bound to the shadow service account")
        provenance = _object(_required(record, "provenance", path), f"{path}.provenance")
        if provenance.get("source") != manifest.get("source") or provenance.get("sequence") != index:
            findings.append(f"{path} provenance sequence/source is not immutable and contiguous")
        raw_hash = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        previous_hash = hashlib.sha256(f"{previous_hash}:{raw_hash}".encode()).hexdigest()
        if baseline_alert != shadow_alert:
            disagreements += 1
            disagreement = _object(_required(record, "disagreement", path), f"{path}.disagreement")
            if disagreement.get("attributed") is True and isinstance(disagreement.get("category"), str):
                attributed += 1
                if disagreement.get("provenance_ref") != incident_id or not disagreement.get("operator_identity"):
                    findings.append(f"{path} disagreement lacks operator identity or provenance")
                if disagreement.get("category") == "override":
                    override_attributed += 1
            else:
                findings.append(f"{path} disagreement is unattributed")
        elif _object(_required(record, "disagreement", path), f"{path}.disagreement").get("attributed") is not False:
            findings.append(f"{path} records attribution without a baseline disagreement")
        if _flag(record, "override", path):
            overrides += 1
            disagreement = _object(_required(record, "disagreement", path), f"{path}.disagreement")
            if disagreement.get("category") != "override":
                findings.append(f"{path} override is not attributed")
        feedback = _object(_required(record, "feedback", path), f"{path}.feedback")
        feedback_status = _text(feedback, "status", f"{path}.feedback")
        feedback_missing += feedback_status == "missing"
        if not isinstance(allowed_feedback, list) or feedback_status not in allowed_feedback:
            findings.append(f"{path} feedback status is outside the pinned schema")
        attempt = record.get("actuation_attempt")
        if attempt is True or (isinstance(attempt, dict) and attempt.get("requested") is True):
            actuation_attempts += 1
        for key in ACTUATION_KEYS:
            if record.get(key) is True:
                side_effects[key] += 1

    window_days = int((max(observed) - min(observed)).total_seconds() // 86_400) if observed else 0
    if window_days < request.min_window_days:
        findings.append(f"window {window_days} days is below {request.min_window_days}")
    thresholds = _object(_required(baseline, "thresholds", "baseline"), "baseline.thresholds")
    for threshold in ("false_alert_rate_max", "p95_end_to_end_latency_ms_max", "availability_min", "calibration_ece_max", "disagreement_attribution_min"):
        if not isinstance(thresholds.get(threshold), (int, float)) or isinstance(thresholds.get(threshold), bool):
            findings.append(f"baseline threshold {threshold} is not numeric")
    false_alert_rate = false_alerts / sample_count if sample_count else 1.0
    availability = available / sample_count if sample_count else 0.0
    p95_latency = sorted(latencies)[max(0, math.ceil(len(latencies) * 0.95) - 1)] if latencies else float("inf")
    attribution_rate = attributed / disagreements if disagreements else 1.0
    metrics: JsonObject = {
        "sample_count": sample_count,
        "window_days": window_days,
        "population": baseline.get("population", {}),
        "baseline_version": baseline.get("baseline_version"),
        "blinding": {"baseline_used_during_replay": False, "comparison_after_replay": True},
        "false_alert_rate": round(false_alert_rate, 6), "false_alert_burden": round(false_alert_rate, 6),
        "alert_precision": round(sum(_flag(record, "actual", "incident") and _flag(record, "shadow", "incident") for record in request.records) / sum(_flag(record, "shadow", "incident") for record in request.records), 6) if any(_flag(record, "shadow", "incident") for record in request.records) else 1.0,
        "p95_end_to_end_latency_ms": p95_latency, "end_to_end_latency_p95_ms": p95_latency,
        "availability": round(availability, 6),
        "calibration": {"ece": round(_ece(request.records), 6), "method": "fixed_10_bin_ece"},
        "override": {"count": overrides, "attributed_count": override_attributed},
        "disagreement": {"count": disagreements, "attributed_count": attributed, "attribution_rate": round(attribution_rate, 6)},
        "feedback": {"missing_count": feedback_missing, "missing_handling": "excluded_from_operator_metrics_never_imputed", "external_operator_comparison": "DEFERRED_EXTERNAL"},
        "incident_outcomes": {"ground_truth_positive": sum(_flag(record, "actual", "incident") for record in request.records), "ground_truth_negative": sum(not _flag(record, "actual", "incident") for record in request.records)},
        "actuation": {"attempts": actuation_attempts, "side_effects": side_effects, "route": "eval.shadow_replay", "service_account_scope": "shadow:replay"},
        "provenance": {"immutable_records_verified": len(request.records) == len({str(item.get("id")) for item in request.records}), "chain_head": previous_hash, "hash_algorithm": "SHA-256"},
        "authenticated_context": auth,
        "external_shadow_claim": "DEFERRED_EXTERNAL",
        "findings": findings,
    }
    if false_alert_rate > float(thresholds["false_alert_rate_max"]):
        findings.append("false-alert threshold failed")
    if p95_latency > float(thresholds["p95_end_to_end_latency_ms_max"]):
        findings.append("p95 end-to-end latency threshold failed")
    if availability < float(thresholds["availability_min"]):
        findings.append("availability threshold failed")
    if metrics["calibration"]["ece"] > thresholds["calibration_ece_max"]:
        findings.append("calibration ECE threshold failed")
    if attribution_rate < float(thresholds["disagreement_attribution_min"]):
        findings.append("disagreement attribution threshold failed")
    if actuation_attempts or any(side_effects.values()):
        findings.append("actuation attempt or side effect detected; shadow replay must fail")
    return (1, "FAIL", metrics) if findings else (0, "PASS", metrics)
