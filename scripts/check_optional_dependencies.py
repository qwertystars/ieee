# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""Check externally supplied validator artifacts without substituting fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Final, TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
EXPECTED: Final = {
    "cap-validator": "1.2.0",
    "ogc-api-features-validator": "1.0.1",
    "sensorthings-validator": "1.1.0",
}


def _load(path: Path) -> JsonObject:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("validator lock must be a JSON object")
    return value


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_lock(lock: JsonObject) -> tuple[list[str], list[JsonObject]]:
    findings: list[str] = []
    entries = lock.get("validators")
    if lock.get("schema_version") != "resqnet.validators-lock.v1" or not isinstance(entries, list):
        return ["validator lock schema or validators array is invalid"], []
    typed_entries: list[JsonObject] = []
    for entry in entries:
        if not isinstance(entry, dict):
            findings.append("validator lock entry must be an object")
            continue
        typed_entries.append(entry)
        identifier = entry.get("id")
        version = entry.get("version")
        if not isinstance(identifier, str) or identifier not in EXPECTED or version != EXPECTED[identifier]:
            findings.append(f"unexpected validator pin: {identifier}")
        for field in ("artifact_path", "sha256", "source_url", "offline_invocation"):
            if not isinstance(entry.get(field), str) or not entry[field]:
                findings.append(f"validator[{identifier}].{field} is missing")
    if {str(entry.get("id")) for entry in typed_entries} != set(EXPECTED):
        findings.append("validator lock must contain exactly the three roadmap pins")
    return findings, typed_entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=Path("config/validators.lock"))
    parser.add_argument("--simulate-missing", action="store_true")
    args = parser.parse_args(argv)
    root = Path.cwd().resolve()
    lock_path = args.lock.resolve()
    try:
        lock = _load(lock_path)
        findings, entries = _validate_lock(lock)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print("status=FAIL")
        print(f"finding={error}")
        return 1
    if findings:
        print("status=FAIL")
        for finding in findings:
            print(f"finding={finding}")
        return 1
    unavailable: list[str] = []
    for entry in entries:
        identifier = str(entry["id"])
        artifact = root / str(entry["artifact_path"])
        expected_hash = str(entry["sha256"])
        if args.simulate_missing:
            unavailable.append(f"simulated_missing:{identifier}")
        elif not artifact.is_file():
            unavailable.append(f"missing:{identifier}")
        elif _digest(artifact) != expected_hash:
            print("status=FAIL")
            print(f"finding=validator[{identifier}] artifact SHA-256 mismatch")
            return 1
    if unavailable:
        print("status=DEFERRED_EXTERNAL")
        for reason in unavailable:
            print(f"deferred_reason={reason}")
        print("machine_conformance=not evaluated by dependency preflight")
        return 2
    print("status=PASS")
    print("optional_dependencies=all pinned validator artifacts available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
