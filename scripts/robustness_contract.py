"""Validation and evidence helpers for the Todo 18 robustness CLI."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from scripts.benchmark_contract import JsonObject

FAMILIES = (
    "unseen_region_shift", "unseen_hazard_shift", "sensor_outage", "sensor_delay",
    "sensor_duplication", "sensor_conflict", "adversarial_misinformation",
    "weather_quality", "language_shift",
)


def policy_findings(policy: JsonObject) -> tuple[str, ...]:
    """Validate the machine-readable failure-family and release policy."""
    findings: list[str] = []
    if policy.get("schema_version") != "resqnet.robustness-policy.v1":
        findings.append("policy schema_version is invalid")
    if policy.get("claim_policy") != "deterministic fixture validation only; external robustness and equity claims remain DEFERRED_EXTERNAL":
        findings.append("policy must forbid external claims from deterministic fixtures")
    sample_policy = policy.get("sample_policy")
    if not isinstance(sample_policy, dict) or sample_policy.get("subgroup_minimum_samples") != 200:
        findings.append("subgroup minimum must be 200")
    thresholds = policy.get("thresholds")
    required_thresholds = {
        "max_degradation", "false_alert_burden_max", "severe_error_rate_max",
        "risk_coverage_max", "subgroup_gap_max", "fallback_rate_min",
    }
    if not isinstance(thresholds, dict) or set(thresholds) != required_thresholds:
        findings.append("release thresholds are incomplete")
    attack_budget = policy.get("attack_budget")
    if not isinstance(attack_budget, dict) or attack_budget.get("privileged_access") is not False:
        findings.append("attack budget must deny privileged access")
    privacy = policy.get("privacy")
    if not isinstance(privacy, dict) or privacy.get("status") != "PASS" or privacy.get("raw_pii") is not False:
        findings.append("privacy contract must pass without raw PII")
    routes = policy.get("route_fallbacks")
    if not isinstance(routes, dict) or set(routes) != {"flood_mapping", "damage", "nlp", "ensemble", "route_planner"}:
        findings.append("route fallback map is incomplete")
    families = policy.get("failure_families")
    valid_families = isinstance(families, list) and all(isinstance(entry, dict) for entry in families)
    family_ids = {entry.get("id") for entry in families} if valid_families else set()
    if family_ids != set(FAMILIES):
        findings.append("failure-family definitions are incomplete")
    if valid_families:
        for family in families:
            for field in ("formula", "expected_degradation_max", "safe_fallback", "affected_routes", "release_blocking"):
                if field not in family:
                    findings.append(f"failure family {family.get('id')} lacks {field}")
    return tuple(findings)


def write_report(
    path: Path,
    command: str,
    status: str,
    exit_code: int,
    metrics: JsonObject,
    inputs: tuple[Path, ...],
) -> None:
    """Write the normative Task 18 report with content hashes."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "unavailable"
    hashes = {str(item): hashlib.sha256(item.read_bytes()).hexdigest() for item in inputs if item.is_file()}
    payload: JsonObject = {
        "task_id": "18", "command": command, "cwd": str(Path.cwd()),
        "inputs": [str(item) for item in inputs], "code_revision": revision,
        "started_at": now, "finished_at": now, "exit_code": exit_code,
        "status": status, "metrics": metrics, "hashes": hashes,
        "failure_assertion": "all robustness families and route fallbacks passed" if exit_code == 0 else "one or more robustness assertions failed",
        "cleanup": "No external datasets, models, or artifacts downloaded; deterministic validation-only execution.",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = ["FAMILIES", "policy_findings", "write_report"]
