"""STAC adapter — index satellite imagery from SpatioTemporal Asset Catalogs.

STAC API spec: https://github.com/radiantearth/stac-api-spec

Supports both remote STAC APIs (HTTP) and local catalogs (file path to a
GeoJSON FeatureCollection). Does NOT download imagery — only indexes metadata.
Actual download is deferred to T18 (imagery fetch).

Each indexed item lands as corroboration_state=uncorroborated (draft) until
human or fusion confirmation. Imagery asset URLs are preserved in
quality_flags.assets for later retrieval.
"""

import hashlib
import json
import logging
import os
from typing import Any

import httpx
from shapely.geometry import shape

from app.lib.time import from_iso, now_ms, to_iso
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
_MAX_PAGES = 100  # Safety guard against infinite pagination loops.


class STACClient:
    """Async client for a STAC API or local STAC catalog.

    catalog_url may be:
      - An HTTP/HTTPS URL to a STAC API root
      - A file path to a local GeoJSON FeatureCollection (offline/cached)
    """

    def __init__(self, catalog_url: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.catalog_url = catalog_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._is_file = os.path.isfile(catalog_url)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "STACClient":
        await self._get_client()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def search_items(
        self,
        bbox: tuple[float, float, float, float],
        datetime_range: tuple[int, int],
        collections: list[str] | None = None,
        max_cloud_cover: float | None = None,
    ) -> list[dict[str, Any]]:
        """Search STAC items by bbox, time range, collections, cloud cover.

        For local file catalogs, loads the FeatureCollection and filters
        in-memory (no network required). For remote APIs, uses GET /search
        and applies cloud_cover filtering client-side for portability.
        """
        if self._is_file:
            return self._search_local(
                bbox, datetime_range, collections, max_cloud_cover
            )
        return await self._search_remote(
            bbox, datetime_range, collections, max_cloud_cover
        )

    def _search_local(
        self,
        bbox: tuple[float, float, float, float],
        datetime_range: tuple[int, int],
        collections: list[str] | None,
        max_cloud_cover: float | None,
    ) -> list[dict[str, Any]]:
        """Filter a local GeoJSON FeatureCollection in-memory."""
        with open(self.catalog_url, encoding="utf-8") as f:
            catalog = json.load(f)
        items = catalog.get("features", catalog.get("items", []))
        return _filter_items(items, bbox, datetime_range, collections, max_cloud_cover)

    async def _search_remote(
        self,
        bbox: tuple[float, float, float, float],
        datetime_range: tuple[int, int],
        collections: list[str] | None,
        max_cloud_cover: float | None,
    ) -> list[dict[str, Any]]:
        """GET /search from a STAC API, following pagination links."""
        client = await self._get_client()
        params: dict[str, Any] = {
            "bbox": ",".join(str(c) for c in bbox),
            "datetime": f"{to_iso(datetime_range[0])}/{to_iso(datetime_range[1])}",
            "limit": 100,
        }
        if collections:
            params["collections"] = ",".join(collections)

        items: list[dict[str, Any]] = []
        url: str | None = f"{self.catalog_url}/search"
        visited: set[str] = set()
        pages = 0
        first = True
        while url and url not in visited and pages < _MAX_PAGES:
            visited.add(url)
            try:
                # First page: pass query params. Subsequent pages: use the
                # next-link URL as-is (it carries its own query params).
                if first:
                    resp = await client.get(url, params=params)
                    first = False
                else:
                    resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                logger.warning("STAC search error for %s: %s", url, exc)
                break
            items.extend(data.get("features", []))
            url = _next_link(data.get("links", []))
            pages += 1

        if max_cloud_cover is not None:
            items = _filter_items(
                items, bbox, datetime_range, collections, max_cloud_cover
            )
        return items


def _next_link(links: list[dict]) -> str | None:
    """Extract the 'next' pagination link from a STAC response."""
    for link in links or []:
        if link.get("rel") == "next" and link.get("href"):
            return link["href"]
    return None


def _filter_items(
    items: list[dict],
    bbox: tuple[float, float, float, float],
    datetime_range: tuple[int, int],
    collections: list[str] | None,
    max_cloud_cover: float | None,
) -> list[dict]:
    """Apply client-side filters to a list of STAC items."""
    minx, miny, maxx, maxy = bbox
    start_ms, end_ms = datetime_range
    result: list[dict] = []
    for item in items:
        if collections:
            coll = item.get("collection")
            if coll not in collections:
                continue
        props = item.get("properties", {})
        dt = props.get("datetime")
        if dt:
            try:
                obs_ms = from_iso(dt)
                if obs_ms < start_ms or obs_ms > end_ms:
                    continue
            except ValueError:
                pass
        if max_cloud_cover is not None:
            cc = props.get("eo:cloud_cover")
            if cc is not None and float(cc) > max_cloud_cover:
                continue
        ib = item.get("bbox")
        if ib and len(ib) == 4:
            if ib[0] > maxx or ib[2] < minx or ib[1] > maxy or ib[3] < miny:
                continue
        result.append(item)
    return result


def _geometry_to_wkt(geometry: dict[str, Any]) -> str:
    """Convert a GeoJSON geometry dict to WKT (lon/lat ordering)."""
    return shape(geometry).wkt


def index_item(
    stac_item: dict[str, Any], org_id: str, incident_id: str
) -> dict[str, Any]:
    """Extract metadata from a STAC item into an observation dict.

    Returns a dict with Observation-compatible fields plus stac-specific
    metadata. Imagery asset URLs are stored in quality_flags.assets for
    later download (T18).
    """
    item_id = stac_item.get("id", generate_ulid())
    collection = stac_item.get("collection", "unknown")
    props = stac_item.get("properties", {})
    geometry = stac_item.get("geometry") or {
        "type": "Point",
        "coordinates": [0, 0],
    }
    geometry_wkt = _geometry_to_wkt(geometry)

    dt = props.get("datetime")
    observed_at = from_iso(dt) if dt else now_ms()

    cloud_cover = props.get("eo:cloud_cover")
    platform = props.get("platform")
    instruments = props.get("instruments", [])
    constellation = props.get("constellation")
    assets = stac_item.get("assets", {})

    asset_refs = {
        key: {"href": a.get("href"), "type": a.get("type")}
        for key, a in assets.items()
    }

    source_id = f"stac:{collection}:{item_id}"
    raw = json.dumps(stac_item, sort_keys=True, default=str, separators=(",", ":"))
    raw_hash = "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    return {
        "observation_id": generate_ulid(),
        "event_type": "satellite_imagery",
        "phenomenon": constellation or collection,
        "value": float(cloud_cover) if cloud_cover is not None else None,
        "unit": "%" if cloud_cover is not None else None,
        "geometry_wkt": geometry_wkt,
        "geometry_uncertainty": 0.0,
        "observed_at": observed_at,
        "valid_from": observed_at,
        "valid_until": None,
        "received_at": now_ms(),
        "source_id": source_id,
        "source_type": SourceType.satellite,
        "collection_method": "stac_api",
        "source_reliability": 0.9,
        "freshness": 1.0,
        "corroboration_state": CorroborationState.uncorroborated,
        "model_uncertainty": None,
        "quality_flags": {
            "cloud_cover": cloud_cover,
            "platform": platform,
            "instruments": instruments,
            "constellation": constellation,
            "assets": asset_refs,
            "bbox": stac_item.get("bbox"),
        },
        "access_policy": AccessPolicy.internal,
        "provenance_chain": {
            "adapter": "stac",
            "collection": collection,
            "item_id": item_id,
            "stac_version": stac_item.get("stac_version"),
        },
        "raw_data_hash": raw_hash,
        "model_version": None,
        "supersedes": None,
        "duplicate_group": None,
        "org_id": org_id,
        "incident_id": incident_id,
    }


__all__ = ["STACClient", "index_item"]
