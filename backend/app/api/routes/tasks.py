"""Response tasks API — list, create, update, assign. Deterministic assignment."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_roles
from app.lib.audit import write_audit
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.entities import OperationalTask, Responder, RoadSegment
from app.models.user import User
from app.optimizer.routing import RouteReliabilityEngine
from app.optimizer.routing_types import Route, RouteSegment
from app.realtime import manager, schedule_broadcast

router = APIRouter(prefix="/incidents/{incident_id}/tasks", tags=["tasks"])
task_router = APIRouter(prefix="/tasks", tags=["tasks"])

_MANAGE_ROLES = ("admin", "emergency_manager", "responder_coordinator")
_VALID_STATUSES = ("pending", "in_progress", "completed", "cancelled", "blocked")
_DEFAULT_SPEED_MPS = 11.176  # ~40 km/h urban emergency
_WORKLOAD_WEIGHT = 300.0  # seconds of equivalent cost per active assignment
_BLOCKED_ROAD_BUFFER_DEG = 200.0 / 111_000.0  # ~200m in degrees


def _to_dict(t: OperationalTask) -> dict[str, Any]:
    return {
        "id": t.id, "org_id": t.org_id, "incident_id": t.incident_id,
        "title": t.title, "status": t.status, "priority": t.priority,
        "assigned_team_id": t.assigned_team_id,
        "required_capability": t.required_capability,
        "assignment_history": t.assignment_history,
        "properties": t.properties,
        "created_at": t.created_at, "updated_at": t.updated_at,
    }


def _fetch_task(
    db: Session, org_id: str, task_id: str, incident_id: str | None = None
) -> OperationalTask:
    stmt = select(OperationalTask).where(
        OperationalTask.org_id == org_id, OperationalTask.id == task_id,
    )
    if incident_id is not None:
        stmt = stmt.where(OperationalTask.incident_id == incident_id)
    task = db.execute(stmt).scalars().first()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.get("")
def list_tasks(
    incident_id: str,
    request: Request,
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List tasks for an incident, optionally filtered by status."""
    org_id = request.state.org_id or ""
    stmt = select(OperationalTask).where(
        OperationalTask.org_id == org_id,
        OperationalTask.incident_id == incident_id,
    )
    if status_filter is not None:
        if status_filter not in _VALID_STATUSES:
            raise HTTPException(
                status_code=422, detail=f"invalid status: {status_filter}"
            )
        stmt = stmt.where(OperationalTask.status == status_filter)
    stmt = stmt.order_by(OperationalTask.created_at.desc())
    rows = db.execute(stmt).scalars().all()
    return {"tasks": [_to_dict(t) for t in rows], "count": len(rows)}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(
    incident_id: str,
    request: Request,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*_MANAGE_ROLES)),
) -> dict[str, Any]:
    """Create a new operational task."""
    org_id = request.state.org_id or ""
    title = payload.get("title")
    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    task_status = payload.get("status", "pending")
    if task_status not in _VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"invalid status: {task_status}")
    geometry = payload.get("geometry")
    if isinstance(geometry, dict) and geometry.get("type") == "Feature":
        geometry = geometry.get("geometry")
    geom_value = (
        func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geometry)), 4326)
        if geometry else None
    )
    task_id = generate_ulid()
    ts = now_ms()
    task = OperationalTask(
        id=task_id, org_id=org_id, incident_id=incident_id, title=title,
        status=task_status, priority=payload.get("priority"),
        required_capability=payload.get("required_capability"),
        geometry=geom_value, properties=payload.get("properties"),
        created_at=ts, updated_at=ts,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    write_audit(db, org_id=org_id, incident_id=incident_id, actor=user.email,
                action="task.created", entity=task_id, after=_to_dict(task))
    result = _to_dict(task)
    schedule_broadcast(
        manager.broadcast(incident_id, {"type": "task_changed", "payload": result}),
        request.app,
    )
    return result


@task_router.patch("/{task_id}")
def update_task_status(
    task_id: str,
    request: Request,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update a task's status (any authenticated user)."""
    org_id = request.state.org_id or ""
    task = _fetch_task(db, org_id, task_id)
    new_status = payload.get("status")
    if new_status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid status: {new_status}; must be one of {list(_VALID_STATUSES)}",
        )
    before = _to_dict(task)
    task.status = new_status
    task.updated_at = now_ms()
    db.commit()
    db.refresh(task)
    write_audit(db, org_id=org_id, incident_id=task.incident_id, actor=user.email,
                action="task.status_updated", entity=task_id,
                before=before, after=_to_dict(task))
    result = _to_dict(task)
    schedule_broadcast(
        manager.broadcast(task.incident_id, {"type": "task_changed", "payload": result}),
        request.app,
    )
    return result


@router.post("/{task_id}/assign")
def assign_task(
    incident_id: str,
    task_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*_MANAGE_ROLES)),
) -> dict[str, Any]:
    """Deterministically assign a task to the best eligible responder.

    INITIAL DETERMINISTIC method — separate from the CVaR optimizer (Task 17).
    Picks the responder with lowest combined travel-cost + workload factor.
    Travel cost is computed via RouteReliabilityEngine.compute_cost().
    """
    org_id = request.state.org_id or ""
    task = _fetch_task(db, org_id, task_id, incident_id)
    if task.assigned_team_id:
        raise HTTPException(status_code=409, detail="task already assigned")
    if not task.required_capability:
        raise HTTPException(status_code=422, detail="task has no required_capability")
    if not task.geometry:
        raise HTTPException(status_code=422, detail="task has no geometry; cannot compute cost")

    responders = db.execute(
        select(Responder).where(
            Responder.org_id == org_id,
            Responder.incident_id == incident_id,
            Responder.status == "available",
            Responder.role == task.required_capability,
        )
    ).scalars().all()
    if not responders:
        raise HTTPException(status_code=409, detail="no eligible responders available")

    near_blocked: set[str] = set()
    rows = db.execute(
        select(Responder.id).join(RoadSegment, func.ST_DWithin(
            Responder.geometry, RoadSegment.geometry, _BLOCKED_ROAD_BUFFER_DEG))
        .where(Responder.id.in_([r.id for r in responders]),
               Responder.org_id == org_id, Responder.incident_id == incident_id,
               RoadSegment.org_id == org_id, RoadSegment.incident_id == incident_id,
               RoadSegment.status.in_(["blocked", "dangerous"])).distinct()
    ).all()
    near_blocked = {row[0] for row in rows}

    engine = RouteReliabilityEngine()
    candidates: list[tuple[float, Responder]] = []
    for resp in responders:
        if resp.id in near_blocked:
            continue
        dist_m = db.execute(
            select(func.ST_DistanceSphere(resp.geometry, task.geometry))
        ).scalar()
        if dist_m is None:
            continue
        seg = RouteSegment(f"{resp.id}-{task.id}", float(dist_m), _DEFAULT_SPEED_MPS)
        route = Route(f"route-{resp.id}-{task.id}", (seg,))
        cost = engine.compute_cost(route).total
        active = _count_active_assignments(db, org_id, resp.id)
        candidates.append((cost + active * _WORKLOAD_WEIGHT, resp))

    if not candidates:
        raise HTTPException(status_code=409, detail="no reachable responders (all blocked)")

    candidates.sort(key=lambda c: c[0])
    best_cost, best_resp = candidates[0]

    before = _to_dict(task)
    ts = now_ms()
    history = list(task.assignment_history or [])
    history.append({"team_id": best_resp.id, "team_name": best_resp.name,
                    "assigned_at": ts, "assigned_by": user.email,
                    "cost": best_cost, "method": "deterministic"})
    task.assigned_team_id = best_resp.id
    task.assignment_history = history
    task.status = "in_progress"
    task.updated_at = ts
    best_resp.status = "assigned"
    best_resp.updated_at = ts
    db.commit()
    db.refresh(task)
    write_audit(db, org_id=org_id, incident_id=incident_id, actor=user.email,
                action="task.assigned", entity=task_id,
                before=before, after=_to_dict(task))
    result = _to_dict(task)
    result["assignment"] = {"team_id": best_resp.id, "team_name": best_resp.name,
                           "cost": best_cost, "method": "deterministic"}
    schedule_broadcast(
        manager.broadcast(incident_id, {"type": "task_changed", "payload": result}),
        request.app,
    )
    return result


def _count_active_assignments(db: Session, org_id: str, team_id: str) -> int:
    return int(db.execute(
        select(func.count()).select_from(OperationalTask).where(
            OperationalTask.org_id == org_id,
            OperationalTask.assigned_team_id == team_id,
            OperationalTask.status.notin_(["completed", "cancelled"]),
        )
    ).scalar() or 0)
