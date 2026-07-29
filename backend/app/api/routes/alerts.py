"""Alerts API — list, approve, dismiss, modify alerts for an incident.

The system NEVER auto-dispatches. Every alert state change (approve, dismiss,
modify) requires admin or emergency_manager role and is recorded in the
hash-chained audit log and the provenance chain.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.provenance import ProvenanceChain
from app.audit.provenance_types import ProvenanceInput
from app.deps import check_sensitive_operation, get_current_user, get_db, oauth2_scheme, require_roles, SensitiveOperation
from app.lib.audit import write_audit, write_break_glass_audit_if_outage
from app.lib.time import now_ms
from app.models.alert import Alert
from app.models.user import User
from app.realtime import manager, schedule_broadcast

logger = logging.getLogger("app.api.routes.alerts")

router = APIRouter(
    prefix="/incidents/{incident_id}/alerts", tags=["alerts"]
)

_REVIEW_ROLES = ("admin", "emergency_manager")
_VALID_STATUSES = ("draft", "approved", "dismissed", "modified")


def _to_dict(a: Alert) -> dict[str, Any]:
    """Serialize an Alert to a JSON-safe dict."""
    return {
        "id": a.id,
        "org_id": a.org_id,
        "incident_id": a.incident_id,
        "alert_type": a.alert_type,
        "title": a.title,
        "message": a.message,
        "severity": a.severity,
        "recommended_action": a.recommended_action,
        "confidence_vector": a.confidence_vector,
        "status": a.status,
        "created_by": a.created_by,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
        "reviewed_by": a.reviewed_by,
        "review_rationale": a.review_rationale,
        "reviewed_at": a.reviewed_at,
    }


def _get_alert(
    db: Session, org_id: str, incident_id: str, alert_id: str
) -> Alert:
    """Fetch an alert, raising 404 if not found or outside this org/incident."""
    stmt = select(Alert).where(
        Alert.org_id == org_id,
        Alert.incident_id == incident_id,
        Alert.id == alert_id,
    )
    alert = db.execute(stmt).scalars().first()
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="alert not found",
        )
    return alert


def _record_provenance(
    db: Session,
    org_id: str,
    alert: Alert,
    user: User,
    action: str,
    rationale: str,
) -> None:
    """Record a provenance entry for an alert decision (best-effort)."""
    cv: Any = alert.confidence_vector or {}
    source_obs = cv.get("source_observation_id") if isinstance(cv, dict) else None
    ProvenanceChain.record_decision(
        db,
        org_id=org_id,
        recommendation_id=alert.id,
        provenance=ProvenanceInput(
            input_observation_ids=[source_obs] if source_obs else [],
            data_versions={},
            model_versions={"alert_rules": "1.0"},
            optimization_parameters={},
            scenario_set=[],
            constraints={"thresholds": {"s": 0.5, "c": 0.2}},
            generated_alternatives=[{"alert_id": alert.id, "type": alert.alert_type}],
            operator_decision={"action": action, "user": user.email},
            override_reason=rationale,
            execution_outcome={"status": alert.status},
        ),
    )


@router.get("")
def list_alerts(
    incident_id: str,
    request: Request,
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List alerts for an incident, optionally filtered by status."""
    org_id = request.state.org_id or ""
    stmt = select(Alert).where(
        Alert.org_id == org_id,
        Alert.incident_id == incident_id,
    )
    if status_filter is not None:
        if status_filter not in _VALID_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"invalid status: {status_filter}",
            )
        stmt = stmt.where(Alert.status == status_filter)
    stmt = stmt.order_by(Alert.created_at.desc())
    rows = db.execute(stmt).scalars().all()
    return {"alerts": [_to_dict(a) for a in rows], "count": len(rows)}


