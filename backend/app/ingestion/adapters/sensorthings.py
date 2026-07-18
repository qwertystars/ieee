"""OGC SensorThings API adapter — pull sensor observations into Observations.

SensorThings API v1.0 spec: https://docs.ogc.org/is/15-078r6/15-078r6.html

Each Observation is expanded with its Datastream (for phenomenon name and unit)
and FeatureOfInterest (for geometry) via $expand. Observations land as
corroboration_state=uncorroborated (draft) until human/fusion confirmation.
"""

import hashlib
import json
import logging
from typing import Any

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.lib.time import from_iso, now_ms, to_iso
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.models.observation import Observation

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0
_MAX_PAGES = 100  # Safety guard against infinite pagination loops.


class SensorThingsClient:
    """Async client for OGC SensorThings API v1.0."""

    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "SensorThingsClient":
        await self._get_client()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def _fetch_json(self, url: str) -> dict[str, Any] | None:
        """GET a URL and return parsed JSON. Returns None on 404/timeout."""
        client = await self._get_client()
        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                logger.warning("SensorThings 404: %s", url)
                return None
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            logger.warning("SensorThings timeout: %s", url)
            return None
        except httpx.HTTPError as exc:
            logger.warning("SensorThings HTTP error for %s: %s", url, exc)
            return None

    async def get_datastream(self, datastream_id: str) -> dict[str, Any] | None:
        """Fetch Datastream metadata (name, unitOfMeasurement, etc.)."""
        url = f"{self.base_url}/v1.0/Datastreams({datastream_id})"
        return await self._fetch_json(url)

    async def pull_observations(
        self,
        datastream_id: str,
        time_range: tuple[int, int] | None = None,
    ) -> list[dict[str, Any]]:
        """Pull observations for a datastream, following @iot.nextLink pagination.

        Each observation is expanded with its Datastream and FeatureOfInterest
        via $expand. If time_range (start_ms, end_ms) is provided, filters via
        $filter on phenomenonTime.
        """
        url = (
            f"{self.base_url}/v1.0/Datastreams({datastream_id})/Observations"
            "?$expand=Datastream,FeatureOfInterest"
        )
        if time_range is not None:
            start_iso = to_iso(time_range[0])
            end_iso = to_iso(time_range[1])
            url += (
                f"&$filter=phenomenonTime ge {start_iso}"
                f" and phenomenonTime le {end_iso}"
            )

        observations: list[dict[str, Any]] = []
        next_url: str | None = url
        pages = 0
        while next_url and pages < _MAX_PAGES:
            data = await self._fetch_json(next_url)
            if data is None:
                break
            observations.extend(data.get("value", []))
            next_url = data.get("@iot.nextLink")
            pages += 1
        return observations


def _is_numeric(val: Any) -> bool:
    try:
        float(val)
        return True
    except (TypeError, ValueError):
        return False


def _feature_to_wkt(feature: dict[str, Any]) -> WKTElement:
    """Convert a GeoJSON feature dict to a WKTElement for PostGIS."""
    geom_type = feature.get("type")
    coords = feature.get("coordinates")
    if geom_type == "Point" and coords and len(coords) >= 2:
        return WKTElement(f"POINT({coords[0]} {coords[1]})", srid=4326)
    if geom_type == "Polygon" and coords:
        ring = coords[0]
        pts = ", ".join(f"{x} {y}" for x, y in ring)
        return WKTElement(f"POLYGON(({pts}))", srid=4326)
    return WKTElement("POINT(0 0)", srid=4326)


def map_to_observation(st_obs: dict[str, Any], org_id: str, incident_id: str) -> Observation:
    """Map a SensorThings observation dict to the Observation model.

    Expects st_obs to contain inlined Datastream and FeatureOfInterest
    (via $expand). Falls back gracefully when fields are missing.
    """
    datastream = st_obs.get("Datastream") or {}
    foi = st_obs.get("FeatureOfInterest") or {}
    feature = foi.get("feature") or {}

    phenomenon = datastream.get("name", "unknown")
    unit_obj = datastream.get("unitOfMeasurement") or {}
    unit = unit_obj.get("symbol") or unit_obj.get("name")

    geometry = _feature_to_wkt(feature)

    phen_time = st_obs.get("phenomenonTime")
    observed_at = from_iso(phen_time) if phen_time else now_ms()
    received_at = now_ms()

    result = st_obs.get("result")
    value = float(result) if result is not None and _is_numeric(result) else None

    source_id = f"sensorthings:{st_obs.get('@iot.id', generate_ulid())}"

    raw = json.dumps(st_obs, sort_keys=True, default=str, separators=(",", ":"))
    raw_hash = "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    return Observation(
        observation_id=generate_ulid(),
        event_type="sensor_reading",
        phenomenon=phenomenon,
        value=value,
        unit=unit,
        geometry=geometry,
        geometry_uncertainty=0.0,
        observed_at=observed_at,
        valid_from=observed_at,
        valid_until=None,
        received_at=received_at,
        source_id=source_id,
        source_type=SourceType.sensor,
        collection_method="sensorthings_api",
        source_reliability=0.8,
        freshness=1.0,
        corroboration_state=CorroborationState.uncorroborated,
        model_uncertainty=None,
        quality_flags={"sensorthings": True},
        access_policy=AccessPolicy.internal,
        provenance_chain={
            "adapter": "sensorthings",
            "datastream_id": str(datastream.get("@iot.id", "")),
            "self_link": st_obs.get("@iot.selfLink", ""),
        },
        raw_data_hash=raw_hash,
        model_version=None,
        supersedes=None,
        duplicate_group=None,
        org_id=org_id,
        incident_id=incident_id,
    )


async def sync_datastream(
    db: Session,
    client: SensorThingsClient,
    datastream_id: str,
    org_id: str,
    incident_id: str,
) -> int:
    """Pull observations for a datastream and insert into the DB.

    Idempotent: skips observations with a (source_id, raw_data_hash) pair that
    already exists for this org. Returns the number of new observations inserted.
    """
    observations = await client.pull_observations(datastream_id)
    if not observations:
        logger.info("No observations for datastream %s", datastream_id)
        return 0

    count = 0
    for st_obs in observations:
        obs = map_to_observation(st_obs, org_id, incident_id)
        existing = db.execute(
            select(Observation.observation_id).where(
                Observation.source_id == obs.source_id,
                Observation.raw_data_hash == obs.raw_data_hash,
                Observation.org_id == org_id,
            )
        ).first()
        if existing:
            continue
        db.add(obs)
        count += 1

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info(
        "Inserted %d/%d observations for datastream %s",
        count, len(observations), datastream_id,
    )
    return count


__all__ = ["SensorThingsClient", "map_to_observation", "sync_datastream"]
