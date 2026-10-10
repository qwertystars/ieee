"""Authenticated subject export and deletion endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.lib.audit import write_audit, write_security_denial
from app.lib.privacy_controls import (
    PrivacyTombstone,
    apply_user_tombstone,
    export_user,
    is_tombstoned_email,
)
from app.lib.time import now_ms
from app.models.events import Event
from app.models.user import User

router = APIRouter(prefix="/privacy", tags=["privacy"])


class DeleteSubjectRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    legal_reason: str = Field(min_length=1, max_length=500)


def _target_user(db: Session, org_id: str, subject_id: str) -> User:
    target = db.execute(
        select(User).where(User.org_id == org_id, User.id == subject_id)
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="subject not found")
    return target


def _last_tombstone(db: Session, subject_id: str) -> tuple[str, str] | None:
    event = db.execute(
        select(Event).where(
            Event.action == "privacy.subject_deleted",
            Event.entity == f"user:{subject_id}",
        ).order_by(Event.ts.desc(), Event.id.desc()).limit(1)
    ).scalar_one_or_none()
    if event is None or not isinstance(event.after, dict):
        return None
    pseudonym = event.after.get("subject_pseudonym")
    reason = event.after.get("legal_retention_reason")
    if not isinstance(pseudonym, str) or not isinstance(reason, str):
        return None
    return pseudonym, reason


def _authorize_target(
    db: Session,
    request: Request,
    current_user: User,
    subject_id: str,
    action: str,
) -> User:
    org_id = request.state.org_id or ""
    target = _target_user(db, org_id, subject_id)
    if target.id == current_user.id or current_user.role == "admin":
        return target
    write_security_denial(
        db,
        org_id=org_id,
        incident_id="",
        actor=current_user.id,
        action=action,
        entity=f"user:{subject_id}",
        reason_code="subject_scope_denied",
    )
    raise HTTPException(status_code=403, detail="subject export/deletion is not authorized")


@router.get("/export")
def export_current_subject(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Export only the authenticated subject's PII and retention metadata."""
    return _export_subject(db, request, current_user, current_user.id)


@router.get("/subjects/{subject_id}/export")
def export_subject_record(
    subject_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Allow self export or an explicitly authorized administrator export."""
    return _export_subject(db, request, current_user, subject_id)


def _export_subject(db: Session, request: Request, current_user: User, subject_id: str) -> dict:
    target = _authorize_target(db, request, current_user, subject_id, "privacy_export")
    tombstone_data = _last_tombstone(db, target.id)
    tombstone = None
    if tombstone_data is not None:
        tombstone = PrivacyTombstone(
            subject_id=target.id,
            pseudonym=tombstone_data[0],
            legal_reason=tombstone_data[1],
            deleted_at_ms=0,
            retention_until_ms=0,
        )
    result = export_user(target, tombstone=tombstone)
    write_audit(
        db,
        org_id=request.state.org_id or "",
        incident_id="",
        actor=current_user.id,
        action="privacy.export",
        entity=f"user:{target.id}",
        after={"subject_id": target.id, "tombstoned": result["tombstoned"]},
    )
    return dict(result)


@router.post("/delete")
def delete_current_subject(
    body: DeleteSubjectRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Tombstone the authenticated subject while retaining a legal audit reason."""
    return _delete_subject(db, request, current_user, current_user.id, body.legal_reason)


@router.post("/subjects/{subject_id}/delete")
def delete_subject_record(
    subject_id: str,
    body: DeleteSubjectRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Restrict administrative deletion of another subject to admins."""
    target = _target_user(db, request.state.org_id or "", subject_id)
    if target.id != current_user.id and current_user.role != "admin":
        write_security_denial(
            db,
            org_id=request.state.org_id or "",
            incident_id="",
            actor=current_user.id,
            action="privacy_delete",
            entity=f"user:{subject_id}",
            reason_code="subject_scope_denied",
        )
        raise HTTPException(status_code=403, detail="subject deletion is not authorized")
    return _delete_subject(db, request, current_user, subject_id, body.legal_reason)


def _delete_subject(
    db: Session,
    request: Request,
    current_user: User,
    subject_id: str,
    legal_reason: str,
) -> dict:
    target = _target_user(db, request.state.org_id or "", subject_id)
    if is_tombstoned_email(target.email):
        write_security_denial(
            db,
            org_id=request.state.org_id or "",
            incident_id="",
            actor=current_user.id,
            action="privacy_delete",
            entity=f"user:{subject_id}",
            reason_code="subject_already_tombstoned",
        )
        raise HTTPException(status_code=409, detail="subject is already deleted")
    tombstone = apply_user_tombstone(target, legal_reason=legal_reason, deleted_at_ms=now_ms())
    write_audit(
        db,
        org_id=request.state.org_id or "",
        incident_id="",
        actor=current_user.id,
        action="privacy.subject_deleted",
        entity=f"user:{subject_id}",
        after={
            "subject_pseudonym": tombstone.pseudonym,
            "legal_retention_reason": tombstone.legal_reason,
            "retention_until_ms": tombstone.retention_until_ms,
        },
    )
    return {
        "status": "tombstoned",
        "subject_id": subject_id,
        "subject_pseudonym": tombstone.pseudonym,
        "retention_until_ms": tombstone.retention_until_ms,
    }


__all__ = ["router"]
