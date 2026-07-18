"""OGC API Features client — pull GeoJSON features and upsert into entity tables.

Supports incremental sync via datetime filter and conflict detection (won't
overwrite user-edited rows). Uses httpx for async HTTP and shapely for
GeoJSON -> WKT conversion.

External source ID and a content hash are stored in the entity's `properties`
JSONB column under `_external_id` / `_source_hash` for idempotent upserts.
A `_user_edited` flag, when True, prevents the upsert from overwriting the row.
"""

import hashlib
import json
from typing import Any

import httpx
from geoalchemy2.elements import WKTElement
from shapely.geometry import shape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.lib.time import now_ms, to_iso
from app.lib.ulid import generate_ulid
from app.models.entities import (
    Bridge,
    Building,
    CellTower,
    Hospital,
    PowerSubstation,
    RoadSegment,
    Shelter,
    Zone,
)

# entity_type string -> ORM class
ENTITY_MAP: dict[str, type] = {
    "road_segment": RoadSegment,
    "shelter": Shelter,
    "hospital": Hospital,
    "zone": Zone,
    "building": Building,
    "bridge": Bridge,
    "power_substation": PowerSubstation,
    "cell_tower": CellTower,
}

# Whitelisted property fields copied from GeoJSON properties to model columns.
PROP_FIELDS: dict[str, list[str]] = {
    "road_segment": ["name", "status"],
    "shelter": ["name", "status", "capacity", "occupancy"],
    "hospital": ["name", "status", "capacity"],
    "zone": ["name", "zone_type"],
    "building": ["name", "building_type"],
    "bridge": ["name", "status"],
    "power_substation": ["name", "status"],
    "cell_tower": ["name", "status"],
}

_INT_FIELDS = frozenset({"capacity", "occupancy"})


def _geojson_to_wkt(geometry: dict | None) -> WKTElement | None:
    """Convert a GeoJSON geometry dict to a WKTElement (srid=4326)."""
    if geometry is None:
        return None
    return WKTElement(shape(geometry).wkt, srid=4326)


