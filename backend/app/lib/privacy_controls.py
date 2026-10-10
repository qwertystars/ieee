"""Deletion, export, and retention controls for live subject data."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Final, TypedDict

from app.auth.passwords import hash_password
from app.lib.ulid import generate_ulid
from app.models.user import User

MAX_RETENTION_DAYS: Final = 7 * 366
TOMBSTONE_PREFIX: Final = "deleted+"
TOMBSTONE_DOMAIN: Final = "invalid.resqnet"


class SubjectExport(TypedDict):
    subject_id: str
    org_id: str
    role: str | None
    email: str | None
    tombstoned: bool
    subject_pseudonym: str | None
    legal_retention_reason: str | None


@dataclass(frozen=True, slots=True)
class PrivacyTombstone:
    """The non-PII record retained after live subject deletion."""

    subject_id: str
    pseudonym: str
    legal_reason: str
    deleted_at_ms: int
    retention_until_ms: int


def subject_pseudonym(subject_id: str, salt: str | None = None) -> str:
    """Derive a stable salted pseudonym without retaining the subject value."""
    resolved_salt = salt or os.environ.get("PRIVACY_TOMBSTONE_SALT", "resqnet-local-privacy-salt")
    digest = hashlib.sha256((resolved_salt + subject_id).encode("utf-8")).hexdigest()
    return f"subject:{digest[:32]}"


def retention_until_ms(deleted_at_ms: int, tenant_retention_days: int | None = None) -> int:
    """Return the seven-year maximum, reduced by a shorter tenant policy."""
    days = MAX_RETENTION_DAYS if tenant_retention_days is None else min(
        max(tenant_retention_days, 1), MAX_RETENTION_DAYS
    )
    return deleted_at_ms + days * 86_400_000


def tombstone_email(pseudonym: str) -> str:
    """Build a non-routable email replacement containing no original PII."""
    digest = hashlib.sha256(pseudonym.encode("utf-8")).hexdigest()[:32]
    return f"{TOMBSTONE_PREFIX}{digest}@{TOMBSTONE_DOMAIN}"


def is_tombstoned_email(email: str) -> bool:
    """Return whether an email is an internal deletion tombstone."""
    return email.startswith(TOMBSTONE_PREFIX) and email.endswith("@" + TOMBSTONE_DOMAIN)


def export_user(user: User, tombstone: PrivacyTombstone | None = None) -> SubjectExport:
    """Return a subject export that excludes credentials and redacts tombstones."""
    if tombstone is not None or is_tombstoned_email(user.email):
        return {
            "subject_id": user.id,
            "org_id": user.org_id,
            "role": None,
            "email": None,
            "tombstoned": True,
            "subject_pseudonym": tombstone.pseudonym if tombstone else subject_pseudonym(user.id),
            "legal_retention_reason": tombstone.legal_reason if tombstone else None,
        }
    return {
        "subject_id": user.id,
        "org_id": user.org_id,
        "role": user.role,
        "email": user.email,
        "tombstoned": False,
        "subject_pseudonym": None,
        "legal_retention_reason": None,
    }


def apply_user_tombstone(
    user: User,
    *,
    legal_reason: str,
    deleted_at_ms: int,
    tenant_retention_days: int | None = None,
) -> PrivacyTombstone:
    """Remove live login PII and replace it with a bounded retention tombstone."""
    reason = legal_reason.strip()
    if not reason:
        raise ValueError("legal retention reason is required")
    pseudonym = subject_pseudonym(user.id)
    tombstone = PrivacyTombstone(
        subject_id=user.id,
        pseudonym=pseudonym,
        legal_reason=reason,
        deleted_at_ms=deleted_at_ms,
        retention_until_ms=retention_until_ms(deleted_at_ms, tenant_retention_days),
    )
    user.email = tombstone_email(pseudonym)
    user.hashed_password = hash_password(generate_ulid())
    return tombstone


__all__ = [
    "MAX_RETENTION_DAYS",
    "PrivacyTombstone",
    "SubjectExport",
    "apply_user_tombstone",
    "export_user",
    "is_tombstoned_email",
    "retention_until_ms",
    "subject_pseudonym",
    "tombstone_email",
]
