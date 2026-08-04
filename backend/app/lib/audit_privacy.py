"""PII-safe values for immutable audit records and operational logs."""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping, Sequence
from typing import TypeAlias

from app.lib.privacy import PII_FIELDS

AuditValue: TypeAlias = None | bool | int | float | str | list["AuditValue"] | dict[str, "AuditValue"]
AuditInput: TypeAlias = None | bool | int | float | str | list["AuditInput"] | dict[str, "AuditInput"]

_EMAIL_RE = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d .()\-]{6,}\d)(?!\w)")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PRIVACY_SALT_ENV = "PRIVACY_TOMBSTONE_SALT"
_DEFAULT_SALT = "resqnet-local-privacy-salt"
_REDACTED = "[REDACTED]"


def redact_text(value: str) -> str:
    """Remove common direct identifiers from free-form audit/log text."""
    redacted = _EMAIL_RE.sub(_REDACTED, value)
    redacted = _SSN_RE.sub(_REDACTED, redacted)
    return _PHONE_RE.sub(_REDACTED, redacted)


def sanitize_audit_value(value: AuditInput, key: str | None = None) -> AuditValue:
    """Recursively remove PII fields and scrub direct identifiers from values."""
    if key is not None and key.casefold().replace("-", "_") in PII_FIELDS:
        return _REDACTED
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            str(item_key): sanitize_audit_value(item, str(item_key))
            for item_key, item in value.items()
            if str(item_key).casefold().replace("-", "_") not in PII_FIELDS
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize_audit_value(item) for item in value]
    return redact_text(str(value))


def pseudonymize_actor(actor: str) -> str:
    """Keep stable non-PII actor IDs while pseudonymizing email-like actors."""
    if _EMAIL_RE.search(actor) is None and _PHONE_RE.search(actor) is None:
        return actor
    salt = os.environ.get(_PRIVACY_SALT_ENV, _DEFAULT_SALT)
    digest = hashlib.sha256((salt + actor).encode("utf-8")).hexdigest()
    return f"subject:{digest[:32]}"


__all__ = ["AuditInput", "AuditValue", "pseudonymize_actor", "redact_text", "sanitize_audit_value"]
