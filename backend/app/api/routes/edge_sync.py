"""Authenticated HTTP boundary for the durable edge synchronization protocol."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.incident import Incident
from app.models.user import User
from app.realtime.edge_sync import EdgeSync

router = APIRouter(prefix="/incidents/{incident_id}/sync", tags=["offline-sync"])


@router.post("")
def sync_incident_items(
    incident_id: str,
    payload: list[dict[str, Any]],
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Validate and apply an authenticated tenant-scoped outbox batch."""
    del user
    org_id = request.state.org_id or ""
    if db.execute(select(Incident).where(Incident.id == incident_id, Incident.org_id == org_id)).scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return EdgeSync(db).sync(payload, db, org_id, incident_id)


@router.get("")
def sync_status(
    incident_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return only the authenticated organization’s durable sync status."""
    del user
    org_id = request.state.org_id or ""
    if db.execute(select(Incident).where(Incident.id == incident_id, Incident.org_id == org_id)).scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return EdgeSync(db).get_sync_status(incident_id, org_id)
