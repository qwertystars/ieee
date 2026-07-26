"""Hypotheses API — GET/POST /api/incidents/{incident_id}/hypotheses.

Lists hypotheses (including contradictory ones) and creates new ones.
Contradictory hypotheses are preserved — never deleted or overwritten.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_roles
from app.knowledge.graph import KnowledgeGraph
from app.lib.audit import write_audit
from app.lib.time import now_ms
from app.models.enums import HypothesisStatus
from app.models.hypotheses import Hypothesis
from app.models.user import User
from app.realtime import manager, schedule_broadcast

router = APIRouter(
    prefix="/incidents/{incident_id}/hypotheses", tags=["hypotheses"]
)

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 500
_WRITE_ROLES = ("admin", "emergency_manager", "responder_coordinator")


def _to_dict(h: Hypothesis) -> dict[str, Any]:
    """Serialize a Hypothesis to a dict for JSON response."""
    return {
        "id": h.id,
        "org_id": h.org_id,
        "incident_id": h.incident_id,
        "entity_type": h.entity_type,
        "entity_id": h.entity_id,
        "claim": h.claim,
        "probability": h.probability,
        "supporting_evidence": h.supporting_evidence,
        "contradicting_evidence": h.contradicting_evidence,
        "status": h.status.value if h.status else None,
        "created_at": h.created_at,
        "updated_at": h.updated_at,
        "data_age_ms": now_ms() - h.updated_at,
    }


@router.get("")
def list_hypotheses(
    incident_id: str,
    request: Request,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List hypotheses for an incident, optionally filtered by status.

    Returns ALL hypotheses including contradictory ones — the system never
    silently discards a hypothesis. Filter by status using the query param.
    """
    org_id = request.state.org_id or ""
    stmt = select(Hypothesis).where(
        Hypothesis.org_id == org_id,
        Hypothesis.incident_id == incident_id,
    )
    if status_filter is not None:
        try:
            status_enum = HypothesisStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"invalid status: {status_filter}",
            ) from None
        stmt = stmt.where(Hypothesis.status == status_enum)
    stmt = stmt.order_by(Hypothesis.created_at.desc()).limit(limit).offset(offset)
    rows = db.execute(stmt).scalars().all()
    return {
        "hypotheses": [_to_dict(h) for h in rows],
        "count": len(rows),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_hypothesis(
    incident_id: str,
    request: Request,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*_WRITE_ROLES)),
) -> dict[str, Any]:
    """Create a new hypothesis for an incident.

    The hypothesis is created with status=active. Contradictory hypotheses
    coexist — creating a new one does NOT modify or delete existing ones.
    """
    org_id = request.state.org_id
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="org_id not resolved from token",
        )
    claim = payload.get("claim")
    entity_type = payload.get("entity_type")
    entity_id = payload.get("entity_id")
    if not claim or not entity_type or not entity_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="claim, entity_type, entity_id are required",
        )
    probability = float(payload.get("probability", 0.5))
    kg = KnowledgeGraph(db, org_id, incident_id)
    hid = kg.add_hypothesis(
        entity_type=entity_type,
        entity_id=entity_id,
        claim=claim,
        probability=probability,
        supporting_evidence=payload.get("supporting_evidence"),
        contradicting_evidence=payload.get("contradicting_evidence"),
    )
    write_audit(
        db,
        org_id=org_id,
        incident_id=incident_id,
        actor=user.email,
        action="hypothesis.created",
        entity=hid,
        after={
            "claim": claim,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "probability": probability,
        },
    )
    h = db.get(Hypothesis, hid)
    result = _to_dict(h)  # type: ignore[arg-type]
    schedule_broadcast(
        manager.broadcast_hypothesis(incident_id, result),
        request.app,
    )
    return result
