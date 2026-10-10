"""Incidents API — CRUD + situation report.

An Incident is the top-level container for the response effort. Situation
reports aggregate recent observations, hazards, hypotheses, roads, shelters,
tasks, alerts, and responders into a single structured snapshot.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_roles
from app.lib.audit import write_audit
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.alert import Alert
from app.models.entities import (
    Hazard,
    OperationalTask,
    Responder,
    RoadSegment,
    Shelter,
)
from app.models.hypotheses import Hypothesis
from app.models.incident import Incident
from app.models.observation import Observation
from app.models.user import User

logger = logging.getLogger("app.api.routes.incidents")

router = APIRouter(prefix="/incidents", tags=["incidents"])

_WRITE_ROLES = ("admin", "emergency_manager")
_DEFAULT_LIMIT = 50
_MAX_LIMIT = 500
_SITREP_RECENT_MS = 6 * 60 * 60 * 1000  # 6 hours


def _to_dict(inc: Incident) -> dict[str, Any]:
    return {
        "id": inc.id,
        "org_id": inc.org_id,
        "title": inc.title,
        "disaster_type": inc.disaster_type,
        "severity": inc.severity,
        "status": inc.status,
        "declaration_level": inc.declaration_level,
        "description": inc.description,
        "start_time": inc.start_time,
        "expected_end": inc.expected_end,
        "config": inc.config,
        "created_at": inc.created_at,
        "updated_at": inc.updated_at,
    }


def _get_incident(db: Session, org_id: str, incident_id: str) -> Incident:
    inc = db.execute(
        select(Incident).where(
            Incident.org_id == org_id, Incident.id == incident_id,
        )
    ).scalars().first()
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return inc


@router.get("")
def list_incidents(
    request: Request,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List incidents for the current org."""
    org_id = request.state.org_id or ""
    stmt = select(Incident).where(Incident.org_id == org_id)
    if status_filter is not None:
        stmt = stmt.where(Incident.status == status_filter)
    stmt = stmt.order_by(Incident.start_time.desc()).limit(limit).offset(offset)
    rows = db.execute(stmt).scalars().all()
    return {"incidents": [_to_dict(i) for i in rows], "count": len(rows)}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_incident(
    request: Request,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*_WRITE_ROLES)),
) -> dict[str, Any]:
    """Create a new incident."""
    org_id = request.state.org_id or ""
    title = payload.get("title")
    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    disaster_type = payload.get("disaster_type")
    if not disaster_type:
        raise HTTPException(status_code=422, detail="disaster_type is required")
    ts = now_ms()
    inc_id = generate_ulid()
    geometry = payload.get("geometry")
    geom_value = (
        func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geometry)), 4326)
        if geometry else None
    )
    inc = Incident(
        id=inc_id, org_id=org_id, title=title,
        disaster_type=disaster_type,
        severity=payload.get("severity", "moderate"),
        status=payload.get("status", "active"),
        declaration_level=payload.get("declaration_level"),
        description=payload.get("description"),
        geometry=geom_value,
        start_time=int(payload.get("start_time", ts)),
        expected_end=payload.get("expected_end"),
        config=payload.get("config"),
        created_at=ts, updated_at=ts,
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)
    write_audit(db, org_id=org_id, incident_id=inc_id, actor=user.email,
                action="incident.created", entity=inc_id, after=_to_dict(inc))
    return _to_dict(inc)


