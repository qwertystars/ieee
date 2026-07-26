"""Audit API — hash-chained event log and decision provenance.

Provides:
- GET /api/incidents/{incident_id}/audit-logs — paginated audit events
- GET /api/decisions/{record_id}/provenance — decision provenance chain
- GET /api/audit/verify — verify the audit hash chain for the current org
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.provenance import ProvenanceChain
from app.audit.provenance_types import REQUIRED_FIELDS
from app.deps import get_current_user, get_db
from app.lib.audit import verify_chain
from app.models.events import Event
from app.models.user import User

router = APIRouter(prefix="", tags=["audit"])

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 500


@router.get("/incidents/{incident_id}/audit-logs")
def list_audit_logs(
    incident_id: str,
    request: Request,
    action: str | None = Query(None),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List paginated audit log entries for an incident."""
    org_id = request.state.org_id or ""
    stmt = select(Event).where(
        Event.org_id == org_id, Event.incident_id == incident_id,
    )
    if action is not None:
        stmt = stmt.where(Event.action == action)
    stmt = stmt.order_by(Event.ts.desc(), Event.id.desc()).limit(limit).offset(offset)
    rows = db.execute(stmt).scalars().all()
    return {
        "logs": [
            {
                "id": e.id, "ts": e.ts, "actor": e.actor,
                "action": e.action, "entity": e.entity,
                "before": e.before, "after": e.after,
                "prev_hash": e.prev_hash, "hash": e.hash,
            }
            for e in rows
        ],
        "count": len(rows),
    }


@router.get("/decisions/{record_id}/provenance")
def get_decision_provenance(
    record_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the full provenance chain for a decision record."""
    org_id = request.state.org_id or ""
    rows = ProvenanceChain.get_provenance(db, org_id, record_id)
    if not rows:
        raise HTTPException(status_code=404, detail="provenance not found")
    verified = ProvenanceChain.verify_chain(db, org_id, record_id)
    return {
        "recommendation_id": record_id,
        "entries": [
            {
                "id": e.id, "ts": e.ts,
                "prev_hash": e.prev_hash, "hash": e.hash,
                **{f: getattr(e, f) for f in REQUIRED_FIELDS},
            }
            for e in rows
        ],
        "verified": verified is True,
    }


@router.get("/audit/verify")
def verify_audit_chain(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Verify the hash-chained audit log for the current org."""
    org_id = request.state.org_id or ""
    result = verify_chain(db, org_id)
    if result is True:
        return {"valid": True}
    return {"valid": False, "first_broken_index": result}
