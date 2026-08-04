from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from app.api.routes.command_helpers import alert_dict, get_alert, get_incident, task_dict
from app.audit.reconstruction import AuditContext
from app.auth.command_authorization import (
    DUAL_CONTROL_ROLES,
    CommandAuthorizationError,
    verify_command_signature,
)
from app.deps import get_current_user, get_db, is_token_revoked_strict, oauth2_scheme
from app.lib.audit import (
    JSONValue,
    canonical_json_bytes,
    sha256_hex,
    write_audit,
    write_security_denial,
)
from app.lib.idempotency import IdempotencyConflictError, check_and_record
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.alert import AlertDecision, CommandApproval
from app.models.entities import OperationalTask
from app.models.user import User
from app.realtime import manager, schedule_broadcast

router = APIRouter()
_DUAL_COMMANDS = frozenset({
    "task_creation", "public_warning", "resource_commitment", "high_consequence",
})


class CommandApprovalPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: str = Field(min_length=1, max_length=26)
    key_id: str = Field(min_length=1, max_length=26)
    nonce: str = Field(min_length=26, max_length=26)
    signed_at_ms: int = Field(ge=0)
    expires_at_ms: int = Field(ge=0)
    signature: str = Field(min_length=1)


class CommandRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_type: str = Field(min_length=1, max_length=64)
    rationale: str = Field(min_length=1, max_length=4000)
    approval: CommandApprovalPayload


