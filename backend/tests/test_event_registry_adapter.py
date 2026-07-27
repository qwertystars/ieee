"""Tests for the Event Registry adapter.

Tests:
- test_pull_articles: mock API response, pull 2 articles, verify mapping
- test_map_to_observation: verify article -> observation dict mapping
- test_map_to_observation_geometry: verify geometry from source location
- test_missing_api_key: graceful degradation when api_key missing
- test_api_error: graceful handling on HTTP error
- test_sync: DB dedup + Kafka publish via mock session
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.ingestion.adapters.event_registry import EventRegistryAdapter


def _make_article(
    uri: str,
    title: str = "Flood hits Rivertown",
    lat: float = 40.71,
    lon: float = -74.0,
    sentiment: float = -0.8,
    date: str = "2026-07-26T10:00:00Z",
    lang: str = "eng",
    source_title: str = "Rivertown Gazette",
    url: str = "https://example.org/article/1",
) -> dict[str, Any]:
    """Build a minimal Event Registry article dict."""
    return {
        "uri": uri,
        "title": title,
        "body": "Heavy rainfall caused severe flooding in downtown Rivertown.",
        "date": date,
        "lang": lang,
        "sentiment": sentiment,
        "url": url,
        "source": {
            "title": source_title,
            "location": {"lat": lat, "lon": lon},
        },
    }


@pytest.fixture
def two_articles():
    return [
        _make_article("ART-001", title="Flood hits Rivertown", sentiment=-0.8),
        _make_article("ART-002", title="Earthquake reported", lat=35.0, lon=139.0, sentiment=0.3),
    ]


def test_pull_articles(two_articles):
    """Mock Event Registry API, pull 2 articles, verify mapping."""

    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"articles": two_articles})

        adapter = EventRegistryAdapter({"api_key": "test_key"})
        adapter._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0,
        )
        try:
            result = await adapter.pull_articles()
            assert len(result) == 2
            assert result[0]["uri"] == "ART-001"
            assert result[1]["uri"] == "ART-002"

            obs = adapter.map_to_observation(result[0], "org_1", "inc_1")
            assert obs["event_type"] == "news_article"
            assert obs["phenomenon"] == "disaster_news"
            assert obs["source_type"] == "official_feed"
            assert obs["collection_method"] == "event_registry_api"
            assert obs["org_id"] == "org_1"
            assert obs["incident_id"] == "inc_1"
            assert obs["corroboration_state"] == "uncorroborated"
            assert obs["access_policy"] == "internal"
            assert obs["raw_data_hash"].startswith("sha256:")
            assert obs["source_id"] == "event_registry:ART-001"
            assert obs["source_reliability"] == 0.8
            assert obs["freshness"] == 1.0
            assert obs["valid_from"] == obs["observed_at"]
            assert obs["valid_until"] is None

            # Sentiment mapped to value + unit
            assert obs["value"] == -0.8
            assert obs["unit"] == "sentiment"
            assert obs["quality_flags"]["sentiment"] == -0.8
            assert obs["quality_flags"]["platform"] == "event_registry"
            assert obs["provenance_chain"]["article_uri"] == "ART-001"
        finally:
            await adapter.close()

    asyncio.run(_test())


def test_map_to_observation_geometry():
    """Verify geometry from article source location."""
    article = _make_article("ART-GEO", lat=40.71, lon=-74.0)
    adapter = EventRegistryAdapter({"api_key": "k"})
    obs = adapter.map_to_observation(article, "org_1", "inc_1")
    assert "POINT(-74.0 40.71)" in obs["geometry_wkt"]
    assert obs["geometry_uncertainty"] == 10000.0

    # Article without location falls back to sentinel
    article_no_geo = _make_article("ART-NOGEO")
    article_no_geo["source"]["location"] = {}
    obs2 = adapter.map_to_observation(article_no_geo, "org_1", "inc_1")
    assert "POINT(0 0)" in obs2["geometry_wkt"]
    assert obs2["geometry_uncertainty"] == 9_999_999.0


def test_missing_api_key():
    """Graceful degradation when api_key missing."""

    async def _test():
        adapter = EventRegistryAdapter({})
        result = await adapter.pull_articles()
        assert result == []
        await adapter.close()

    asyncio.run(_test())


def test_api_error():
    """Graceful handling on HTTP error (returns empty list)."""

    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Internal Server Error")

        adapter = EventRegistryAdapter({"api_key": "test_key"})
        adapter._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0,
        )
        try:
            result = await adapter.pull_articles()
            assert result == []
        finally:
            await adapter.close()

    asyncio.run(_test())


def test_sync(two_articles):
    """Verify sync pulls, dedups, and publishes to Kafka."""

    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"articles": two_articles})

        adapter = EventRegistryAdapter({"api_key": "test_key"})
        adapter._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0,
        )

        db = MagicMock()
        # check_and_record returns True (first time) for all
        db.add.return_value = None
        db.commit.return_value = None
        db.rollback.return_value = None

        producer = MagicMock()
        producer.send = AsyncMock()

        try:
            # Patch check_and_record to always return True
            import app.ingestion.adapters.event_registry as mod
            original = mod.check_and_record
            mod.check_and_record = lambda d, s, e: True
            try:
                count = await adapter.sync(db, producer, "org_1", "inc_1")
                assert count == 2
                assert producer.send.call_count == 2
                # Verify topic and message structure
                call_args = producer.send.call_args_list[0]
                assert call_args.args[0] == "observations.raw"
                msg = call_args.args[1]
                assert msg["source_type"] == "official_feed"
                assert msg["org_id"] == "org_1"
            finally:
                mod.check_and_record = original
        finally:
            await adapter.close()

    asyncio.run(_test())
