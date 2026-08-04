"""Observations API — POST/GET/GET-by-id, all GeoJSON Feature/FeatureCollection.

org_id is always taken from `request.state.org_id` (set by OrgContextMiddleware
from the signed JWT), never from the request body or query params.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes.observations_fusion import run_single_post_commit_fusion
from app.api.routes.observations_queries import (
    apply_filters,
    fetch_feature,
    to_feature,
    visible_policies,
)
from app.api.routes.observations_validation import parse_feature
from app.deps import get_current_user, get_db, require_roles
from app.lib.idempotency import (
    IdempotencyConflictError,
    claim_raw_event,
    lookup_observation_id,
    next_raw_sequence,
)
from app.lib.observability_metrics import record_event_state
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.models.events import RawEvent
from app.models.observation import Observation
from app.models.user import User
from app.realtime import manager, schedule_broadcast

logger = logging.getLogger("app.api.routes.observations")

router = APIRouter(prefix="/observations", tags=["observations"])

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 500
_WRITE_ROLES = (
    "admin",
    "emergency_manager",
    "responder_coordinator",
    "field_responder",
)


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    parts = bbox.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="bbox must be minx,miny,maxx,maxy",
        )
    try:
        return tuple(float(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="bbox values must be numeric",
        ) from None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_observation(
    request: Request,
    background_tasks: BackgroundTasks,
    feature: dict[str, Any],
    incident_id: str = Query(..., description="Incident ID to scope this observation to"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*_WRITE_ROLES)),
) -> dict[str, Any]:
    """Create an observation from a GeoJSON Feature.

    The Feature's `properties` carry observation fields; `geometry` is a GeoJSON
    geometry. org_id is taken from request.state.org_id (JWT-derived), never
    from the body.
    """
    org_id = request.state.org_id
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="org_id not resolved from token",
        )

    feature = parse_feature(feature)
    geometry = feature["geometry"]
    props = feature["properties"]

    observation_id = generate_ulid()
    ts_now = now_ms()
    observed_at = props.get("observed_at") or ts_now
    source_id = str(props["source_id"])
    external_id = str(props.get("external_id") or idempotency_key or observation_id)
    raw_event = RawEvent(
        event_id=generate_ulid(),
        org_id=org_id,
        incident_id=incident_id,
        source_id=source_id,
        external_id=external_id,
        event_type=str(props["event_type"]),
        source_time_ms=observed_at,
        receipt_time_ms=ts_now,
        sequence=next_raw_sequence(db, org_id, source_id),
        payload=feature,
    )
    try:
        is_new = claim_raw_event(db, raw_event, feature, idempotency_key)
    except IdempotencyConflictError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="idempotency key conflicts with a different payload",
        ) from None
    if not is_new:
        existing_id = lookup_observation_id(db, org_id, source_id, external_id)
        if existing_id is not None:
            existing = fetch_feature(db, existing_id, org_id)
            if existing is not None:
                return existing
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="idempotency record has no observation projection",
        )

    obs = Observation(
        observation_id=observation_id,
        event_type=props["event_type"],
        phenomenon=props["phenomenon"],
        value=props.get("value"),
        unit=props.get("unit"),
        geometry=func.ST_SetSRID(
            func.ST_GeomFromGeoJSON(json.dumps(geometry)), 4326
        ),
        geometry_uncertainty=float(props.get("geometry_uncertainty", 0.0)),
        observed_at=observed_at,
        valid_from=props.get("valid_from") or observed_at,
        valid_until=props.get("valid_until"),
        received_at=ts_now,
        source_id=source_id,
        source_type=SourceType(str(props.get("source_type", "other")).lower()),
        collection_method=props.get("collection_method", "unknown"),
        source_reliability=float(props.get("source_reliability", 0.5)),
        freshness=float(props.get("freshness", 1.0)),
        corroboration_state=CorroborationState(
            props.get("corroboration_state", "uncorroborated")
        ),
        model_uncertainty=props.get("model_uncertainty"),
        quality_flags=props.get("quality_flags", {}),
        access_policy=AccessPolicy(props.get("access_policy", "internal")),
        provenance_chain=props.get("provenance_chain", {}),
        raw_data_hash=props.get("raw_data_hash", ""),
        model_version=props.get("model_version"),
        supersedes=props.get("supersedes"),
        duplicate_group=props.get("duplicate_group"),
        org_id=org_id,
        incident_id=incident_id,
        raw_event_id=raw_event.event_id,
        source_time_ms=raw_event.source_time_ms,
        receipt_time_ms=raw_event.receipt_time_ms,
        sequence=raw_event.sequence,
        payload_hash=raw_event.canonical_hash(),
        visibility=raw_event.visibility.value,
        review_status=raw_event.review_status.value,
        schema_version=raw_event.schema_version,
    )
    db.add(obs)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="observation could not be created (constraint violation)",
        ) from None
    db.refresh(obs)
    record_event_state("accepted", "api", "observations.raw")

    background_tasks.add_task(
        run_single_post_commit_fusion,
        observation_id,
        org_id,
        incident_id,
        user.email,
    )

    result = fetch_feature(db, observation_id, org_id)
    if result is not None:
        schedule_broadcast(
            manager.broadcast_observation(incident_id, result, org_id),
            request.app,
        )
    return result  # type: ignore[return-value]


@router.get("")
def list_observations(
    request: Request,
    incident_id: str | None = Query(None),
    source_id: str | None = Query(None),
    phenomenon: str | None = Query(None),
    observed_start: int | None = Query(None, description="observed_at >= (epoch ms)"),
    observed_end: int | None = Query(None, description="observed_at <= (epoch ms)"),
    recent_ms: int | None = Query(
        None, description="only observations from last N ms"
    ),
    bbox: str | None = Query(None, description="minx,miny,maxx,maxy"),
    confidence_s: float | None = Query(
        None, description="confidence_vector.s >= value"
    ),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List observations as a GeoJSON FeatureCollection with filters."""
    org_id = request.state.org_id or ""
    policies = visible_policies(user.role)
    bbox_tuple = _parse_bbox(bbox)

    stmt = select(
        Observation, func.ST_AsGeoJSON(Observation.geometry).label("geojson")
    )
    stmt = apply_filters(
        stmt,
        org_id=org_id,
        incident_id=incident_id,
        source_id=source_id,
        phenomenon=phenomenon,
        observed_start=observed_start,
        observed_end=observed_end,
        recent_ms=recent_ms,
        bbox=bbox_tuple,
        confidence_s=confidence_s,
        policies=policies,
    )
    stmt = stmt.order_by(Observation.observed_at.desc()).limit(limit).offset(offset)

    rows = db.execute(stmt).all()
    features = [
        to_feature(obs, json.loads(g) if g else None) for obs, g in rows
    ]
    return {"type": "FeatureCollection", "features": features}


@router.get("/{observation_id}")
def get_observation(
    observation_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return a single observation as a GeoJSON Feature."""
    org_id = request.state.org_id or ""
    result = fetch_feature(db, observation_id, org_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="observation not found",
        )
    props = result.get("properties") or {}
    access = props.get("access_policy")
    allowed = {p.value for p in visible_policies(user.role)}
    if access not in allowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="observation not found",
        )
    return result
