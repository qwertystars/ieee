"""HDX HAPI adapter — pull humanitarian indicators from HDX Humanitarian API.

HDX HAPI spec: https://github.com/OCHA-DAP/hapi-api

Note: OCHA retired HDX HXL services on January 31, 2026. This adapter uses
HAPI (the replacement), NOT the deprecated HXL endpoints.

Each indicator lands as corroboration_state=uncorroborated (draft) until
human or fusion confirmation. Indicators are country-level; geometry is a
country centroid from a small lookup table.
"""

import hashlib
import json
import logging
from typing import Any

import httpx

from app.lib.time import from_iso, now_ms
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
_MAX_PAGES = 100  # Safety guard against infinite pagination loops.

# Minimal ISO3 country code -> (lon, lat) centroid lookup for geometry.
# Extend as needed for additional countries.
_COUNTRY_CENTROIDS: dict[str, tuple[float, float]] = {
    "COL": (-74.0, 4.6),
    "AFG": (67.0, 33.0),
    "SYR": (38.0, 35.0),
    "YEM": (48.0, 15.5),
    "ETH": (40.0, 9.0),
    "SDN": (30.0, 15.0),
    "SSD": (31.0, 7.0),
    "MMR": (96.0, 21.0),
    "UKR": (32.0, 49.0),
    "PHL": (122.0, 13.0),
    "BGD": (90.0, 24.0),
    "PAK": (69.0, 30.0),
    "IND": (78.0, 21.0),
    "USA": (-98.0, 39.0),
}


class HDXClient:
    """Async client for HDX HAPI (Humanitarian API).

    base_url should point to the HAPI root, e.g.
    https://hapi.humdata.org/api/v1
    """

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

    async def __aenter__(self) -> "HDXClient":
        await self._get_client()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def pull_indicators(
        self,
        country: str,
        indicator_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Pull humanitarian indicators for a country from HDX HAPI.

        Follows next_url pagination. If indicator_ids is provided, filters
        client-side by #indicator+code.

        Returns a list of HAPI indicator dicts (HXL-tagged keys).
        """
        client = await self._get_client()
        url: str | None = (
            f"{self.base_url}/population?country_code={country.upper()}"
        )
        visited: set[str] = set()
        results: list[dict[str, Any]] = []
        pages = 0
        while url and url not in visited and pages < _MAX_PAGES:
            visited.add(url)
            try:
                resp = await client.get(url)
                if resp.status_code == 404:
                    logger.warning("HDX HAPI 404: %s", url)
                    break
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                logger.warning("HDX HAPI error for %s: %s", url, exc)
                break
            page_items = data.get("data", [])
            if indicator_ids:
                page_items = [
                    d
                    for d in page_items
                    if d.get("#indicator+code") in indicator_ids
                ]
            results.extend(page_items)
            url = data.get("next_url")
            pages += 1
        return results


def _country_centroid(country_code: str) -> tuple[float, float]:
    """Return (lon, lat) centroid for an ISO3 country code."""
    return _COUNTRY_CENTROIDS.get(country_code.upper(), (0.0, 0.0))


def _extract_value(
    indicator: dict[str, Any],
) -> tuple[float | None, str | None]:
    """Extract numeric value and unit from an HXL-tagged indicator dict."""
    value = indicator.get("#indicator+value")
    if value is None:
        value = indicator.get("#value")
    unit = indicator.get("#indicator+unit") or indicator.get("#unit")
    try:
        return float(value), unit
    except (TypeError, ValueError):
        return None, unit


def map_to_observations(
    indicator: dict[str, Any],
    org_id: str,
    incident_id: str,
) -> list[dict[str, Any]]:
    """Map an HDX HAPI indicator dict to one or more observation dicts.

    Returns a list of dicts with Observation-compatible fields. Typically
    produces exactly one observation per indicator record.
    """
    country = (
        indicator.get("#country+code")
        or indicator.get("#country+iso3")
        or "XXX"
    )
    country_name = indicator.get("#country+name", country)
    indicator_code = indicator.get("#indicator+code", "unknown")
    indicator_name = indicator.get("#indicator+name", indicator_code)
    date_str = indicator.get("#date")
    observed_at = from_iso(date_str) if date_str else now_ms()

    lon, lat = _country_centroid(country)
    geometry_wkt = f"POINT({lon} {lat})"

    value, unit = _extract_value(indicator)

    source_id = f"hdx:{country}:{indicator_code}"
    raw = json.dumps(
        indicator, sort_keys=True, default=str, separators=(",", ":")
    )
    raw_hash = "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    return [
        {
            "observation_id": generate_ulid(),
            "event_type": "humanitarian_indicator",
            "phenomenon": indicator_name,
            "value": value,
            "unit": unit,
            "geometry_wkt": geometry_wkt,
            "geometry_uncertainty": 50000.0,  # country-level, ~50km
            "observed_at": observed_at,
            "valid_from": observed_at,
            "valid_until": None,
            "received_at": now_ms(),
            "source_id": source_id,
            "source_type": SourceType.official_feed,
            "collection_method": "hdx_hapi",
            "source_reliability": 0.85,
            "freshness": 1.0,
            "corroboration_state": CorroborationState.uncorroborated,
            "model_uncertainty": None,
            "quality_flags": {
                "country_code": country,
                "country_name": country_name,
                "indicator_code": indicator_code,
                "hxl_tags": True,
            },
            "access_policy": AccessPolicy.internal,
            "provenance_chain": {
                "adapter": "hdx",
                "source": "hapi",
                "country": country,
                "indicator_code": indicator_code,
            },
            "raw_data_hash": raw_hash,
            "model_version": None,
            "supersedes": None,
            "duplicate_group": None,
            "org_id": org_id,
            "incident_id": incident_id,
        }
    ]


__all__ = ["HDXClient", "map_to_observations"]
