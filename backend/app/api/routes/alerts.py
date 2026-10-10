from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.alert_commands import router as command_router
from app.audit.provenance import ProvenanceChain
from app.audit.provenance_types import ProvenanceInput
from app.deps import (
    SensitiveOperation,
    check_sensitive_operation,
    get_current_user,
    get_db,
    oauth2_scheme,
    require_roles,
)
from app.lib.audit import write_audit, write_break_glass_audit_if_outage
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.alert import Alert, AlertDecision
from app.models.user import User
from app.realtime import manager, schedule_broadcast

logger = logging.getLogger("app.api.routes.alerts")
router = APIRouter(prefix="/incidents/{incident_id}/alerts", tags=["alerts"])
_REVIEW_ROLES = ("admin", "emergency_manager")
_VALID_STATUSES = ("draft", "approved", "dismissed", "modified")


class AlertApprovalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_rationale: str = Field(min_length=1, max_length=4000)


def _to_dict(alert: Alert) -> dict[str, Any]:
    return {
        "id": alert.id, "org_id": alert.org_id, "incident_id": alert.incident_id,
        "alert_type": alert.alert_type, "title": alert.title, "message": alert.message,
        "severity": alert.severity, "recommended_action": alert.recommended_action,
        "confidence_vector": alert.confidence_vector, "status": alert.status,
        "created_by": alert.created_by, "created_at": alert.created_at,
        "updated_at": alert.updated_at, "reviewed_by": alert.reviewed_by,
        "review_rationale": alert.review_rationale, "reviewed_at": alert.reviewed_at,
    }


def _get_alert(db: Session, org_id: str, incident_id: str, alert_id: str) -> Alert:
    alert = db.execute(select(Alert).where(
        Alert.org_id == org_id, Alert.incident_id == incident_id, Alert.id == alert_id,
    )).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return alert


def _record_provenance(
    db: Session, org_id: str, alert: Alert, user: User, action: str, rationale: str,
) -> None:
    raw_confidence = alert.confidence_vector
    confidence: dict[str, Any] = raw_confidence if isinstance(raw_confidence, dict) else {}
    source_obs = confidence.get("source_observation_id") if isinstance(confidence, dict) else None
    ProvenanceChain.record_decision(
        db, org_id=org_id, recommendation_id=alert.id,
        provenance=ProvenanceInput(
            input_observation_ids=[source_obs] if source_obs else [], data_versions={},
            model_versions={"alert_rules": "1.0"}, optimization_parameters={}, scenario_set=[],
            constraints={"thresholds": {"s": 0.5, "c": 0.2}},
            generated_alternatives=[{"alert_id": alert.id, "type": alert.alert_type}],
            operator_decision={"action": action, "user": user.email},
            override_reason=rationale, execution_outcome={"status": alert.status},
        ),
    )


@router.get("")
def list_alerts(
    incident_id: str, request: Request,
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
) -> dict[str, Any]:
    org_id = request.state.org_id or ""
    stmt = select(Alert).where(Alert.org_id == org_id, Alert.incident_id == incident_id)
    if status_filter is not None:
        if status_filter not in _VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"invalid status: {status_filter}")
        stmt = stmt.where(Alert.status == status_filter)
    rows = db.execute(stmt.order_by(Alert.created_at.desc())).scalars().all()
    return {"alerts": [_to_dict(alert) for alert in rows], "count": len(rows)}


