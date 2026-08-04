"""Boundary parsing and Ed25519 checks for sensor harness records."""

from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path
from typing import TypeAlias

from app.lib.canonical_json import JSONValue, canonical_json_bytes
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

JsonObject: TypeAlias = dict[str, JSONValue]


class HarnessInputError(ValueError):
    """Raised when a fixture is not a valid harness input."""


def _object(value: JSONValue, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise HarnessInputError(f"{label} must be an object")
    return value


def _text(value: JSONValue, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HarnessInputError(f"{label} must be a non-empty string")
    return value


def integer(value: JSONValue, label: str) -> int:
    """Parse a non-boolean integer at a trust boundary."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise HarnessInputError(f"{label} must be an integer")
    return value


def load_fixture(path: Path) -> tuple[JsonObject, list[JsonObject]]:
    """Parse a manifest-first NDJSON fixture."""
    manifest: JsonObject | None = None
    records: list[JsonObject] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise HarnessInputError(
                f"line {line_number}: invalid JSON: {error}"
            ) from error
        item = _object(value, f"line {line_number}")
        if manifest is None:
            if item.get("record_type") != "provisioning":
                raise HarnessInputError("first non-empty line must be provisioning")
            manifest = item
        else:
            records.append(item)
    if manifest is None or not records:
        raise HarnessInputError("fixture requires a provisioning line and telemetry")
    return manifest, records


def verify_signature(record: JsonObject, keys: dict[str, JsonObject]) -> str | None:
    """Verify an active Ed25519 key over canonical telemetry bytes."""
    key_id = _text(record.get("key_id"), "telemetry.key_id")
    key = keys.get(key_id)
    if key is None:
        return "unknown signing key"
    if key.get("status") != "active" or key.get("revoked_at_ms") is not None:
        return "signing key is rotated or revoked"
    try:
        public_key = base64.b64decode(
            _text(key.get("public_key_b64"), "key.public_key_b64"), validate=True
        )
        signature = base64.b64decode(
            _text(record.get("signature"), "telemetry.signature"), validate=True
        )
        if len(public_key) != 32 or len(signature) != 64:
            return "invalid Ed25519 byte length"
        unsigned = {key: value for key, value in record.items() if key != "signature"}
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature, canonical_json_bytes(unsigned)
        )
    except (binascii.Error, InvalidSignature, ValueError) as error:
        return f"signature verification failed: {error.__class__.__name__}"
    return None
