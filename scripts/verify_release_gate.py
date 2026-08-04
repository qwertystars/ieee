from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
CLAIMS: Final = {"research", "production", "shadow", "field"}
STATUSES: Final = {"NOT_ATTEMPTED", "AVAILABLE", "PASSED", "FAILED", "DEFERRED_EXTERNAL", "REVOKED"}
CLAIM_FIELDS: Final = {"research": ("dataset", "license", "split", "model", "calibration"), "production": ("security", "config", "DR", "validator", "key_custody"), "shadow": ("operator", "baseline", "30_day"), "field": ("agency", "IRB", "training", "hardware", "physical_calibration")}
PREREQUISITE_FIELDS: Final = {"id", "owner", "authority", "status", "evidence_type", "evidence_hash", "hash_algorithm", "source_url", "recorded_at", "expires_at", "depends_on", "deferred_reason", "claim_classes"}
EVIDENCE_FIELDS: Final = {"kind", "consent_status", "IRB_status", "geographic_privacy_status", "validator_status", "key_custody_status"}
HASH_RE: Final = re.compile(r"^[0-9a-f]{64}$")
ATTESTATION_FIELDS: Final = {"claim_class", "owner", "authority_quorum", "conflict_declaration", "recusal", "delegate", "timestamp", "revision", "expires_at", "prerequisite_hashes", "rollback_decision", "claim_taxonomy", "signature", "status"}


def _load(path: Path) -> JsonValue:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: JsonValue) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _timestamp(value: JsonValue, label: str, future: bool = False) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be UTC ISO-8601")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if future and parsed <= datetime.now(timezone.utc):
        raise ValueError(f"{label} is expired")


def _hash(value: JsonValue, label: str) -> None:
    if not isinstance(value, str) or HASH_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be lowercase SHA-256")


def _records(path: Path) -> tuple[dict[str, JsonObject], list[str]]:
    value = _load(path)
    records = value if isinstance(value, list) else value.get("prerequisites") if isinstance(value, dict) else None
    if not isinstance(records, list):
        raise TypeError("prerequisites must be an array")
    result: dict[str, JsonObject] = {}
    errors: list[str] = []
    for index, item in enumerate(records):
        if not isinstance(item, dict) or set(item) != PREREQUISITE_FIELDS:
            errors.append(f"prerequisites[{index}] exact 13-field schema violation")
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in result:
            errors.append(f"prerequisites[{index}] invalid or duplicate id")
            continue
        status = item.get("status")
        if status not in STATUSES:
            errors.append(f"{identifier} unsupported status")
        evidence = item.get("evidence_type")
        if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_FIELDS:
            errors.append(f"{identifier} exact six-field evidence_type violation")
        if item.get("hash_algorithm") != "SHA-256":
            errors.append(f"{identifier} hash_algorithm must be SHA-256")
        evidence_hash = item.get("evidence_hash")
        if status in {"AVAILABLE", "PASSED"} or evidence_hash is not None:
            _hash(evidence_hash, f"{identifier}.evidence_hash")
        _timestamp(item.get("recorded_at"), f"{identifier}.recorded_at")
        if item.get("expires_at") is not None:
            _timestamp(item.get("expires_at"), f"{identifier}.expires_at", True)
        if status == "DEFERRED_EXTERNAL" and not isinstance(item.get("deferred_reason"), str):
            errors.append(f"{identifier} deferred_reason is required")
        if status != "DEFERRED_EXTERNAL" and item.get("deferred_reason") is not None:
            errors.append(f"{identifier} deferred_reason must be null")
        claims = item.get("claim_classes")
        if not isinstance(claims, list) or not claims or not all(isinstance(claim, str) and claim in CLAIMS for claim in claims):
            errors.append(f"{identifier} claim_classes is invalid")
        result[identifier] = item
    return result, errors


def _claim_status(records: dict[str, JsonObject], identifiers: list[str]) -> str:
    values = [records[identifier].get("status") for identifier in identifiers if identifier in records]
    if not values or any(value in {"FAILED", "REVOKED"} for value in values):
        return "FAIL"
    if any(value in {"DEFERRED_EXTERNAL", "NOT_ATTEMPTED"} for value in values):
        return "DEFERRED_EXTERNAL"
    return "PASS"


