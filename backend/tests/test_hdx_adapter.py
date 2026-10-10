"""Tests for the HDX HAPI adapter.

Tests:
- test_pull_indicators: mock HDX HAPI response, pull 2 indicators, verify mapping
- test_map_to_observations: verify indicator -> observation dict mapping
- test_map_to_observations_geometry: verify country centroid geometry
- test_pull_with_indicator_filter: filter by indicator_ids
"""

import asyncio
from typing import Any

import httpx
import pytest

from app.ingestion.adapters.hdx import HDXClient, map_to_observations


def _make_hdx_indicator(
    code: str,
    name: str,
    value: float,
    country: str = "COL",
    country_name: str = "Colombia",
    date: str = "2024-07-01",
    unit: str = "people",
) -> dict[str, Any]:
    """Build a minimal HDX HAPI indicator dict with HXL tags."""
    return {
        "#country+code": country,
        "#country+name": country_name,
        "#date": date,
        "#indicator+code": code,
        "#indicator+name": name,
        "#indicator+value": value,
        "#indicator+unit": unit,
    }


@pytest.fixture
def two_indicators():
    """Two HDX HAPI indicators: population and affected population."""
    return [
        _make_hdx_indicator("POP", "Population", 51000000),
        _make_hdx_indicator("AFFECTED", "Affected Population", 2500000),
    ]


def test_pull_indicators(two_indicators):
    """Mock HDX HAPI response, pull 2 indicators, verify mapping."""

    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"data": two_indicators, "next_url": None}
            )

        client = HDXClient("https://hapi.humdata.org/api/v1")
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0
        )
        try:
            result = await client.pull_indicators("COL")
            assert len(result) == 2
            assert result[0]["#indicator+code"] == "POP"
            assert result[1]["#indicator+code"] == "AFFECTED"

            # Map both indicators to observations
            all_obs = []
            for ind in result:
                obs_list = map_to_observations(ind, "org_1", "inc_1")
                assert len(obs_list) == 1
                all_obs.extend(obs_list)

            assert len(all_obs) == 2

            for obs in all_obs:
                assert obs["event_type"] == "humanitarian_indicator"
                assert obs["source_type"].value == "official_feed"
                assert obs["collection_method"] == "hdx_hapi"
                assert obs["org_id"] == "org_1"
                assert obs["incident_id"] == "inc_1"
                assert obs["corroboration_state"].value == "uncorroborated"
                assert obs["access_policy"].value == "internal"
                assert obs["raw_data_hash"].startswith("sha256:")
                assert "POINT" in obs["geometry_wkt"]
                assert obs["geometry_uncertainty"] == 50000.0
                assert obs["source_reliability"] == 0.85
                assert obs["freshness"] == 1.0
                assert obs["valid_from"] == obs["observed_at"]
                assert obs["valid_until"] is None

            # Verify first indicator (POP)
            obs0 = all_obs[0]
            assert obs0["phenomenon"] == "Population"
            assert obs0["value"] == 51000000.0
            assert obs0["unit"] == "people"
            assert obs0["source_id"] == "hdx:COL:POP"
            assert obs0["quality_flags"]["country_code"] == "COL"
            assert obs0["quality_flags"]["country_name"] == "Colombia"
            assert obs0["quality_flags"]["indicator_code"] == "POP"
            assert obs0["provenance_chain"]["adapter"] == "hdx"
            assert obs0["provenance_chain"]["source"] == "hapi"

            # Verify second indicator (AFFECTED)
            obs1 = all_obs[1]
            assert obs1["phenomenon"] == "Affected Population"
            assert obs1["value"] == 2500000.0
            assert obs1["source_id"] == "hdx:COL:AFFECTED"

            # Verify unique observation_ids
            obs_ids = [o["observation_id"] for o in all_obs]
            assert len(set(obs_ids)) == 2
        finally:
            await client.close()

    asyncio.run(_test())


def test_map_to_observations_geometry():
    """Verify country centroid geometry mapping for different countries."""
    # Colombia centroid: (-74.0, 4.6)
    ind_col = _make_hdx_indicator("POP", "Population", 1000, country="COL")
    obs_col = map_to_observations(ind_col, "org_1", "inc_1")[0]
    assert "POINT" in obs_col["geometry_wkt"]
    assert "-74" in obs_col["geometry_wkt"]
    assert "4.6" in obs_col["geometry_wkt"]

    # Afghanistan centroid: (67.0, 33.0)
    ind_afg = _make_hdx_indicator("POP", "Population", 1000, country="AFG")
    obs_afg = map_to_observations(ind_afg, "org_1", "inc_1")[0]
    assert "67" in obs_afg["geometry_wkt"]
    assert "33" in obs_afg["geometry_wkt"]

    # Unknown country defaults to (0.0, 0.0)
    ind_xxx = _make_hdx_indicator("POP", "Population", 1000, country="ZZZ")
    obs_xxx = map_to_observations(ind_xxx, "org_1", "inc_1")[0]
    assert "POINT(0.0 0.0)" in obs_xxx["geometry_wkt"]


def test_pull_with_indicator_filter(two_indicators):
    """Filter pulled indicators by indicator_ids list."""

    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"data": two_indicators, "next_url": None}
            )

        client = HDXClient("https://hapi.humdata.org/api/v1")
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0
        )
        try:
            # Filter to only POP indicator
            result = await client.pull_indicators("COL", indicator_ids=["POP"])
            assert len(result) == 1
            assert result[0]["#indicator+code"] == "POP"
        finally:
            await client.close()

    asyncio.run(_test())
