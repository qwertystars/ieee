"""Entities API — list and update spatial entities as GeoJSON.

Entities (zones, roads, shelters, hospitals, etc.) are returned as GeoJSON
FeatureCollection. Updates are scoped by org_id and audited.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_roles
from app.lib.audit import write_audit
from app.lib.time import now_ms
from app.models.entities import (
    Bridge,
    Building,
    CellTower,
    Hazard,
    Hospital,
    PowerSubstation,
    Responder,
    RoadSegment,
    Sensor,
    Shelter,
    Vehicle,
    Zone,
)
from app.models.user import User

logger = logging.getLogger("app.api.routes.entities")

router = APIRouter(prefix="/incidents", tags=["entities"])

_WRITE_ROLES = ("admin", "emergency_manager", "responder_coordinator")

_ENTITY_MAP: dict[str, type] = {
    "zones": Zone,
    "roads": RoadSegment,
    "shelters": Shelter,
    "hospitals": Hospital,
    "hazards": Hazard,
    "buildings": Building,
    "bridges": Bridge,
    "substations": PowerSubstation,
    "cell_towers": CellTower,
    "responders": Responder,
    "vehicles": Vehicle,
    "sensors": Sensor,
}

_PROP_FIELDS = (
    "name", "status", "hazard_type", "severity", "zone_type",
    "building_type", "vehicle_type", "sensor_type", "role",
    "capacity", "occupancy", "priority", "title",
    "assigned_team_id", "required_capability",
)


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    parts = bbox.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=422, detail="bbox must be minx,miny,maxx,maxy",
        )
    try:
        return tuple(float(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        raise HTTPException(
            status_code=422, detail="bbox values must be numeric",
        ) from None


def _to_feature(entity: Any, geojson: str | None) -> dict[str, Any]:
    props: dict[str, Any] = {
        "id": entity.id, "org_id": entity.org_id,
        "incident_id": entity.incident_id,
        "created_at": entity.created_at, "updated_at": entity.updated_at,
    }
    for attr in _PROP_FIELDS:
        if hasattr(entity, attr):
            props[attr] = getattr(entity, attr)
    if getattr(entity, "properties", None) is not None:
        props["properties"] = entity.properties
    geom = json.loads(geojson) if geojson else None
    return {"type": "Feature", "geometry": geom, "properties": props}


@router.get("/{incident_id}/entities")
def list_entities(
    incident_id: str,
    request: Request,
    type_filter: str | None = Query(None, alias="type"),
    bbox: str | None = Query(None, description="minx,miny,maxx,maxy"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List entities as a GeoJSON FeatureCollection.

    Accepts `type` (zones, roads, shelters, etc.) and `bbox` filters.
    If `type` is omitted, returns all entity types.
    """
    org_id = request.state.org_id or ""
    bbox_tuple = _parse_bbox(bbox)
    features: list[dict[str, Any]] = []

    types = [type_filter] if type_filter else list(_ENTITY_MAP.keys())
    for type_name in types:
        model = _ENTITY_MAP.get(type_name)
        if model is None:
            raise HTTPException(
                status_code=422, detail=f"unknown entity type: {type_name}",
            )
        geom_col = getattr(model, "geometry", None)
        if geom_col is None:
            continue
        stmt = select(model, func.ST_AsGeoJSON(geom_col).label("geojson")).where(
            model.org_id == org_id, model.incident_id == incident_id,
        )
        if bbox_tuple is not None:
            minx, miny, maxx, maxy = bbox_tuple
            stmt = stmt.where(func.ST_Intersects(
                geom_col, func.ST_MakeEnvelope(minx, miny, maxx, maxy, 4326),
            ))
        rows = db.execute(stmt).all()
        for entity, geojson in rows:
            features.append(_to_feature(entity, geojson))

    return {"type": "FeatureCollection", "features": features}


@router.patch("/entities/{entity_type}/{entity_id}")
def update_entity(
    entity_type: str,
    entity_id: str,
    request: Request,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*_WRITE_ROLES)),
) -> dict[str, Any]:
    """Update an entity's status/properties. Returns a GeoJSON Feature."""
    org_id = request.state.org_id or ""
    model = _ENTITY_MAP.get(entity_type)
    if model is None:
        raise HTTPException(
            status_code=422, detail=f"unknown entity type: {entity_type}",
        )
    entity = db.execute(
        select(model).where(model.org_id == org_id, model.id == entity_id)
    ).scalars().first()
    if entity is None:
        raise HTTPException(status_code=404, detail="entity not found")

    before = _to_feature(entity, None)["properties"]
    for field in ("status", "name", "severity", "priority", "capacity", "occupancy"):
        if field in payload and hasattr(entity, field):
            setattr(entity, field, payload[field])
    if "properties" in payload:
        entity.properties = payload["properties"]
    entity.updated_at = now_ms()
    db.commit()
    db.refresh(entity)

    geom_col = getattr(model, "geometry", None)
    geojson = None
    if geom_col is not None:
        geojson = db.execute(
            select(func.ST_AsGeoJSON(geom_col)).where(model.id == entity_id)
        ).scalar()

    write_audit(
        db, org_id=org_id, incident_id=entity.incident_id, actor=user.email,
        action=f"entity.{entity_type}.updated", entity=entity_id,
        before=before, after=_to_feature(entity, None)["properties"],
    )
    return _to_feature(entity, geojson)