@router.get("/{incident_id}")
def get_incident(
    incident_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get a single incident by ID."""
    org_id = request.state.org_id or ""
    return _to_dict(_get_incident(db, org_id, incident_id))


@router.patch("/{incident_id}")
def update_incident(
    incident_id: str,
    request: Request,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*_WRITE_ROLES)),
) -> dict[str, Any]:
    """Update an incident's mutable fields."""
    org_id = request.state.org_id or ""
    inc = _get_incident(db, org_id, incident_id)
    before = _to_dict(inc)
    for field in ("title", "disaster_type", "severity", "status",
                  "declaration_level", "description", "expected_end", "config"):
        if field in payload:
            setattr(inc, field, payload[field])
    inc.updated_at = now_ms()
    db.commit()
    db.refresh(inc)
    write_audit(db, org_id=org_id, incident_id=incident_id, actor=user.email,
                action="incident.updated", entity=incident_id,
                before=before, after=_to_dict(inc))
    return _to_dict(inc)


@router.get("/{incident_id}/situation-report")
def get_situation_report(
    incident_id: str,
    request: Request,
    fmt: str = Query("json", alias="format"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return a structured situation report for an incident.

    Aggregates recent observations, hazards, hypotheses, roads, shelters,
    tasks, alerts, and responders. If format=text, attempts LLM narrative
    (degrades gracefully on failure).
    """
    org_id = request.state.org_id or ""
    inc = _get_incident(db, org_id, incident_id)
    ts_now = now_ms()
    since = ts_now - _SITREP_RECENT_MS

    def _query(model: Any, *, order_col: Any = None, limit_n: int | None = None,
               extra: Any = None) -> list[Any]:
        stmt = select(model).where(
            model.org_id == org_id, model.incident_id == incident_id,
        )
        if extra is not None:
            stmt = stmt.where(extra)
        if order_col is not None:
            stmt = stmt.order_by(order_col)
        if limit_n is not None:
            stmt = stmt.limit(limit_n)
        return list(db.execute(stmt).scalars().all())

    observations = _query(Observation, order_col=Observation.observed_at.desc(),
                          limit_n=50, extra=Observation.observed_at >= since)
    hazards = _query(Hazard)
    hypotheses = _query(Hypothesis, order_col=Hypothesis.probability.desc(), limit_n=20)
    roads = _query(RoadSegment)
    shelters = _query(Shelter)
    tasks = _query(OperationalTask)
    alerts = _query(Alert, order_col=Alert.created_at.desc())
    responders = _query(Responder)

    report: dict[str, Any] = {
        "incident": _to_dict(inc),
        "generated_at": ts_now,
        "window_ms": _SITREP_RECENT_MS,
        "observations": [{"id": o.observation_id, "event_type": o.event_type,
                          "phenomenon": o.phenomenon, "observed_at": o.observed_at}
                         for o in observations],
        "hazards": [{"id": h.id, "hazard_type": h.hazard_type, "severity": h.severity} for h in hazards],
        "hypotheses": [{"id": h.id, "claim": h.claim, "probability": h.probability,
                        "status": h.status.value} for h in hypotheses],
        "roads": [{"id": r.id, "name": r.name, "status": r.status} for r in roads],
        "shelters": [{"id": s.id, "name": s.name, "status": s.status,
                       "capacity": s.capacity, "occupancy": s.occupancy} for s in shelters],
        "tasks": [{"id": t.id, "title": t.title, "status": t.status,
                    "priority": t.priority, "assigned_team_id": t.assigned_team_id} for t in tasks],
        "alerts": [{"id": a.id, "title": a.title, "severity": a.severity,
                     "status": a.status} for a in alerts],
        "responders": [{"id": r.id, "name": r.name, "role": r.role, "status": r.status} for r in responders],
        "provenance_links": [
            {"rel": "self", "href": f"/api/incidents/{incident_id}"},
            {"rel": "audit-logs", "href": f"/api/incidents/{incident_id}/audit-logs"},
            {"rel": "observations", "href": f"/api/observations?incident_id={incident_id}"},
            {"rel": "alerts", "href": f"/api/incidents/{incident_id}/alerts"},
            {"rel": "tasks", "href": f"/api/incidents/{incident_id}/tasks"},
        ],
    }

    if fmt == "text":
        try:
            from app.perception.llm import LLMIntegration

            llm = LLMIntegration(org_id=org_id, incident_id=incident_id,
                                 user_id=user.id, db_session=db)
            briefing = llm.generate_briefing(
                [{"event_type": o.event_type, "phenomenon": o.phenomenon} for o in observations]
            )
            report["narrative"] = briefing.model_dump()
        except Exception as exc:
            logger.warning("LLM briefing failed for %s: %s", incident_id, exc)
            report["narrative"] = None
            report["narrative_error"] = str(exc)

    return report
