from __future__ import annotations

import logging
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.auth.command_authorization import COMMAND_PREFIX, build_signature_bytes
from app.lib.audit import canonical_json_bytes
from app.lib.audit_privacy import sanitize_audit_value
from app.lib.logging_config import JsonFormatter
from app.lib.privacy_controls import (
    apply_user_tombstone,
    is_tombstoned_email,
    retention_until_ms,
    subject_pseudonym,
    tombstone_email,
)
from app.models.user import User


def test_signature_frame_is_fixed_length_delimited_bytes() -> None:
    payload = {"message": "réscue", "command": "dispatch"}
    nonce = "01J5V9P7W6G8M3Q2R1T0Y9X8Z7"
    expires_at_ms = 1_800_000_000_000
    payload_bytes = canonical_json_bytes(payload)
    framed = build_signature_bytes(payload, nonce=nonce, expires_at_ms=expires_at_ms)
    assert framed.startswith(COMMAND_PREFIX + struct.pack(">I", len(payload_bytes)))
    assert framed[len(COMMAND_PREFIX) + 4 : -24] == payload_bytes
    assert len(framed[-24:-8]) == 16
    assert framed[-8:] == struct.pack(">Q", expires_at_ms)


def test_audit_sanitizer_removes_nested_pii_and_direct_identifiers() -> None:
    value = sanitize_audit_value({
        "email": "person@example.invalid",
        "nested": {"phone": "+1 555 123 4567", "safe": "source-1"},
        "reason": "incident owner person@example.invalid",
    })
    assert isinstance(value, dict)
    assert "email" not in value
    assert value["nested"] == {"safe": "source-1"}
    assert "person@example.invalid" not in str(value)


def test_tombstone_is_salted_bounded_and_non_routable() -> None:
    user = User(id="01J5V9P7W6G8M3Q2R1T0Y9X8Z7", email="person@example.invalid", hashed_password="hash", role="viewer", org_id="org", created_at=1)
    tombstone = apply_user_tombstone(user, legal_reason="statutory deletion", deleted_at_ms=1_000, tenant_retention_days=2)
    assert tombstone.pseudonym == subject_pseudonym(user.id)
    assert tombstone.retention_until_ms == retention_until_ms(1_000, 2)
    assert is_tombstoned_email(user.email)
    assert user.email == tombstone_email(tombstone.pseudonym)
    assert "person@example.invalid" not in user.email


def test_json_logs_redact_direct_identifiers_in_message_text() -> None:
    record = logging.LogRecord("task21", logging.WARNING, __file__, 1, "contact person@example.invalid", (), None)
    rendered = JsonFormatter().format(record)
    assert "person@example.invalid" not in rendered