def _validate_governance(path: Path, manifest: JsonObject, statuses: dict[str, str], prerequisite_hash: str, required_signatures: bool) -> list[str]:
    value = _load(path)
    if not isinstance(value, dict):
        return ["release governance must be an object"]
    mapping = value.get("claim_mapping")
    expected_mapping = {claim: list(fields) for claim, fields in CLAIM_FIELDS.items()}
    if mapping != expected_mapping:
        return ["claim mapping does not match the exact release policy"]
    board = value.get("release_board")
    if not isinstance(board, dict) or board.get("quorum") != 4 or board.get("roles") != ["security_lead", "ml_lead", "operations_lead", "incident_command"]:
        return ["release board must have the four-role quorum"]
    attestations = value.get("attestations")
    if not isinstance(attestations, list):
        return ["release attestations must be an array"]
    findings: list[str] = []
    revision = manifest.get("revision")
    for index, item in enumerate(attestations):
        if not isinstance(item, dict) or set(item) != ATTESTATION_FIELDS:
            findings.append(f"attestation[{index}] schema violation")
            continue
        claim = item.get("claim_class")
        if not isinstance(claim, str) or claim not in CLAIMS or item.get("claim_taxonomy") != [claim]:
            findings.append(f"attestation[{index}] claim taxonomy is invalid")
        if item.get("revision") != revision:
            findings.append(f"attestation[{index}] revision mismatch")
        quorum = item.get("authority_quorum")
        if quorum != ["security_lead", "ml_lead", "operations_lead", "incident_command"]:
            findings.append(f"attestation[{index}] authority quorum is invalid")
        _timestamp(item.get("timestamp"), f"attestation[{index}].timestamp")
        _timestamp(item.get("expires_at"), f"attestation[{index}].expires_at", True)
        hashes = item.get("prerequisite_hashes")
        if hashes != [prerequisite_hash]:
            findings.append(f"attestation[{index}] prerequisite hashes are not bound")
        if isinstance(claim, str) and claim in statuses and item.get("status") != statuses[claim]:
            findings.append(f"attestation[{index}] status is not derived")
        if required_signatures and isinstance(claim, str) and claim in statuses and statuses[claim] == "PASS" and not isinstance(item.get("signature"), str):
            findings.append(f"attestation[{index}] signature is required for PASS")
    return findings