@router.post("/{alert_id}/approve")
def approve_alert(
    incident_id: str, alert_id: str, request: Request, payload: AlertApprovalPayload,
    db: Session = Depends(get_db), user: User = Depends(require_roles(*_REVIEW_ROLES)),
    token: str = Depends(oauth2_scheme),
) -> dict[str, Any]:
    org_id = request.state.org_id or ""
    if not check_sensitive_operation(token, SensitiveOperation.ALERT_APPROVAL, db):
        raise HTTPException(status_code=403, detail="operation not permitted")
    alert = _get_alert(db, org_id, incident_id, alert_id)
    rationale = payload.review_rationale.strip()
    if not rationale:
        raise HTTPException(status_code=422, detail="review_rationale is required")
    decision = db.execute(select(AlertDecision).where(
        AlertDecision.org_id == org_id, AlertDecision.incident_id == incident_id,
        AlertDecision.alert_id == alert_id, AlertDecision.command_type == "alert_approval",
    )).scalar_one_or_none()
    if decision is not None and decision.status == "approved":
        return _to_dict(alert)
    ts = now_ms()
    before = _to_dict(alert)
    alert.status = "approved"
    alert.reviewed_by = user.id
    alert.reviewed_at = ts
    alert.review_rationale = rationale
    alert.updated_at = ts
    if decision is None:
        db.add(AlertDecision(
            id=generate_ulid(), org_id=org_id, incident_id=incident_id, alert_id=alert_id,
            command_type="alert_approval", status="approved", rationale=rationale,
            payload={"alert_id": alert_id, "command_type": "alert_approval"},
            created_by=user.id, created_at=ts, updated_at=ts,
        ))
    else:
        decision.status = "approved"
        decision.rationale = rationale
        decision.updated_at = ts
    write_audit(
        db, org_id=org_id, incident_id=incident_id, actor=user.email,
        action="alert.approved", entity=alert.id, before=before, after=_to_dict(alert),
    )
    db.refresh(alert)
    write_break_glass_audit_if_outage(
        db, org_id, incident_id, user.email, alert.id, SensitiveOperation.ALERT_APPROVAL.value,
    )
    try:
        _record_provenance(db, org_id, alert, user, "approve", rationale)
    except Exception as exc:
        logger.warning("provenance record failed for alert %s: %s", alert.id, exc)
    result = _to_dict(alert)
    schedule_broadcast(
        manager.broadcast(
            incident_id, {"type": "alert_changed", "payload": result}, org_id,
        ),
        request.app,
    )
    return result


@router.post("/{alert_id}/dismiss")
def dismiss_alert(
    incident_id: str, alert_id: str, request: Request, payload: dict[str, Any],
    db: Session = Depends(get_db), user: User = Depends(require_roles(*_REVIEW_ROLES)),
) -> dict[str, Any]:
    org_id = request.state.org_id or ""
    alert = _get_alert(db, org_id, incident_id, alert_id)
    rationale = payload.get("review_rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise HTTPException(status_code=422, detail="review_rationale is required to dismiss")
    ts = now_ms()
    before = _to_dict(alert)
    alert.status = "dismissed"
    alert.reviewed_by = user.id
    alert.reviewed_at = ts
    alert.review_rationale = rationale.strip()
    alert.updated_at = ts
    db.commit()
    db.refresh(alert)
    write_audit(db, org_id=org_id, incident_id=incident_id, actor=user.email,
                action="alert.dismissed", entity=alert.id, before=before, after=_to_dict(alert))
    result = _to_dict(alert)
    schedule_broadcast(
        manager.broadcast(
            incident_id, {"type": "alert_changed", "payload": result}, org_id,
        ),
        request.app,
    )
    return result


@router.post("/{alert_id}/modify")
def modify_alert(
    incident_id: str, alert_id: str, request: Request, payload: dict[str, Any],
    db: Session = Depends(get_db), user: User = Depends(require_roles(*_REVIEW_ROLES)),
) -> dict[str, Any]:
    org_id = request.state.org_id or ""
    alert = _get_alert(db, org_id, incident_id, alert_id)
    new_action = payload.get("recommended_action")
    if not isinstance(new_action, str) or not new_action.strip():
        raise HTTPException(status_code=422, detail="recommended_action is required")
    ts = now_ms()
    before = _to_dict(alert)
    alert.recommended_action = new_action.strip()
    if alert.status == "draft":
        alert.status = "modified"
    alert.reviewed_by = user.id
    alert.reviewed_at = ts
    alert.review_rationale = "modified recommended_action"
    alert.updated_at = ts
    db.commit()
    db.refresh(alert)
    write_audit(db, org_id=org_id, incident_id=incident_id, actor=user.email,
                action="alert.modified", entity=alert.id, before=before, after=_to_dict(alert))
    result = _to_dict(alert)
    schedule_broadcast(
        manager.broadcast(
            incident_id, {"type": "alert_changed", "payload": result}, org_id,
        ),
        request.app,
    )
    return result


router.include_router(command_router)
