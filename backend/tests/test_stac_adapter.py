"""Tests for the STAC adapter.

Tests:
- test_index_stac_items: index 3 sample STAC items, verify metadata extracted
- test_search_by_cloud_cover: filter items by cloud cover threshold
- test_search_local_catalog: search a local file-based catalog (offline)
- test_search_remote: mock STAC API search with pagination
"""

import asyncio
import json
import os
import tempfile
from typing import Any

import httpx
import pytest

from app.ingestion.adapters.stac import STACClient, index_item, _filter_items


def _make_stac_item(
    item_id: str,
    collection: str = "sentinel-2-l2a",
    cloud_cover: float = 10.0,
    datetime_str: str = "2024-07-18T12:00:00Z",
    platform: str = "sentinel-2a",
    bbox: list[float] | None = None,
) -> dict[str, Any]:
    """Build a minimal STAC Item for testing."""
    if bbox is None:
        bbox = [-74.0, 40.0, -73.9, 40.1]
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": item_id,
        "collection": collection,
        "bbox": bbox,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [bbox[0], bbox[1]],
                [bbox[2], bbox[1]],
                [bbox[2], bbox[3]],
                [bbox[0], bbox[3]],
                [bbox[0], bbox[1]],
            ]],
        },
        "properties": {
            "datetime": datetime_str,
            "eo:cloud_cover": cloud_cover,
            "platform": platform,
            "instruments": ["MSI"],
            "constellation": "sentinel-2",
        },
        "assets": {
            "visual": {
                "href": f"https://example.com/{item_id}/visual.jpg",
                "type": "image/jpeg",
            },
            "B02": {
                "href": f"https://example.com/{item_id}/B02.tif",
                "type": "image/tiff",
            },
        },
        "links": [],
    }


@pytest.fixture
def three_stac_items():
    """Three STAC items with cloud cover 5%, 25%, 80%."""
    return [
        _make_stac_item("S2_001", cloud_cover=5.0),
        _make_stac_item("S2_002", cloud_cover=25.0),
        _make_stac_item("S2_003", cloud_cover=80.0),
    ]


def test_index_stac_items(three_stac_items):
    """Index 3 sample STAC items, verify metadata extracted correctly."""
    results = [
        index_item(item, org_id="org_1", incident_id="inc_1")
        for item in three_stac_items
    ]
    assert len(results) == 3

    for result in results:
        assert result["event_type"] == "satellite_imagery"
        assert result["source_type"].value == "satellite"
        assert result["collection_method"] == "stac_api"
        assert result["org_id"] == "org_1"
        assert result["incident_id"] == "inc_1"
        assert result["corroboration_state"].value == "uncorroborated"
        assert result["access_policy"].value == "internal"
        assert result["raw_data_hash"].startswith("sha256:")
        assert result["source_id"].startswith("stac:sentinel-2-l2a:")
        assert "POLYGON" in result["geometry_wkt"]
        assert result["observed_at"] > 0
        assert result["valid_from"] == result["observed_at"]
        assert result["valid_until"] is None
        assert result["source_reliability"] == 0.9
        assert result["freshness"] == 1.0

    # Verify first item (cloud_cover=5.0)
    first = results[0]
    assert first["value"] == 5.0
    assert first["unit"] == "%"
    assert first["phenomenon"] == "sentinel-2"
    assert first["quality_flags"]["cloud_cover"] == 5.0
    assert first["quality_flags"]["platform"] == "sentinel-2a"
    assert first["quality_flags"]["instruments"] == ["MSI"]
    assert first["quality_flags"]["constellation"] == "sentinel-2"
    assert "visual" in first["quality_flags"]["assets"]
    assert first["quality_flags"]["assets"]["visual"]["href"] == (
        "https://example.com/S2_001/visual.jpg"
    )
    assert "B02" in first["quality_flags"]["assets"]
    assert first["provenance_chain"]["collection"] == "sentinel-2-l2a"
    assert first["provenance_chain"]["item_id"] == "S2_001"
    assert first["provenance_chain"]["adapter"] == "stac"

    # Verify cloud cover values are distinct
    assert results[0]["value"] == 5.0
    assert results[1]["value"] == 25.0
    assert results[2]["value"] == 80.0

    # Verify unique observation_ids and source_ids
    obs_ids = [r["observation_id"] for r in results]
    source_ids = [r["source_id"] for r in results]
    assert len(set(obs_ids)) == 3
    assert len(set(source_ids)) == 3


def test_search_by_cloud_cover(three_stac_items):
    """Filter items by cloud cover threshold — only items <= max_cloud_cover."""
    bbox = (-74.5, 39.5, -73.5, 40.5)
    dt_range = (0, 9999999999999)

    # max_cloud_cover=20 → only item with cloud_cover=5.0 passes
    filtered = _filter_items(
        three_stac_items, bbox, dt_range, None, max_cloud_cover=20.0
    )
    assert len(filtered) == 1
    assert filtered[0]["id"] == "S2_001"

    # max_cloud_cover=30 → items with 5.0 and 25.0 pass
    filtered = _filter_items(
        three_stac_items, bbox, dt_range, None, max_cloud_cover=30.0
    )
    assert len(filtered) == 2
    ids = [f["id"] for f in filtered]
    assert "S2_001" in ids
    assert "S2_002" in ids

    # max_cloud_cover=None → all items pass
    filtered = _filter_items(
        three_stac_items, bbox, dt_range, None, max_cloud_cover=None
    )
    assert len(filtered) == 3

    # max_cloud_cover=100 → all items pass (all <= 100)
    filtered = _filter_items(
        three_stac_items, bbox, dt_range, None, max_cloud_cover=100.0
    )
    assert len(filtered) == 3


def test_search_local_catalog(three_stac_items):
    """Search a local file-based STAC catalog (offline, no network)."""
    catalog = {
        "type": "FeatureCollection",
        "features": three_stac_items,
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(catalog, f)
        catalog_path = f.name

    try:
        client = STACClient(catalog_path)
        assert client._is_file is True

        bbox = (-74.5, 39.5, -73.5, 40.5)
        dt_range = (0, 9999999999999)

        # Search without cloud cover filter
        items = asyncio.run(
            client.search_items(bbox=bbox, datetime_range=dt_range)
        )
        assert len(items) == 3

        # Search with cloud cover filter
        items = asyncio.run(
            client.search_items(
                bbox=bbox, datetime_range=dt_range, max_cloud_cover=20.0
            )
        )
        assert len(items) == 1
        assert items[0]["id"] == "S2_001"
    finally:
        os.unlink(catalog_path)


def test_search_remote():
    """Mock STAC API search endpoint, verify pagination and results."""

    async def _test():
        page1 = [_make_stac_item("S2_001", cloud_cover=5.0)]
        page2 = [_make_stac_item("S2_002", cloud_cover=15.0)]

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "page=2" in url:
                return httpx.Response(200, json={"features": page2, "links": []})
            return httpx.Response(
                200,
                json={
                    "features": page1,
                    "links": [
                        {
                            "rel": "next",
                            "href": "http://stac.example/search?page=2",
                        }
                    ],
                },
            )

        client = STACClient("http://stac.example")
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0
        )
        try:
            results = await client.search_items(
                bbox=(-74.5, 39.5, -73.5, 40.5),
                datetime_range=(0, 9999999999999),
                max_cloud_cover=10.0,
            )
            assert len(results) == 1
            assert results[0]["id"] == "S2_001"
        finally:
            await client.close()

    asyncio.run(_test())
