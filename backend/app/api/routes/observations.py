"""Observations API — POST/GET/GET-by-id, all GeoJSON Feature/FeatureCollection.

org_id is always taken from `request.state.org_id` (set by OrgContextMiddleware
from the signed JWT), never from the request body or query params.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.api.routes.observations_queries import (
    apply_filters,
    fetch_feature,
    to_feature,
    visible_policies,
)
from app.deps import get_current_user, get_db, require_roles
from app.fusion.confidence import ConfidenceVectorCalculator
from app.fusion.hypothesis_update import update_hypotheses_for_observation
from app.lib.audit import write_audit
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.models.observation import Observation
from app.models.user import User

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
    feature: dict[str, Any],
    incident_id: str = Query(..., description="Incident ID to scope this observation to"),
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

    if feature.get("type") != "Feature":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="GeoJSON Feature required",
        )
    geometry = feature.get("geometry")
    if not geometry:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="geometry is required",
        )
    props = feature.get("properties") or {}

    observation_id = generate_ulid()
    ts_now = now_ms()
    observed_at = int(props.get("observed_at", ts_now))

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
        valid_from=int(props.get("valid_from", observed_at)),
        valid_until=props.get("valid_until"),
        received_at=ts_now,
        source_id=props["source_id"],
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

    try:
        calc = ConfidenceVectorCalculator()
        vector = calc.compute_vector(obs, db_session=db)
        calc.attach_to_observation(obs, vector)
        obs.quality_flags["display_confidence"] = (
            calc.compute_display_confidence(vector)
        )
        flag_modified(obs, "quality_flags")
        db.commit()
        db.refresh(obs)
    except Exception as exc:
        logger.warning(
            "Confidence vector computation failed for %s: %s",
            observation_id,
            exc,
        )
        db.rollback()

    try:
        update_hypotheses_for_observation(db, obs)
    except Exception as exc:
        logger.warning(
            "Hypothesis update failed for %s: %s", observation_id, exc
        )
        db.rollback()

    write_audit(
        db,
        org_id=org_id,
        incident_id=incident_id,
        actor=user.email,
        action="observation.created",
        entity=observation_id,
        after={
            "event_type": obs.event_type,
            "phenomenon": obs.phenomenon,
            "observed_at": obs.observed_at,
        },
    )

    result = fetch_feature(db, observation_id, org_id)
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