def verify(args: argparse.Namespace) -> tuple[dict[str, str], list[str]]:
    manifest = _load(args.manifest)
    if not isinstance(manifest, dict) or set(manifest) != {"revision", "claim_classes", "prerequisite_hashes", "gate_attestations", "expires_at"}:
        raise ValueError("release manifest exact top-level schema violation")
    if not isinstance(manifest.get("revision"), str) or re.fullmatch(r"[0-9a-f]{40}", manifest["revision"]) is None:
        raise ValueError("manifest.revision must be a lowercase 40-character revision")
    _timestamp(manifest.get("expires_at"), "manifest.expires_at", True)
    claims = manifest.get("claim_classes")
    if not isinstance(claims, dict) or set(claims) != CLAIMS:
        raise ValueError("claim_classes must contain exactly four classes")
    records, findings = _records(args.prerequisites)
    expected_register_hash = _digest(args.prerequisites)
    hashes = manifest.get("prerequisite_hashes")
    if not isinstance(hashes, list) or expected_register_hash not in hashes:
        findings.append("prerequisite register hash is not attested")
    package = claims.get("research", {}).get("package") if isinstance(claims.get("research"), dict) else None
    if not isinstance(package, dict):
        findings.append("research.package is missing")
    else:
        files = package.get("file_hashes")
        if isinstance(files, dict):
            for group in files.values():
                if isinstance(group, dict):
                    for name, expected in group.items():
                        _hash(expected, f"file_hashes.{name}")
                        path = Path(name)
                        if not path.is_file() or _digest(path) != expected:
                            findings.append(f"hash mismatch for {name}")
        integrity = package.get("integrity")
        if isinstance(integrity, dict) and isinstance(integrity.get("manifest_sha256"), str):
            expected_integrity = integrity["manifest_sha256"]
            _hash(expected_integrity, "package.integrity.manifest_sha256")
            copy = json.loads(json.dumps(manifest))
            copy["claim_classes"]["research"]["package"]["integrity"]["manifest_sha256"] = "0" * 64
            if hashlib.sha256(_canonical(copy)).hexdigest() != expected_integrity:
                findings.append("manifest integrity digest mismatch")
        metric_fingerprint = package.get("metric_fingerprint")
        if isinstance(metric_fingerprint, str) and isinstance(package.get("metric_metadata"), (dict, list)):
            _hash(metric_fingerprint, "package.metric_fingerprint")
            if hashlib.sha256(_canonical(package["metric_metadata"])).hexdigest() != metric_fingerprint:
                findings.append("metric metadata fingerprint mismatch")
        sources = package.get("gate_sources")
        attestations = manifest.get("gate_attestations")
        if isinstance(sources, list) and isinstance(attestations, list) and len(sources) == len(attestations):
            for source, attestation in zip(sources, attestations):
                if not isinstance(source, str):
                    findings.append("gate source path is invalid")
                else:
                    _hash(attestation, f"gate attestation {source}")
                    if not Path(source).is_file() or _digest(Path(source)) != attestation:
                        findings.append(f"gate attestation mismatch for {source}")
        elif args.require_signed_attestations:
            findings.append("gate sources and attestations are not parallel")
    statuses: dict[str, str] = {}
    for claim in CLAIMS:
        record = claims[claim]
        if not isinstance(record, dict):
            findings.append(f"{claim} record is invalid")
            statuses[claim] = "FAIL"
            continue
        identifiers = record.get("prerequisite_ids")
        if not isinstance(identifiers, list) or not identifiers or not all(isinstance(identifier, str) for identifier in identifiers):
            findings.append(f"{claim} prerequisite_ids are missing")
            statuses[claim] = "FAIL"
            continue
        missing = [identifier for identifier in identifiers if identifier not in records]
        if missing:
            findings.append(f"{claim} references missing prerequisites: {','.join(missing)}")
        statuses[claim] = _claim_status(records, identifiers)
        if record.get("status") != statuses[claim]:
            findings.append(f"{claim} status is not derived from prerequisites")
    try:
        findings.extend(_validate_governance(args.governance, manifest, statuses, expected_register_hash, args.require_signed_attestations))
    except (OSError, UnicodeError, TypeError, json.JSONDecodeError, ValueError) as error:
        findings.append(str(error))
    return statuses, findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--prerequisites", type=Path, default=Path("evidence/sota/prerequisites.json"))
    parser.add_argument("--governance", type=Path, default=Path("evidence/sota/release-governance.json"))
    parser.add_argument("--claim-class", required=True)
    parser.add_argument("--allow-deferred", default="none")
    parser.add_argument("--require-signed-attestations", action="store_true")
    parser.add_argument("--aggregate-audit", action="store_true")
    args = parser.parse_args(argv)
    requested = [value.strip() for value in args.claim_class.split(",") if value.strip()]
    allowed = set() if args.allow_deferred == "none" else {value.strip() for value in args.allow_deferred.split(",")}
    try:
        statuses, findings = verify(args)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"status=FAIL\nfinding={error}")
        return 1
    if findings:
        print("status=FAIL")
        for finding in findings:
            print(f"finding={finding}")
        return 1
    requested_statuses = {claim: statuses[claim] for claim in requested}
    print(f"statuses={json.dumps(requested_statuses, sort_keys=True)}")
    if args.aggregate_audit:
        blocked = [claim for claim in requested if statuses[claim] == "FAIL" or (statuses[claim] == "DEFERRED_EXTERNAL" and claim not in allowed and claim != "research")]
        return 1 if blocked else 0
    if any(statuses[claim] == "FAIL" for claim in requested):
        return 1
    if any(statuses[claim] == "DEFERRED_EXTERNAL" for claim in requested):
        return 1 if any(statuses[claim] == "DEFERRED_EXTERNAL" and claim not in allowed for claim in requested) else (0 if args.require_signed_attestations else 2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
