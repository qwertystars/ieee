"""Batch observation ingestion — POST /api/observations/batch.

Accepts a GeoJSON FeatureCollection (up to 100 features), creates all
observations in a single DB transaction (``db.add_all`` + one ``db.commit``),
writes a single batch audit entry, and defers confidence-vector /
hypothesis updates to a post-commit ``BackgroundTasks`` job that opens its
own session. The single-obs POST in ``observations.py`` is unchanged.

Kept in a separate file so ``observations.py`` stays under the 250 LOC
ceiling.
"""

from __future__ import annotations

import json
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
from app.api.routes.observations_validation import parse_feature_collection
from app.deps import get_db, require_roles
from app.lib.audit import write_audit
from app.lib.idempotency import (
    IdempotencyConflictError,
    claim_raw_event,
    next_raw_sequence,
)
from app.lib.observability_metrics import record_event_state
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.models.events import RawEvent, RawEventRecord
from app.models.observation import Observation
from app.models.user import User

router = APIRouter(prefix="/observations", tags=["observations"])

_MAX_BATCH = 100
_WRITE_ROLES = (
    "admin",
    "emergency_manager",
    "responder_coordinator",
    "field_responder",
)


def _build_observation(
    feature: dict[str, Any], org_id: str, incident_id: str, ts_now: int
) -> Observation:
    """Construct an Observation from a GeoJSON Feature dict.

    Mirrors the single-obs POST construction in observations.py. Raises
    HTTPException(422) if the feature is malformed.
    """
    if feature.get("type") != "Feature":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="each feature must be a GeoJSON Feature",
        )
    geometry = feature.get("geometry")
    if not geometry:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="geometry is required on every feature",
        )
    props = feature.get("properties") or {}
    if "event_type" not in props or "phenomenon" not in props:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="event_type and phenomenon are required properties",
        )
    if "source_id" not in props:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="source_id is a required property",
        )

    observed_at = props.get("observed_at") or ts_now
    return Observation(
        observation_id=generate_ulid(),
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


@router.post("/batch", status_code=status.HTTP_201_CREATED)
def create_observations_batch(
    request: Request,
    background_tasks: BackgroundTasks,
    body: dict[str, Any],
    incident_id: str = Query(
        ..., description="Incident ID to scope these observations to"
    ),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*_WRITE_ROLES)),
) -> dict[str, Any]:
    """Create up to 100 observations from a GeoJSON FeatureCollection.

    All observations are inserted in a single transaction
    (``db.add_all`` + one ``db.commit``). A single batch audit entry is
    written. Confidence-vector and hypothesis updates are deferred to a
    post-commit ``BackgroundTasks`` job so the response returns immediately.
    """
    org_id = request.state.org_id
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="org_id not resolved from token",
        )

    features = parse_feature_collection(body)
    if len(features) > _MAX_BATCH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"batch exceeds maximum of {_MAX_BATCH} features",
        )

    ts_now = now_ms()
    observations: list[Observation] = []
    results: list[dict[str, str]] = []
    for index, feature in enumerate(features):
        observation = _build_observation(feature, org_id, incident_id, ts_now)
        props = feature.get("properties") or {}
        source_id = str(props["source_id"])
        external_id = str(
            props.get("external_id")
            or (f"{idempotency_key}:{index}" if idempotency_key else observation.observation_id)
        )
        raw_event = RawEvent(
            event_id=generate_ulid(),
            org_id=org_id,
            incident_id=incident_id,
            source_id=source_id,
            external_id=external_id,
            event_type=str(props["event_type"]),
            source_time_ms=observation.observed_at,
            receipt_time_ms=ts_now,
            sequence=next_raw_sequence(db, org_id, source_id),
            payload=feature,
        )
        try:
            is_new = claim_raw_event(
                db, raw_event, feature, idempotency_key=(
                    f"{idempotency_key}:{index}" if idempotency_key else None
                )
            )
        except IdempotencyConflictError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="idempotency key conflicts with a different payload",
            ) from None
        if not is_new:
            existing_raw = db.execute(
                select(RawEventRecord).where(
                    RawEventRecord.org_id == org_id,
                    RawEventRecord.source_id == source_id,
                    RawEventRecord.external_id == external_id,
                )
            ).scalar_one_or_none()
            existing_id = None
            if existing_raw is not None:
                existing_id = db.execute(
                    select(Observation.observation_id).where(
                        Observation.raw_event_id == existing_raw.id,
                        Observation.org_id == org_id,
                    )
                ).scalar_one_or_none()
            results.append({"id": existing_id or observation.observation_id, "status": "duplicate"})
            continue
        observation.raw_event_id = raw_event.event_id
        observation.source_time_ms = raw_event.source_time_ms
        observation.receipt_time_ms = raw_event.receipt_time_ms
        observation.sequence = raw_event.sequence
        observation.payload_hash = raw_event.canonical_hash()
        observation.raw_data_hash = raw_event.canonical_hash()
        observation.visibility = raw_event.visibility.value
        observation.review_status = raw_event.review_status.value
        observation.schema_version = raw_event.schema_version
        observations.append(observation)
        results.append({"id": observation.observation_id, "status": "created"})

    db.add_all(observations)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="batch could not be created (constraint violation)",
        ) from None
    record_event_state("accepted", "api", "observations.raw")

    observation_ids = [obs.observation_id for obs in observations]

    write_audit(
        db,
        org_id=org_id,
        incident_id=incident_id,
        actor=user.email,
        action="observation.batch_created",
        entity=incident_id,
        after={
            "count": len(observation_ids),
            "observation_ids": observation_ids,
        },
    )

    for observation_id in observation_ids:
        background_tasks.add_task(
            run_single_post_commit_fusion,
            observation_id,
            org_id,
            incident_id,
            user.email,
        )

    return {
        "observations": results,
        "count": len(results),
    }