def _source_hash(feature: dict) -> str:
    """Stable hash of geometry + properties for change detection."""
    payload = json.dumps(
        {"g": feature.get("geometry"), "p": feature.get("properties", {})},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _external_id(feature: dict) -> str:
    """Extract a stable external ID from a GeoJSON Feature."""
    fid = feature.get("id")
    if fid is not None:
        return str(fid)
    props = feature.get("properties", {}) or {}
    return str(props.get("id") or generate_ulid())


class OGCFeaturesClient:
    """Async client for an OGC API Features endpoint.

    Usage:
        async with OGCFeaturesClient("https://example.org") as client:
            features = await client.pull_features("roads", bbox=(-74,40,-73,41))
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> "OGCFeaturesClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.aclose()

    async def close(self) -> None:
        await self._client.aclose()

    async def _fetch_page(self, url: str, params: dict) -> dict:
        """Fetch a single page of features; raise on HTTP error."""
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    async def pull_features(
        self,
        collection_id: str,
        bbox: tuple[float, float, float, float] | None = None,
        datetime_range: tuple[int, int] | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Pull all features for a collection, following pagination links.

        Args:
            collection_id: OGC collection ID.
            bbox: (minx, miny, maxx, maxy) in WGS84 degrees.
            datetime_range: (start_ms, end_ms) epoch ms; converted to ISO interval.
            limit: page size.

        Returns:
            List of GeoJSON Feature dicts.
        """
        url = f"{self.base_url}/collections/{collection_id}/items"
        params: dict[str, Any] = {"limit": limit}
        if bbox is not None:
            params["bbox"] = ",".join(str(c) for c in bbox)
        if datetime_range is not None:
            start_ms, end_ms = datetime_range
            params["datetime"] = f"{to_iso(start_ms)}/{to_iso(end_ms)}"

        features: list[dict] = []
        visited: set[str] = set()
        first = True
        while url:
            if url in visited:
                break
            visited.add(url)
            data = await self._fetch_page(url, params if first else {})
            first = False
            features.extend(data.get("features", []))
            # Follow 'next' link per OGC API Features spec.
            url = ""
            for link in data.get("links", []):
                if link.get("rel") == "next" and link.get("href"):
                    url = link["href"]
                    break
        return features

    def map_to_entity(
        self,
        feature: dict,
        entity_type: str,
        org_id: str,
        incident_id: str,
    ) -> object:
        """Map a GeoJSON Feature to an ORM entity instance (not yet persisted)."""
        cls = ENTITY_MAP.get(entity_type)
        if cls is None:
            raise ValueError(f"unsupported entity_type: {entity_type}")

        props = dict(feature.get("properties", {}) or {})
        ext_id = _external_id(feature)
        src_hash = _source_hash(feature)

        cols: dict[str, Any] = {
            "id": generate_ulid(),
            "org_id": org_id,
            "incident_id": incident_id,
            "created_at": now_ms(),
            "updated_at": now_ms(),
            "geometry": _geojson_to_wkt(feature.get("geometry")),
        }
        for field in PROP_FIELDS.get(entity_type, []):
            if field in props:
                val = props[field]
                if field in _INT_FIELDS and val is not None:
                    try:
                        val = int(val)
                    except (TypeError, ValueError):
                        val = None
                cols[field] = val

        # Stash source provenance for upsert/conflict detection.
        props["_external_id"] = ext_id
        props["_source_hash"] = src_hash
        props["_source"] = "ogc"
        cols["properties"] = props
        return cls(**cols)


def _find_existing(
    db: Session, cls: type, org_id: str, external_id: str
) -> object | None:
    """Find an existing entity row by (org_id, properties._external_id)."""
    rows = db.execute(
        select(cls).where(
            cls.org_id == org_id,
            cls.properties["_external_id"].astext == external_id,
        )
    ).scalars().all()
    return rows[0] if rows else None


def upsert_feature(
    db: Session,
    client: OGCFeaturesClient,
    feature: dict,
    entity_type: str,
    org_id: str,
    incident_id: str,
) -> tuple[object, str]:
    """Insert or update a single feature. Returns (row, action).

    action is one of 'inserted', 'updated', 'skipped'.
    Skips if the row was user-edited (_user_edited flag) or unchanged.
    """
    cls = ENTITY_MAP[entity_type]
    ext_id = _external_id(feature)
    existing = _find_existing(db, cls, org_id, ext_id)
    new_hash = _source_hash(feature)

    if existing is not None:
        existing_props = dict(existing.properties or {})
        # Don't overwrite user-edited rows.
        if existing_props.get("_user_edited"):
            return existing, "skipped"
        # Skip if unchanged (same source hash).
        if existing_props.get("_source_hash") == new_hash:
            return existing, "skipped"
        # Update in place: merge new source properties over existing.
        entity = client.map_to_entity(feature, entity_type, org_id, incident_id)
        existing.geometry = entity.geometry
        existing.updated_at = now_ms()
        for field in PROP_FIELDS.get(entity_type, []):
            if hasattr(entity, field):
                setattr(existing, field, getattr(entity, field))
        merged = dict(existing_props)
        merged.update(entity.properties or {})
        merged["_source_hash"] = new_hash
        merged["_synced_at"] = now_ms()
        existing.properties = merged
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing, "updated"

    entity = client.map_to_entity(feature, entity_type, org_id, incident_id)
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity, "inserted"


async def sync_collection(
    db: Session,
    client: OGCFeaturesClient,
    collection_id: str,
    entity_type: str,
    org_id: str,
    incident_id: str,
    bbox: tuple[float, float, float, float] | None = None,
    datetime_range: tuple[int, int] | None = None,
) -> int:
    """Pull features from an OGC collection and upsert into the DB.

    Returns the number of features inserted or updated.
    """
    features = await client.pull_features(
        collection_id, bbox=bbox, datetime_range=datetime_range
    )
    count = 0
    for feat in features:
        _, action = upsert_feature(
            db, client, feat, entity_type, org_id, incident_id
        )
        if action in ("inserted", "updated"):
            count += 1
    return count


__all__ = [
    "OGCFeaturesClient",
    "sync_collection",
    "upsert_feature",
    "ENTITY_MAP",
]
