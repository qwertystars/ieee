#!/usr/bin/env python3
"""Verify and capture the bounded ResQNet SOTA evidence package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

from scripts.reproduce_sota_contract import (
    CLAIMS,
    ROOT,
    JsonObject,
    ManifestInputError,
    as_object,
    canonical,
    digest,
    read_json,
    relative_path,
    sha256_file,
    text,
    timestamp,
    validate_files,
    validate_prerequisites,
)

REVISION_PATTERN: Final = re.compile(r"^[0-9a-f]{40}$")
MANIFEST_FIELDS: Final = {"revision", "claim_classes", "prerequisite_hashes", "gate_attestations", "expires_at"}
PACKAGE_FIELDS: Final = {
    "format_version", "prerequisite_source", "gate_sources", "file_hashes", "commands",
    "split_metadata", "metric_metadata", "runtime_constraints", "hardware_constraints",
    "tolerances", "nondeterminism_policy", "invalidation_inputs", "clean_room",
    "attestation_policy", "metric_fingerprint", "integrity",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _claim_status(statuses: dict[str, str], identifiers: list[str]) -> str:
    values = [statuses[identifier] for identifier in identifiers]
    if any(value in {"FAILED", "REVOKED"} for value in values):
        return "FAIL"
    if any(value in {"DEFERRED_EXTERNAL", "NOT_ATTEMPTED"} for value in values):
        return "DEFERRED_EXTERNAL"
    return "PASS"


def _manifest_digest(manifest: JsonObject) -> str:
    copy = json.loads(json.dumps(manifest))
    claims = as_object(copy["claim_classes"], "claim_classes")
    research = as_object(claims["research"], "claim_classes.research")
    package = as_object(research["package"], "claim_classes.research.package")
    integrity = as_object(package["integrity"], "package.integrity")
    integrity["manifest_sha256"] = "0" * 64
    return hashlib.sha256(canonical(copy)).hexdigest()


def verify_manifest(manifest_path: Path) -> tuple[JsonObject, dict[str, str], tuple[str, ...]]:
    manifest = as_object(read_json(manifest_path), "release manifest")
    findings: list[str] = []
    if set(manifest) != MANIFEST_FIELDS:
        findings.append("release manifest has unknown or missing top-level fields")
    revision = manifest.get("revision")
    if not isinstance(revision, str) or REVISION_PATTERN.fullmatch(revision) is None:
        findings.append("revision must be a 40-character lowercase git revision")
    try:
        timestamp(manifest.get("expires_at"), "expires_at", future=True)
    except ManifestInputError as error:
        findings.append(str(error))
    flat_hashes: dict[str, str] = {}
    try:
        claims = as_object(manifest.get("claim_classes"), "claim_classes")
        if set(claims) != set(CLAIMS):
            findings.append("claim_classes must contain exactly research, production, shadow, and field")
        research = as_object(claims.get("research"), "research")
        package = as_object(research.get("package"), "research.package")
        if set(package) != PACKAGE_FIELDS:
            findings.append("research package has unknown or missing fields")
        prerequisite_source = relative_path(package.get("prerequisite_source"), "package.prerequisite_source")
        statuses, claim_ids = validate_prerequisites(ROOT / prerequisite_source)
        flat_hashes, file_findings = validate_files(package)
        findings.extend(file_findings)
        prerequisite_hashes = manifest.get("prerequisite_hashes")
        if not isinstance(prerequisite_hashes, list) or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in prerequisite_hashes):
            findings.append("prerequisite_hashes must be lowercase SHA-256 strings")
        elif sha256_file(ROOT / prerequisite_source) not in prerequisite_hashes:
            findings.append("prerequisite register hash is not attested")
        gate_sources = package.get("gate_sources")
        gate_attestations = manifest.get("gate_attestations")
        if not isinstance(gate_sources, list) or not isinstance(gate_attestations, list) or len(gate_sources) != len(gate_attestations):
            findings.append("gate sources and attestations must be parallel arrays")
        else:
            for index, source_value in enumerate(gate_sources):
                source = relative_path(source_value, f"package.gate_sources[{index}]")
                expected = digest(gate_attestations[index], f"gate_attestations[{index}]")
                if sha256_file(ROOT / source) != expected:
                    findings.append(f"gate attestation mismatch for {source}")
        integrity = as_object(package.get("integrity"), "package.integrity")
        if digest(integrity.get("manifest_sha256"), "package.integrity.manifest_sha256") != _manifest_digest(manifest):
            findings.append("manifest integrity digest mismatch")
        metric_fingerprint = digest(package.get("metric_fingerprint"), "package.metric_fingerprint")
        if metric_fingerprint != hashlib.sha256(canonical(package.get("metric_metadata"))).hexdigest():
            findings.append("metric metadata fingerprint mismatch")
        runtime = as_object(package.get("runtime_constraints"), "runtime_constraints")
        if runtime.get("python_major_minor") != f"{sys.version_info.major}.{sys.version_info.minor}":
            findings.append("runtime constraint does not match the verifier interpreter")
        hardware = as_object(package.get("hardware_constraints"), "hardware_constraints")
        if hardware.get("os") != platform.system() or hardware.get("architecture") != platform.machine():
            findings.append("hardware constraint does not match the clean-room host")
        minimum_cores = hardware.get("minimum_cpu_cores")
        if isinstance(minimum_cores, int) and not isinstance(minimum_cores, bool) and (os.cpu_count() or 0) < minimum_cores:
            findings.append("clean-room host has fewer CPU cores than required")
        for claim in CLAIMS:
            claim_record = as_object(claims.get(claim), f"claim_classes.{claim}")
            ids = claim_record.get("prerequisite_ids")
            if ids != claim_ids[claim]:
                findings.append(f"{claim} prerequisite IDs do not match the canonical register")
            if claim_record.get("status") != _claim_status(statuses, claim_ids[claim]):
                findings.append(f"{claim} status is not derived from canonical prerequisites")
    except ManifestInputError as error:
        findings.append(str(error))
    return manifest, flat_hashes, tuple(findings)


def _build_report(manifest: JsonObject, manifest_path: Path, hashes: dict[str, str], findings: tuple[str, ...], command: str, started_at: str) -> JsonObject:
    claims = as_object(manifest["claim_classes"], "claim_classes")
    package = as_object(as_object(claims["research"], "research")["package"], "research.package")
    statuses, _ = validate_prerequisites(ROOT / relative_path(package["prerequisite_source"], "package.prerequisite_source"))
    claim_statuses = {claim: as_object(claims[claim], claim).get("status") for claim in CLAIMS}
    metrics: JsonObject = {
        "machine_gate_status": "FAIL" if findings else "PASS", "research_claim_status": claim_statuses["research"],
        "claim_statuses": claim_statuses, "sota_claim": False,
        "external_prerequisites": [identifier for identifier, status in statuses.items() if status == "DEFERRED_EXTERNAL"],
        "metric_fingerprint": package["metric_fingerprint"], "split_metadata": package["split_metadata"],
        "metric_metadata": package["metric_metadata"], "runtime_constraints": package["runtime_constraints"],
        "hardware_constraints": package["hardware_constraints"], "tolerances": package["tolerances"],
        "nondeterminism_policy": package["nondeterminism_policy"], "invalidation_inputs": package["invalidation_inputs"],
        "clean_room": package["clean_room"],
    }
    report_hashes = {**hashes, str(manifest_path): sha256_file(manifest_path)}
    return {
        "task_id": "19", "command": command, "cwd": str(ROOT), "inputs": list(hashes),
        "code_revision": text(manifest["revision"], "revision"), "started_at": started_at, "finished_at": _now(),
        "exit_code": 1 if findings else 2, "status": "FAIL" if findings else "DEFERRED_EXTERNAL", "metrics": metrics,
        "hashes": report_hashes, "failure_assertion": "; ".join(findings) if findings else "manifest, code, data, model, environment, gates, and clean-room constraints verified",
        "cleanup": "No external datasets, models, credentials, or production systems were modified; local inputs were read-only.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify and capture the reproducible ResQNet SOTA evidence package")
    parser.add_argument("--manifest", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--clean-room", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    started_at = _now()
    try:
        manifest, hashes, findings = verify_manifest(args.manifest)
        if findings:
            print("status=FAIL")
            for finding in findings:
                print(f"finding={finding}")
            return 1
        if args.verify:
            print("status=PASS")
            return 0
        if args.report is None:
            raise ManifestInputError("--clean-room requires --report")
        payload = _build_report(manifest, args.manifest, hashes, findings, "backend/.venv/bin/python " + " ".join(sys.argv), started_at)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"status={payload['status']}")
        return int(payload["exit_code"])
    except (ManifestInputError, OSError) as error:
        print(f"status=FAIL\nerror={error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
