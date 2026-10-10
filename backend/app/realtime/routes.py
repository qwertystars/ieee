from __future__ import annotations

from typing import Any

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.observations_queries import visible_policies
from app.auth.abac import ABACEngine
from app.auth.abac_types import Actor, Context, Subject
from app.deps import authenticate_realtime_token, get_db, get_realtime_user
from app.lib.serialize import serialize
from app.models.enums import AccessPolicy
from app.models.incident import Incident
from app.models.observation import Observation
from app.models.user import User
from app.realtime.manager import manager

router = APIRouter()


async def _revalidate_stream(
    websocket: WebSocket,
    token: str,
    incident_id: str,
    incident_org_id: str,
    db: Session,
    cancel_scope: anyio.CancelScope,
) -> None:
    while True:
        await anyio.sleep(1)
        try:
            user = authenticate_realtime_token(token, db)
        except HTTPException:
            await websocket.close(code=4401)
            cancel_scope.cancel()
            return
        if not _can_access_incident(user, incident_id, incident_org_id, db):
            await websocket.close(code=4401)
            cancel_scope.cancel()
            return


@router.websocket("/ws/realtime/{incident_id}")
async def realtime_ws(
    websocket: WebSocket,
    incident_id: str,
    token: str | None = Query(None, description="JWT Bearer token"),
    db: Session = Depends(get_db),
) -> None:
    try:
        user = authenticate_realtime_token(token, db)
    except HTTPException:
        await websocket.accept()
        await websocket.close(code=4401)
        return
    incident = db.execute(
        select(Incident).where(
            Incident.id == incident_id,
            Incident.org_id == user.org_id,
        )
    ).scalars().first()
    if incident is None or not _can_access_incident(user, incident_id, incident.org_id, db):
        await websocket.accept()
        await websocket.close(code=4401)
        return

    await manager.connect(websocket, incident_id, user.role, user.org_id)
    try:
        async with anyio.create_task_group() as stream_tasks:
            stream_tasks.start_soon(
                _revalidate_stream,
                websocket,
                token or "",
                incident_id,
                incident.org_id,
                db,
                stream_tasks.cancel_scope,
            )
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                stream_tasks.cancel_scope.cancel()
    finally:
        await manager.disconnect(websocket, incident_id)


@router.get("/api/incidents/{incident_id}/updates")
def polling_updates(
    incident_id: str,
    since: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_realtime_user),
) -> dict[str, Any]:
    incident = db.execute(
        select(Incident).where(
            Incident.id == incident_id,
            Incident.org_id == user.org_id,
        )
    ).scalars().first()
    if incident is None or not _can_access_incident(user, incident_id, user.org_id, db):
        raise HTTPException(status_code=403, detail="incident access denied")

    policies = visible_policies(user.role)
    stmt = (
        select(Observation)
        .where(Observation.org_id == user.org_id)
        .where(Observation.incident_id == incident.id)
        .where(Observation.observed_at > since)
        .where(Observation.access_policy.in_(policies))
        .order_by(Observation.observed_at.asc())
    )
    rows = db.execute(stmt).scalars().all()
    visibility = _visibility_for_role(user.role)
    observations = [_serialize_observation(o, visibility) for o in rows]
    return {
        "incident_id": incident_id,
        "since": since,
        "count": len(observations),
        "observations": observations,
    }


def _serialize_observation(obs: Observation, visibility: str) -> dict[str, Any]:
    return serialize({
        "observation_id": obs.observation_id,
        "incident_id": obs.incident_id,
        "event_type": obs.event_type,
        "phenomenon": obs.phenomenon,
        "value": obs.value,
        "unit": obs.unit,
        "observed_at": obs.observed_at,
        "received_at": obs.received_at,
        "source_id": obs.source_id,
        "source_type": obs.source_type.value if obs.source_type else None,
        "corroboration_state": (
            obs.corroboration_state.value if obs.corroboration_state else None
        ),
        "access_policy": obs.access_policy.value if obs.access_policy else None,
    }, visibility, "official")


def _visibility_for_role(role: str) -> str:
    policies = visible_policies(role)
    if AccessPolicy.sensitive in policies:
        return AccessPolicy.sensitive.value
    if AccessPolicy.internal in policies:
        return AccessPolicy.internal.value
    return AccessPolicy.public.value


def _filter_message(message: dict[str, Any], role: str) -> dict[str, Any] | None:
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return message
    properties = payload.get("properties")
    policy = properties.get("access_policy") if isinstance(properties, dict) else payload.get("access_policy")
    allowed = {policy.value for policy in visible_policies(role)}
    if policy is not None and (not isinstance(policy, str) or policy not in allowed):
        return None
    filtered = dict(message)
    if isinstance(properties, dict):
        filtered_payload = dict(payload)
        filtered_payload["properties"] = serialize(properties, _visibility_for_role(role), "official")
        filtered["payload"] = filtered_payload
    else:
        filtered["payload"] = serialize(payload, _visibility_for_role(role), "official")
    return filtered


def _can_access_incident(
    user: User, incident_id: str, incident_org_id: str, db: Session
) -> bool:
    """Authorize org-member access to the incident feed.

    The incident was already resolved org-scoped by the caller, so cross-org
    and unknown-incident requests never reach this check. Viewers may read
    the public feed (per-record sensitivity filtering is applied downstream
    via ``visible_policies``); operational roles require incident assignment
    through ABAC.
    """
    if user.org_id != incident_org_id:
        return False
    if user.role == "viewer":
        return True
    actor = Actor(
        user_id=user.id,
        role=user.role,
        org_id=user.org_id,
        incident_assignments=(),
    )
    subject = Subject(
        type="incident",
        sensitivity=AccessPolicy.public.value,
        org_id=incident_org_id,
        incident_id=incident_id,
        jurisdiction="all",
    )
    context = Context(current_org_id=user.org_id, current_incident_id=incident_id)
    return ABACEngine(db=db).can(actor, "read", subject, context)