@router.post("/{alert_id}/dispatch", response_model=None)
def dispatch_alert_command(
    incident_id: str,
    alert_id: str,
    request: Request,
    payload: CommandRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
) -> dict[str, Any] | JSONResponse:
    org_id = request.state.org_id or ""

    def deny(reason_code: str) -> None:
        write_security_denial(
            db, org_id=org_id, incident_id=incident_id, actor=user.id,
            action="command", entity=alert_id, reason_code=reason_code,
        )

    if user.role not in DUAL_CONTROL_ROLES:
        deny("dual_control_role_required")
        raise HTTPException(status_code=403, detail="dual-control roles are required")
    if is_token_revoked_strict(token, db):
        deny("credential_revoked_or_unavailable")
        raise HTTPException(status_code=401, detail="credential state unavailable")
    if payload.command_type not in _DUAL_COMMANDS:
        deny("unsupported_command_type")
        raise HTTPException(status_code=422, detail="unsupported high-consequence command")
    rationale = payload.rationale.strip()
    if not rationale:
        deny("empty_command_rationale")
        raise HTTPException(status_code=422, detail="rationale is required")
    get_incident(db, org_id, incident_id)
    alert = get_alert(db, org_id, incident_id, alert_id)
    command_payload: dict[str, JSONValue] = {
        "incident_id": incident_id, "alert_id": alert_id,
        "command_type": payload.command_type, "rationale": rationale,
    }
    try:
        first_request = check_and_record(
            db, "alert-command", idempotency_key, org_id=org_id,
            incident_id=incident_id, payload=command_payload, commit=False,
        )
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(
        f"{org_id}:{incident_id}:{alert_id}:{payload.command_type}",
    ))))
    decision = db.execute(select(AlertDecision).where(
        AlertDecision.org_id == org_id, AlertDecision.incident_id == incident_id,
        AlertDecision.alert_id == alert_id, AlertDecision.command_type == payload.command_type,
    ).with_for_update()).scalar_one_or_none()
    if not first_request:
        if decision is None:
            db.rollback()
            raise HTTPException(status_code=409, detail="idempotent command has no decision")
        task = db.get(OperationalTask, decision.task_id) if decision.task_id else None
        return {
            "status": "approved" if task is not None else "awaiting_second_approval",
            "task_id": task.id if task is not None else None, "decision_id": decision.id,
            "approval_count": db.query(CommandApproval).filter(
                CommandApproval.decision_id == decision.id,
            ).count(),
        }
    try:
        approver, _ = verify_command_signature(
            db, org_id=org_id, expected_roles=DUAL_CONTROL_ROLES,
            payload=command_payload, approval=payload.approval.model_dump(), now=now_ms(),
        )
    except CommandAuthorizationError as exc:
        deny(exc.detail)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    if approver.id != user.id:
        deny("authenticated_actor_mismatch")
        raise HTTPException(status_code=403, detail="approval must be submitted by the authenticated user")
    if db.query(CommandApproval).filter(
        CommandApproval.org_id == org_id, CommandApproval.nonce == payload.approval.nonce,
    ).one_or_none() is not None:
        deny("approval_nonce_replay")
        raise HTTPException(status_code=409, detail="approval nonce already used")
    if decision is None:
        decision = AlertDecision(
            id=generate_ulid(), org_id=org_id, incident_id=incident_id,
            alert_id=alert_id, command_type=payload.command_type,
            status="awaiting_second_approval", rationale=rationale,
            payload=command_payload, created_by=user.id, created_at=now_ms(), updated_at=now_ms(),
        )
        db.add(decision)
        db.flush()
    else:
        if decision.payload != command_payload:
            deny("command_payload_conflict")
            raise HTTPException(status_code=409, detail="command payload conflicts with decision")
        if decision.task_id:
            task = db.get(OperationalTask, decision.task_id)
            db.rollback()
            if task is None:
                deny("decision_task_unavailable")
                raise HTTPException(status_code=409, detail="decision task is unavailable")
            return {"status": "approved", "task_id": task.id, "decision_id": decision.id, "approval_count": 2}
        previous = db.query(CommandApproval).filter(
            CommandApproval.org_id == org_id, CommandApproval.decision_id == decision.id,
        ).all()
        if any(item.approver_id == approver.id for item in previous):
            deny("approver_reuse")
            raise HTTPException(status_code=409, detail="approver already recorded")
        if previous and previous[0].approver_role == approver.role:
            deny("approval_role_reuse")
            raise HTTPException(status_code=403, detail="two distinct approval roles are required")
    approval = CommandApproval(
        id=generate_ulid(), org_id=org_id, incident_id=incident_id, alert_id=alert_id,
        decision_id=decision.id, approver_id=approver.id, approver_role=approver.role,
        key_id=payload.approval.key_id, nonce=payload.approval.nonce,
        signed_at_ms=payload.approval.signed_at_ms, expires_at_ms=payload.approval.expires_at_ms,
        signature=payload.approval.signature, created_at=now_ms(),
    )
    db.add(approval)
    db.flush()
    approvals = db.query(CommandApproval).filter(
        CommandApproval.org_id == org_id, CommandApproval.decision_id == decision.id,
    ).all()
    if len(approvals) < 2:
        decision.updated_at = now_ms()
        write_audit(
            db, org_id=org_id, incident_id=incident_id, actor=user.email,
            action="alert.command_approval_recorded", entity=alert_id,
            after={"decision_id": decision.id, "command_type": payload.command_type,
                   "approval_count": len(approvals)},
            audit_context=AuditContext(
                actor_id=approver.id, agency_id=org_id, auth_method="ed25519+bearer",
                source_id="api.command", derivation=("alert", "dual_control"),
                signature_hash=f"sha256:{sha256_hex(payload.approval.signature.encode('ascii'))}",
                payload_hash=f"sha256:{sha256_hex(canonical_json_bytes(command_payload))}",
            ),
        )
        result: dict[str, Any] = {"status": "awaiting_second_approval", "task_id": None,
                                  "decision_id": decision.id, "approval_count": len(approvals)}
        schedule_broadcast(
            manager.broadcast(incident_id, {"type": "alert_changed", "payload": alert_dict(alert)}, org_id),
            request.app,
        )
        return JSONResponse(status_code=202, content=result)
    if len(approvals) != 2 or {item.approver_role for item in approvals} != DUAL_CONTROL_ROLES:
        deny("dual_control_quorum_invalid")
        raise HTTPException(status_code=403, detail="emergency_manager and responder_coordinator approvals are required")
    task = OperationalTask(
        id=generate_ulid(), org_id=org_id, incident_id=incident_id,
        title=alert.recommended_action or alert.title, status="pending", priority=alert.severity,
        source_alert_id=alert.id, decision_id=decision.id,
        properties={"alert_id": alert.id, "command_type": payload.command_type,
                    "approval_ids": [item.id for item in approvals]},
        created_at=now_ms(), updated_at=now_ms(),
    )
    db.add(task)
    decision.status = "approved"
    decision.task_id = task.id
    decision.updated_at = now_ms()
    before = alert_dict(alert)
    alert.status = "approved"
    alert.reviewed_by = user.id
    alert.reviewed_at = now_ms()
    alert.review_rationale = rationale
    alert.updated_at = now_ms()
    write_audit(
        db, org_id=org_id, incident_id=incident_id, actor=user.email,
        action="alert.command_authorized", entity=alert_id, before=before,
        after={"alert": alert_dict(alert), "task": task_dict(task),
               "decision_id": decision.id, "approval_ids": [item.id for item in approvals]},
        audit_context=AuditContext(
            actor_id=user.id, agency_id=org_id, auth_method="ed25519+bearer",
            source_id="api.command", derivation=("alert", "dual_control", "task_effect"),
            payload_hash=f"sha256:{sha256_hex(canonical_json_bytes(command_payload))}",
        ),
    )
    result = {"status": "approved", "task_id": task.id, "decision_id": decision.id,
              "approval_count": len(approvals), "task": task_dict(task)}
    schedule_broadcast(
        manager.broadcast(incident_id, {"type": "alert_changed", "payload": alert_dict(alert)}, org_id),
        request.app,
    )
    schedule_broadcast(
        manager.broadcast(incident_id, {"type": "task_changed", "payload": task_dict(task)}, org_id),
        request.app,
    )
    return result
