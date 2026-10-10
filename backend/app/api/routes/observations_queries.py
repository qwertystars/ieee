"""Filter logic and GeoJSON serialization for observation queries.

Kept separate from `observations.py` so the routes file stays under 250 LOC.
All geometry leaves the DB as GeoJSON via `ST_AsGeoJSON` — never WKT.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.enums import AccessPolicy
from app.models.observation import Observation

# Access policies visible to each role. Operational roles see sensitive data;
# viewer is restricted to public only. Unknown roles get public-only.
_ROLE_VISIBILITY: dict[str, tuple[AccessPolicy, ...]] = {
    "admin": (AccessPolicy.public, AccessPolicy.internal, AccessPolicy.sensitive),
    "emergency_manager": (
        AccessPolicy.public,
        AccessPolicy.internal,
        AccessPolicy.sensitive,
    ),
    "responder_coordinator": (
        AccessPolicy.public,
        AccessPolicy.internal,
        AccessPolicy.sensitive,
    ),
    "field_responder": (AccessPolicy.public, AccessPolicy.internal),
    "shelter_manager": (AccessPolicy.public, AccessPolicy.internal),
    "viewer": (AccessPolicy.public,),
}


def visible_policies(role: str) -> tuple[AccessPolicy, ...]:
    """Return the access policies this role is allowed to see."""
    return _ROLE_VISIBILITY.get(role, (AccessPolicy.public,))


def apply_filters(
    stmt: Select,
    *,
    org_id: str,
    incident_id: str | None,
    source_id: str | None,
    phenomenon: str | None,
    observed_start: int | None,
    observed_end: int | None,
    recent_ms: int | None,
    bbox: tuple[float, float, float, float] | None,
    confidence_s: float | None,
    policies: tuple[AccessPolicy, ...],
) -> Select:
    """Apply all list filters to the given select statement."""
    stmt = stmt.where(Observation.org_id == org_id)
    if incident_id is not None:
        stmt = stmt.where(Observation.incident_id == incident_id)
    if source_id is not None:
        stmt = stmt.where(Observation.source_id == source_id)
    if phenomenon is not None:
        stmt = stmt.where(Observation.phenomenon == phenomenon)
    if observed_start is not None:
        stmt = stmt.where(Observation.observed_at >= observed_start)
    if observed_end is not None:
        stmt = stmt.where(Observation.observed_at <= observed_end)
    if recent_ms is not None:
        from app.lib.time import now_ms

        stmt = stmt.where(Observation.observed_at >= now_ms() - recent_ms)
    if bbox is not None:
        envelope = func.ST_MakeEnvelope(bbox[0], bbox[1], bbox[2], bbox[3], 4326)
        stmt = stmt.where(func.ST_Intersects(Observation.geometry, envelope))
    if confidence_s is not None:
        stmt = stmt.where(
            Observation.quality_flags["confidence_vector"]["s"].as_float()
            >= confidence_s
        )
    if policies:
        stmt = stmt.where(Observation.access_policy.in_(policies))
    return stmt


def fetch_feature(db: Session, observation_id: str, org_id: str) -> dict | None:
    """Fetch a single observation as a GeoJSON Feature dict, or None if missing."""
    row = db.execute(
        select(Observation, func.ST_AsGeoJSON(Observation.geometry).label("geojson"))
        .where(Observation.observation_id == observation_id)
        .where(Observation.org_id == org_id)
    ).first()
    if row is None:
        return None
    obs, geojson_str = row
    geometry = json.loads(geojson_str) if geojson_str else None
    return to_feature(obs, geometry)


def to_feature(obs: Observation, geometry: dict | None) -> dict[str, Any]:
    """Convert an Observation ORM instance to a GeoJSON Feature dict."""
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "observation_id": obs.observation_id,
            "event_type": obs.event_type,
            "phenomenon": obs.phenomenon,
            "value": obs.value,
            "unit": obs.unit,
            "geometry_uncertainty": obs.geometry_uncertainty,
            "observed_at": obs.observed_at,
            "valid_from": obs.valid_from,
            "valid_until": obs.valid_until,
            "received_at": obs.received_at,
            "source_id": obs.source_id,
            "source_type": obs.source_type.value if obs.source_type else None,
            "collection_method": obs.collection_method,
            "source_reliability": obs.source_reliability,
            "freshness": obs.freshness,
            "corroboration_state": (
                obs.corroboration_state.value if obs.corroboration_state else None
            ),
            "model_uncertainty": obs.model_uncertainty,
            "quality_flags": obs.quality_flags,
            "access_policy": (
                obs.access_policy.value if obs.access_policy else None
            ),
            "provenance_chain": obs.provenance_chain,
            "raw_data_hash": obs.raw_data_hash,
            "model_version": obs.model_version,
            "supersedes": obs.supersedes,
            "duplicate_group": obs.duplicate_group,
            "org_id": obs.org_id,
            "incident_id": obs.incident_id,
        },
    }


__all__ = ["apply_filters", "fetch_feature", "to_feature", "visible_policies"]
