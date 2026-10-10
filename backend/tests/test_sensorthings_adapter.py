"""Tests for the SensorThings API adapter.

Mocks the SensorThings HTTP endpoint using httpx.MockTransport. Tests:
- test_pull_observations: 5 observations, verify mapping to Observation schema
- test_pagination: @iot.nextLink following across two pages
- test_timeout_handling: graceful handling on timeout (returns empty list)
- test_404_handling: graceful handling on 404 (returns empty list)
- test_map_to_observation_geometry: geometry correctly mapped from FeatureOfInterest
- test_sync_datastream: DB insert via mock session, returns correct count
"""

import asyncio
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from app.ingestion.adapters.sensorthings import (
    SensorThingsClient,
    map_to_observation,
    sync_datastream,
)


def _make_observation(iot_id: int, lat: float = 40.7484, lng: float = -73.9857) -> dict[str, Any]:
    """Build a minimal SensorThings observation with inlined Datastream + FOI."""
    return {
        "@iot.id": iot_id,
        "@iot.selfLink": f"http://st.example/v1.0/Observations({iot_id})",
        "phenomenonTime": "2024-07-18T12:00:00Z",
        "result": 1.5 + iot_id,
        "resultTime": "2024-07-18T12:00:00Z",
        "Datastream": {
            "@iot.id": 1,
            "name": "Water Level",
            "unitOfMeasurement": {
                "name": "Meter",
                "symbol": "m",
                "definition": "http://qudt.org/vocab/unit/M",
            },
        },
        "FeatureOfInterest": {
            "@iot.id": 1,
            "name": "Gauge 1",
            "encodingType": "application/vnd.geo+json",
            "feature": {"type": "Point", "coordinates": [lng, lat]},
        },
    }


@pytest.fixture
def five_observations():
    return [_make_observation(i) for i in range(1, 6)]


def test_pull_observations(five_observations):
    """Mock SensorThings endpoint with 5 observations, verify pull + mapping."""

    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"value": five_observations})

        client = SensorThingsClient("http://st.example")
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0
        )
        try:
            result = await client.pull_observations("1")
            assert len(result) == 5
            assert result[0]["@iot.id"] == 1
            assert result[4]["@iot.id"] == 5

            obs = map_to_observation(result[0], org_id="org_1", incident_id="inc_1")
            assert obs.event_type == "sensor_reading"
            assert obs.phenomenon == "Water Level"
            assert obs.unit == "m"
            assert obs.value == 2.5  # 1.5 + 1
            assert obs.source_type.value == "sensor"
            assert obs.collection_method == "sensorthings_api"
            assert obs.org_id == "org_1"
            assert obs.incident_id == "inc_1"
            assert obs.access_policy.value == "internal"
            assert obs.corroboration_state.value == "uncorroborated"
            assert obs.raw_data_hash.startswith("sha256:")
            assert obs.source_id == "sensorthings:1"
        finally:
            await client.close()

    asyncio.run(_test())


def test_pagination():
    """Mock @iot.nextLink, verify all observations pulled across two pages."""
    page1 = [_make_observation(i) for i in range(1, 4)]
    page2 = [_make_observation(i) for i in range(4, 6)]

    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "$skip=3" in url:
                return httpx.Response(200, json={"value": page2})
            return httpx.Response(
                200,
                json={
                    "value": page1,
                    "@iot.nextLink": (
                        "http://st.example/v1.0/Datastreams(1)/Observations"
                        "?$expand=Datastream,FeatureOfInterest&$skip=3"
                    ),
                },
            )

        client = SensorThingsClient("http://st.example")
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0
        )
        try:
            result = await client.pull_observations("1")
            assert len(result) == 5
            ids = [r["@iot.id"] for r in result]
            assert ids == [1, 2, 3, 4, 5]
        finally:
            await client.close()

    asyncio.run(_test())


def test_timeout_handling():
    """Mock timeout, verify graceful handling (returns empty list)."""

    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("simulated timeout")

        client = SensorThingsClient("http://st.example")
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=1.0
        )
        try:
            result = await client.pull_observations("1")
            assert result == []
        finally:
            await client.close()

    asyncio.run(_test())


def test_404_handling():
    """Mock 404, verify graceful handling (returns empty list)."""

    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": "not found"})

        client = SensorThingsClient("http://st.example")
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0
        )
        try:
            result = await client.pull_observations("999")
            assert result == []
        finally:
            await client.close()

    asyncio.run(_test())


def test_map_to_observation_geometry():
    """Verify geometry is correctly mapped from FeatureOfInterest."""
    st_obs = _make_observation(1, lat=40.0, lng=-74.0)
    obs = map_to_observation(st_obs, "org_1", "inc_1")
    wkt_str = obs.geometry.data
    assert "POINT" in wkt_str.upper()
    assert "-74" in wkt_str
    assert "40" in wkt_str
    assert obs.geometry.srid == 4326


def test_sync_datastream(five_observations):
    """Verify sync_datastream inserts observations via mock DB session."""

    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"value": five_observations})

        client = SensorThingsClient("http://st.example")
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0
        )

        db = MagicMock()
        db.execute.return_value.first.return_value = None  # No existing obs

        try:
            count = await sync_datastream(db, client, "1", "org_1", "inc_1")
            assert count == 5
            assert db.add.call_count == 5
            db.commit.assert_called_once()
        finally:
            await client.close()

    asyncio.run(_test())
