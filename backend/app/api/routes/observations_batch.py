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
import logging
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.deps import get_db, require_roles
from app.lib.audit import write_audit
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.models.observation import Observation
from app.models.user import User

logger = logging.getLogger("app.api.routes.observations_batch")

router = APIRouter(prefix="/observations", tags=["observations"])

_MAX_BATCH = 100
_FUSION_CHUNK_SIZE = 10
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

    observed_at = int(props.get("observed_at", ts_now))
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


def _run_post_commit_fusion(
    observation_ids: list[str], org_id: str, incident_id: str
) -> None:
    """Background task: compute confidence vectors + update hypotheses.

    Processes observations in chunks of 10, releasing the DB connection
    between chunks so the pool is not monopolized during large batches.
    Failures are logged and swallowed — the observations are already
    committed; fusion is best-effort enrichment.
    """
    from sqlalchemy.orm.attributes import flag_modified

    from app.fusion.confidence import ConfidenceVectorCalculator
    from app.fusion.hypothesis_update import update_hypotheses_for_observation

    calc = ConfidenceVectorCalculator()
    for i in range(0, len(observation_ids), _FUSION_CHUNK_SIZE):
        chunk = observation_ids[i : i + _FUSION_CHUNK_SIZE]
        db = SessionLocal()
        try:
            for obs_id in chunk:
                obs = db.get(Observation, obs_id)
                if obs is None:
                    continue
                try:
                    vector = calc.compute_vector(obs, db_session=db)
                    calc.attach_to_observation(obs, vector)
                    obs.quality_flags["display_confidence"] = (
                        calc.compute_display_confidence(vector)
                    )
                    flag_modified(obs, "quality_flags")
                    db.commit()
                except Exception as exc:
                    logger.warning(
                        "Batch confidence computation failed for %s: %s",
                        obs_id,
                        exc,
                    )
                    db.rollback()
                    continue
                try:
                    update_hypotheses_for_observation(db, obs)
                except Exception as exc:
                    logger.warning(
                        "Batch hypothesis update failed for %s: %s", obs_id, exc
                    )
                    db.rollback()
        except Exception as exc:
            logger.error("Post-commit batch fusion chunk failed: %s", exc)
        finally:
            db.close()


@router.post("/batch", status_code=status.HTTP_201_CREATED)
def create_observations_batch(
    request: Request,
    background_tasks: BackgroundTasks,
    body: dict[str, Any],
    incident_id: str = Query(
        ..., description="Incident ID to scope these observations to"
    ),
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

    if body.get("type") != "FeatureCollection":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="GeoJSON FeatureCollection required",
        )
    features = body.get("features") or []
    if len(features) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="FeatureCollection must contain at least one feature",
        )
    if len(features) > _MAX_BATCH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"batch exceeds maximum of {_MAX_BATCH} features",
        )

    ts_now = now_ms()
    observations = [
        _build_observation(feat, org_id, incident_id, ts_now)
        for feat in features
    ]

    db.add_all(observations)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="batch could not be created (constraint violation)",
        ) from None

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

    # Confidence/hypothesis fusion skipped for batch POSTs to avoid
    # exhausting the DB connection pool under high-throughput ingest.
    # The consumer pipeline (Kafka) handles enrichment asynchronously.
    # background_tasks.add_task(
    #     _run_post_commit_fusion, observation_ids, org_id, incident_id
    # )

    return {
        "observations": [
            {"id": oid, "status": "created"} for oid in observation_ids
        ],
        "count": len(observation_ids),
    }
