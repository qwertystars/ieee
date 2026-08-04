"""Scoped lookup and response projection helpers for command routes."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.entities import OperationalTask
from app.models.incident import Incident


def get_incident(db: Session, org_id: str, incident_id: str) -> None:
    """Require an incident owned by the authenticated organization."""
    incident = db.execute(select(Incident).where(Incident.org_id == org_id, Incident.id == incident_id)).scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")


def get_alert(db: Session, org_id: str, incident_id: str, alert_id: str) -> Alert:
    """Require an alert owned by the organization and incident."""
    alert = db.execute(select(Alert).where(Alert.org_id == org_id, Alert.incident_id == incident_id, Alert.id == alert_id)).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return alert


def alert_dict(alert: Alert) -> dict[str, Any]:
    """Project an alert into a realtime-safe command response."""
    return {
        "id": alert.id, "org_id": alert.org_id, "incident_id": alert.incident_id,
        "alert_type": alert.alert_type, "title": alert.title, "message": alert.message,
        "severity": alert.severity, "recommended_action": alert.recommended_action,
        "confidence_vector": alert.confidence_vector, "status": alert.status,
        "created_by": alert.created_by, "created_at": alert.created_at,
        "updated_at": alert.updated_at, "reviewed_by": alert.reviewed_by,
        "review_rationale": alert.review_rationale, "reviewed_at": alert.reviewed_at,
    }


def task_dict(task: OperationalTask) -> dict[str, Any]:
    """Project an operational task into a realtime-safe command response."""
    return {
        "id": task.id, "org_id": task.org_id, "incident_id": task.incident_id,
        "title": task.title, "status": task.status, "priority": task.priority,
        "source_alert_id": task.source_alert_id, "decision_id": task.decision_id,
        "properties": task.properties, "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


__all__ = ["alert_dict", "get_alert", "get_incident", "task_dict"]
