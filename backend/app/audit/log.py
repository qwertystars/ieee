"""Audit logging helper (DESIGN §6 / §7).

Every state-changing action should call ``write_audit``. This is the canonical
implementation; feature modules import it rather than writing AuditLog directly.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def write_audit(
    db: Session,
    user_id: uuid.UUID | None,
    action: str,
    target_type: str | None = None,
    target_id: str | uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Persist an audit log row. Caller is responsible for committing."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=details,
    )
    db.add(entry)
    db.flush()
    return entry
