from __future__ import annotations

import base64
import binascii
import struct
from typing import TypeAlias

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy.orm import Session

from app.lib.audit import JSONValue, canonical_json_bytes
from app.lib.ulid import parse_ulid
from app.models.alert import CommandApproval, CommandSigningKey
from app.models.events import validate_ulid
from app.models.user import User

COMMAND_PREFIX = b"RESQNET-SIG-V1"
MAX_SIGNATURE_AGE_MS = 300_000
MAX_CLOCK_SKEW_MS = 30_000
MAX_KEY_AGE_MS = 30 * 86_400_000
DUAL_CONTROL_ROLES = frozenset({"emergency_manager", "responder_coordinator"})
CommandPayload: TypeAlias = dict[str, JSONValue]


class CommandAuthorizationError(Exception):
    def __init__(self, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _nonce_bytes(nonce: str) -> bytes:
    try:
        validate_ulid(nonce)
        timestamp, randomness = parse_ulid(nonce)
    except (OverflowError, ValueError) as exc:
        raise CommandAuthorizationError("nonce must be a valid ULID", 422) from exc
    return timestamp.to_bytes(6, "big") + randomness.to_bytes(10, "big")


def build_signature_bytes(
    payload: CommandPayload,
    *,
    nonce: str,
    expires_at_ms: int,
) -> bytes:
    payload_bytes = canonical_json_bytes(payload)
    return (
        COMMAND_PREFIX
        + struct.pack(">I", len(payload_bytes))
        + payload_bytes
        + _nonce_bytes(nonce)
        + struct.pack(">Q", expires_at_ms)
    )


def verify_command_signature(
    db: Session,
    *,
    org_id: str,
    expected_roles: frozenset[str],
    payload: CommandPayload,
    approval: dict[str, str | int],
    now: int,
) -> tuple[User, CommandSigningKey]:
    required = {"user_id", "key_id", "nonce", "signed_at_ms", "expires_at_ms", "signature"}
    if set(approval) != required:
        raise CommandAuthorizationError("approval fields are incomplete", 422)
    user_id = approval["user_id"]
    key_id = approval["key_id"]
    nonce = approval["nonce"]
    signed_at = approval["signed_at_ms"]
    expires_at = approval["expires_at_ms"]
    signature_text = approval["signature"]
    if (
        not isinstance(user_id, str)
        or not isinstance(key_id, str)
        or not isinstance(nonce, str)
        or not isinstance(signature_text, str)
    ):
        raise CommandAuthorizationError("approval fields have invalid types", 422)
    if not isinstance(signed_at, int) or isinstance(signed_at, bool):
        raise CommandAuthorizationError("signed_at_ms must be an integer", 422)
    if not isinstance(expires_at, int) or isinstance(expires_at, bool):
        raise CommandAuthorizationError("expires_at_ms must be an integer", 422)
    if signed_at > now + MAX_CLOCK_SKEW_MS or now - signed_at > MAX_SIGNATURE_AGE_MS:
        raise CommandAuthorizationError("signature is stale", 422)
    if (
        expires_at < now
        or expires_at < signed_at
        or expires_at - signed_at > MAX_SIGNATURE_AGE_MS
        or expires_at - now > MAX_SIGNATURE_AGE_MS
    ):
        raise CommandAuthorizationError("signature has expired", 422)

    key = db.query(CommandSigningKey).filter(
        CommandSigningKey.org_id == org_id,
        CommandSigningKey.user_id == user_id,
        CommandSigningKey.key_id == key_id,
        CommandSigningKey.active.is_(True),
        CommandSigningKey.revoked_at.is_(None),
    ).one_or_none()
    user = db.query(User).filter(User.id == user_id, User.org_id == org_id).one_or_none()
    if key is None or user is None or user.role not in expected_roles:
        raise CommandAuthorizationError("approver is not authorized", 403)
    if now - key.created_at > MAX_KEY_AGE_MS:
        raise CommandAuthorizationError("signing key rotation is overdue", 403)
    if db.query(CommandApproval).filter(
        CommandApproval.org_id == org_id,
        CommandApproval.nonce == nonce,
    ).one_or_none() is not None:
        raise CommandAuthorizationError("approval nonce already used", 409)
    try:
        public_key = base64.b64decode(key.public_key, validate=True)
        signature = base64.b64decode(signature_text, validate=True)
        if len(public_key) != 32 or len(signature) != 64:
            raise ValueError("invalid Ed25519 byte length")
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature,
            build_signature_bytes(payload, nonce=nonce, expires_at_ms=expires_at),
        )
    except (OverflowError, ValueError, binascii.Error, InvalidSignature, struct.error) as exc:
        raise CommandAuthorizationError("signature verification failed", 422) from exc
    return user, key


__all__ = [
    "COMMAND_PREFIX",
    "DUAL_CONTROL_ROLES",
    "MAX_KEY_AGE_MS",
    "MAX_SIGNATURE_AGE_MS",
    "CommandAuthorizationError",
    "build_signature_bytes",
    "verify_command_signature",
]
