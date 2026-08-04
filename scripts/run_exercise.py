#!/usr/bin/env python3
"""Replay laboratory controls and keep the participant tabletop gate external."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, TypeAlias

import yaml

ROOT: Final = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
REQUIRED_PREREQUISITE_FIELDS: Final = {
    "id", "owner", "authority", "status", "evidence_type", "evidence_hash",
    "hash_algorithm", "source_url", "recorded_at", "expires_at", "depends_on",
    "deferred_reason", "claim_classes",
}
ZERO_HASH: Final = "0" * 64


class ExerciseInputError(ValueError):
    pass

def _object(value: JsonValue, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ExerciseInputError(f"{label} must be an object")
    return value


def _text(value: JsonValue, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExerciseInputError(f"{label} must be a non-empty string")
    return value


def _path(value: JsonValue, label: str) -> Path:
    candidate = Path(_text(value, label))
    return candidate if candidate.is_absolute() else ROOT / candidate


def _canonical(value: JsonValue) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: JsonValue) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def load_scenario(path: Path) -> JsonObject:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ExerciseInputError(f"{path}: invalid YAML: {error}") from error
    return _object(value, str(path))


def _require_sections(scenario: JsonObject, findings: list[str]) -> None:
    required = {"schema_version", "exercise_id", "mode", "claim_class", "interoperability", "security", "role_authorization", "authority", "conflicting_reports", "offline_sync", "audit_reconstruction", "replay_tamper"}
    missing = sorted(required - set(scenario))
    findings.extend(f"scenario missing {field}" for field in missing)
    if scenario.get("schema_version") != "resqnet.tabletop-machine.v1":
        findings.append("scenario schema_version is invalid")
    if scenario.get("mode") != "machine_replay" or scenario.get("claim_class") != "tabletop_machine":
        findings.append("scenario must be a machine_replay/tabletop_machine fixture")


def _check_interoperability(scenario: JsonObject, findings: list[str]) -> JsonObject:
    from scripts.interoperability_contract import validate_contracts

    contract = _object(scenario["interoperability"], "interoperability")
    report = validate_contracts(
        _path(contract.get("fixtures"), "interoperability.fixtures"),
        _path(contract.get("profile"), "interoperability.profile"),
        _path(contract.get("lock"), "interoperability.lock"),
        offline=bool(contract.get("offline", False)),
        expected_ogc=("core", "crs", "query"),
        sensorthings_version="1.1",
    )
    findings.extend(f"interoperability: {finding}" for finding in report.findings)
    metrics = dict(report.metrics)
    metrics["operational_interoperability"] = "DEFERRED_EXTERNAL"
    metrics["machine_conformance"] = "PASS" if not report.findings else "FAIL"
    return metrics


def _check_authority(scenario: JsonObject, findings: list[str]) -> None:
    roles = _object(scenario["role_authorization"], "role_authorization").get("roles")
    if not isinstance(roles, dict):
        findings.append("role_authorization.roles must be an object")
        return
    cases = _object(scenario["role_authorization"], "role_authorization").get("cases")
    if not isinstance(cases, list):
        findings.append("role_authorization.cases must be an array")
        return
    for index, case_value in enumerate(cases):
        case = _object(case_value, f"authorization case {index}")
        role = _text(case.get("actor_role"), f"authorization case {index}.actor_role")
        action = _text(case.get("action"), f"authorization case {index}.action")
        expected = _text(case.get("expected"), f"authorization case {index}.expected")
        role_record = _object(roles.get(role), f"role {role}")
        allowed = action in role_record.get("allowed_actions", [])
        observed = "allow" if allowed else "deny"
        if expected != observed or (observed == "deny" and case.get("side_effects") != 0):
            findings.append(f"authorization case {case.get('id', index)} did not fail closed")
    authority = _object(scenario["authority"], "authority")
    warning = _object(authority.get("public_warning"), "authority.public_warning")
    approvals = warning.get("approvals")
    required_roles = warning.get("required_roles")
    if not isinstance(approvals, list) or not isinstance(required_roles, list):
        findings.append("public warning dual-control record is incomplete")
        return
    approved_roles = [item.get("role") for item in approvals if isinstance(item, dict) and item.get("approved") is True]
    if warning.get("status") != "approved" or len(approvals) != 2 or sorted(approved_roles) != sorted(required_roles) or len(set(approved_roles)) != 2:
        findings.append("public warning requires two distinct authorized approvals")


def _check_conflicts(scenario: JsonObject, findings: list[str]) -> None:
    conflict = _object(scenario["conflicting_reports"], "conflicting_reports")
    reports = conflict.get("reports")
    resolution = _object(conflict.get("resolution"), "conflicting_reports.resolution")
    values = [item.get("claim") for item in reports] if isinstance(reports, list) else []
    if len(values) < 2 or len({json.dumps(value, sort_keys=True) for value in values}) < 2:
        findings.append("conflicting reports must retain at least two different claims")
    if resolution.get("detected") is not True or resolution.get("last_write_wins") is not False or resolution.get("pre_resolution_state") != "abstain":
        findings.append("conflicting reports did not enter an explicit fail-closed state")
    if resolution.get("method") != "manual_authority_review" or not isinstance(resolution.get("selected_report"), str):
        findings.append("conflicting reports lack an explicit authority resolution")


def _check_offline(scenario: JsonObject, findings: list[str]) -> None:
    sync = _object(scenario["offline_sync"], "offline_sync")
    queue = sync.get("queue")
    sequences = [item.get("device_sequence") for item in queue] if isinstance(queue, list) else []
    if not sequences or sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
        findings.append("offline queue sequences are not monotonic and unique")
    duplicate = _object(sync.get("duplicate_replay"), "offline_sync.duplicate_replay")
    conflict = _object(sync.get("conflict"), "offline_sync.conflict")
    if duplicate.get("status") != "duplicate" or duplicate.get("side_effects") != 0:
        findings.append("offline duplicate replay was not idempotent")
    if conflict.get("status") != "conflict" or conflict.get("resolution") != "human_resolution_required" or conflict.get("last_write_wins") is not False or conflict.get("side_effects") != 0:
        findings.append("offline critical conflict was not surfaced for human resolution")


def _check_audit(scenario: JsonObject, findings: list[str]) -> str:
    audit = _object(scenario["audit_reconstruction"], "audit_reconstruction")
    events = audit.get("events")
    previous = ZERO_HASH
    if not isinstance(events, list) or not events:
        findings.append("audit reconstruction requires chained events")
        return previous
    for index, event_value in enumerate(events, 1):
        event = _object(event_value, f"audit event {index}")
        payload = _object(event.get("payload"), f"audit event {index}.payload")
        expected = hashlib.sha256((previous + _canonical(payload).decode()).encode()).hexdigest()
        if event.get("sequence") != index or event.get("prev_hash") != previous or event.get("hash") != expected:
            findings.append(f"audit event {index} failed hash-chain verification")
        previous = _text(event.get("hash"), f"audit event {index}.hash")
    required_actions = {"role_authorization", "public_warning", "conflicting_reports", "offline_sync"}
    actions = {str(_object(_object(item, "audit event").get("payload"), "audit payload").get("action")) for item in events}
    if not required_actions <= actions or audit.get("sanitized") is not True:
        findings.append("incident reconstruction is missing required sanitized control history")
    return previous


def replay_machine(scenario: JsonObject) -> tuple[int, str, JsonObject]:
    findings: list[str] = []
    _require_sections(scenario, findings)
    security = _object(scenario.get("security"), "security")
    expected_security = {"fail_closed": True, "dual_control": True, "signature": "Ed25519", "replay_protection": True, "tenant_scope": True, "network_access": "none"}
    if any(security.get(key) != value for key, value in expected_security.items()):
        findings.append("security/schema controls are not fail-closed")
    interoperability = _check_interoperability(scenario, findings) if "interoperability" in scenario else {}
    _check_authority(scenario, findings) if "role_authorization" in scenario and "authority" in scenario else None
    _check_conflicts(scenario, findings) if "conflicting_reports" in scenario else None
    _check_offline(scenario, findings) if "offline_sync" in scenario else None
    chain_head = _check_audit(scenario, findings) if "audit_reconstruction" in scenario else ZERO_HASH
    tamper = _object(scenario.get("replay_tamper"), "replay_tamper")
    tampered = _object(tamper.get("tampered_event"), "replay_tamper.tampered_event")
    tampered_expected = hashlib.sha256((str(tampered.get("prev_hash")) + _canonical(_object(tampered.get("payload"), "tampered payload")).decode()).encode()).hexdigest()
    if tamper.get("original_chain") != "PASS" or tamper.get("detector_status") != "FAIL_CLOSED" or tamper.get("tampered_hash") == tampered_expected or tamper.get("side_effects") != 0:
        findings.append("replay/tamper handling did not fail closed")
    metrics: JsonObject = {
        "machine_conformance": "PASS" if not findings else "FAIL",
        "machine_gate_status": "PASS" if not findings else "FAIL",
        "claim_class": "tabletop_machine",
        "participant_tabletop": "DEFERRED_EXTERNAL",
        "interoperability": interoperability,
        "controls": ["CAP", "OGC API Features", "SensorThings", "security", "schema", "roles", "authority", "conflicts", "public_warning_dual_approval", "offline_sync", "incident_reconstruction", "replay_tamper"],
        "audit_chain_head": chain_head,
        "findings": findings,
        "external_limitations": ["Local fixtures do not establish agency, production, or operational interoperability."],
    }
    return (1, "FAIL", metrics) if findings else (0, "PASS", metrics)


def _validate_external(scenario: JsonObject, prerequisites_path: Path) -> tuple[int, str, JsonObject]:
    findings: list[str] = []
    if scenario.get("schema_version") != "resqnet.tabletop-external.v1" or scenario.get("mode") != "participant_tabletop":
        findings.append("external scenario schema or mode is invalid")
    try:
        records = json.loads(prerequisites_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExerciseInputError(f"{prerequisites_path}: invalid prerequisite register: {error}") from error
    if not isinstance(records, list):
        findings.append("prerequisite register must be an array")
        records = []
    required_ids = scenario.get("prerequisite_ids", [])
    selected = {str(item.get("id")): item for item in records if isinstance(item, dict)}
    for identifier in required_ids if isinstance(required_ids, list) else []:
        record = selected.get(str(identifier))
        if record is None or set(record) != REQUIRED_PREREQUISITE_FIELDS:
            findings.append(f"prerequisite {identifier} does not contain exactly 13 fields")
        elif record.get("status") != "DEFERRED_EXTERNAL":
            findings.append(f"prerequisite {identifier} must remain DEFERRED_EXTERNAL")
    report = _path(scenario.get("report"), "external.report")
    report_value = _object(json.loads(report.read_text(encoding="utf-8")), str(report))
    required_report = {"authorized_participants", "agency_roles", "scoring", "unresolved_risk_severity", "after_action_owners", "retest_dates", "hash", "prerequisite_linkage"}
    if not required_report <= set(report_value):
        findings.append("tabletop report schema is incomplete")
    if any(report_value.get(field) is not None for field in required_report - {"hash", "prerequisite_linkage"}):
        findings.append("tabletop report contains fabricated participant evidence")
    report_copy = dict(report_value)
    report_copy["hash"] = None
    if report_value.get("hash") != _digest(report_copy):
        findings.append("tabletop report hash does not verify")
    metrics: JsonObject = {"participant_tabletop": "DEFERRED_EXTERNAL", "machine_pass_satisfies_participant_gate": False, "prerequisite_ids": required_ids, "report": str(report), "findings": findings}
    return (1, "FAIL", metrics) if findings else (2, "DEFERRED_EXTERNAL", metrics)


def _write_report(path: Path, command: str, status: str, exit_code: int, metrics: JsonObject, inputs: tuple[Path, ...], started_at: str) -> None:
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "unavailable"
    payload: JsonObject = {
        "task_id": "24", "claim_class": "tabletop_machine", "command": command, "cwd": str(Path.cwd()),
        "inputs": [str(item) for item in inputs], "code_revision": revision, "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"), "exit_code": exit_code,
        "status": status, "metrics": metrics, "hashes": {str(item): hashlib.sha256(item.read_bytes()).hexdigest() for item in inputs if item.is_file()},
        "failure_assertion": "all machine controls passed and unsafe paths failed closed" if exit_code == 0 else "; ".join(str(item) for item in metrics.get("findings", [])),
        "cleanup": "Read-only local fixtures; no validators, dependencies, credentials, network, agency systems, or runtime state were modified.",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--assert-fail-closed", action="store_true")
    parser.add_argument("--prerequisites", type=Path)
    parser.add_argument("--expect-deferred")
    args = parser.parse_args(argv)
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    try:
        scenario = load_scenario(args.scenario)
        if args.replay:
            exit_code, status, metrics = replay_machine(scenario)
            if args.assert_fail_closed and status != "FAIL":
                exit_code, status = 1, "FAIL"
            inputs = (args.scenario, Path("scripts/run_exercise.py"), Path("config/cap-profile-v1.2.yaml"), Path("config/validators.lock"))
        else:
            if args.prerequisites is None or args.expect_deferred != "participant-tabletop":
                raise ExerciseInputError("external mode requires --prerequisites and --expect-deferred participant-tabletop")
            exit_code, status, metrics = _validate_external(scenario, args.prerequisites)
            inputs = (args.scenario, args.prerequisites, Path("evidence/sota/tabletop-report.json"), Path("scripts/run_exercise.py"))
    except (ExerciseInputError, OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        exit_code, status, metrics = 1, "FAIL", {"findings": [str(error)]}
        inputs = (args.scenario, Path("scripts/run_exercise.py"))
    print(f"status={status}")
    for finding in metrics.get("findings", []):
        print(f"finding={finding}")
    if args.report is not None and args.replay:
        _write_report(args.report, " ".join(sys.argv), status, exit_code, metrics, inputs, started_at)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