@router.post("/{alert_id}/approve")
def approve_alert(
    incident_id: str,
    alert_id: str,
    request: Request,
    payload: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*_REVIEW_ROLES)),
    token: str = Depends(oauth2_scheme),
) -> dict[str, Any]:
    """Approve an alert — sets status='approved', records audit + provenance.

    The system NEVER auto-dispatches. Approval only marks the alert as ready
    for task creation (wired in Task 15).
    """
    org_id = request.state.org_id or ""
    if not check_sensitive_operation(token, SensitiveOperation.ALERT_APPROVAL):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "operation not permitted")
    alert = _get_alert(db, org_id, incident_id, alert_id)
    rationale = (payload or {}).get("review_rationale", "")
    ts = now_ms()
    before = _to_dict(alert)
    alert.status = "approved"
    alert.reviewed_by = user.id
    alert.reviewed_at = ts
    alert.review_rationale = rationale
    alert.updated_at = ts
    db.commit()
    db.refresh(alert)
    write_audit(
        db,
        org_id=org_id,
        incident_id=incident_id,
        actor=user.email,
        action="alert.approved",
        entity=alert.id,
        before=before,
        after=_to_dict(alert),
    )
    write_break_glass_audit_if_outage(db, org_id, incident_id, user.email, alert.id, SensitiveOperation.ALERT_APPROVAL.value)
    try:
        _record_provenance(db, org_id, alert, user, "approve", rationale)
    except Exception as exc:
        logger.warning("provenance record failed for alert %s: %s", alert.id, exc)
    # TODO: Create task from approved alert (todo 15)
    result = _to_dict(alert)
    schedule_broadcast(
        manager.broadcast(incident_id, {"type": "alert_changed", "payload": result}),
        request.app,
    )
    return result


@router.post("/{alert_id}/dismiss")
def dismiss_alert(
    incident_id: str,
    alert_id: str,
    request: Request,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*_REVIEW_ROLES)),
) -> dict[str, Any]:
    """Dismiss an alert with a required rationale."""
    org_id = request.state.org_id or ""
    alert = _get_alert(db, org_id, incident_id, alert_id)
    rationale = payload.get("review_rationale")
    if not rationale:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="review_rationale is required to dismiss",
        )
    ts = now_ms()
    before = _to_dict(alert)
    alert.status = "dismissed"
    alert.reviewed_by = user.id
    alert.reviewed_at = ts
    alert.review_rationale = rationale
    alert.updated_at = ts
    db.commit()
    db.refresh(alert)
    write_audit(
        db,
        org_id=org_id,
        incident_id=incident_id,
        actor=user.email,
        action="alert.dismissed",
        entity=alert.id,
        before=before,
        after=_to_dict(alert),
    )
    result = _to_dict(alert)
    schedule_broadcast(
        manager.broadcast(incident_id, {"type": "alert_changed", "payload": result}),
        request.app,
    )
    return result


@router.post("/{alert_id}/modify")
def modify_alert(
    incident_id: str,
    alert_id: str,
    request: Request,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*_REVIEW_ROLES)),
) -> dict[str, Any]:
    """Modify the recommended_action of an alert before approving."""
    org_id = request.state.org_id or ""
    alert = _get_alert(db, org_id, incident_id, alert_id)
    new_action = payload.get("recommended_action")
    if not new_action:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="recommended_action is required",
        )
    ts = now_ms()
    before = _to_dict(alert)
    alert.recommended_action = new_action
    if alert.status == "draft":
        alert.status = "modified"
    alert.reviewed_by = user.id
    alert.reviewed_at = ts
    alert.review_rationale = "modified recommended_action"
    alert.updated_at = ts
    db.commit()
    db.refresh(alert)
    write_audit(
        db,
        org_id=org_id,
        incident_id=incident_id,
        actor=user.email,
        action="alert.modified",
        entity=alert.id,
        before=before,
        after=_to_dict(alert),
    )
    result = _to_dict(alert)
    schedule_broadcast(
        manager.broadcast(incident_id, {"type": "alert_changed", "payload": result}),
        request.app,
    )
    return result
