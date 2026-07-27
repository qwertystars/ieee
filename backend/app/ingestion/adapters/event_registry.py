"""Event Registry adapter — pull geo-located disaster news into observations.

Uses the Event Registry API (https://github.com/EventRegistry/eventregistry-python)
GET /api/v1/minuteStreamArticles with mandatorySourceLocation=true for geo-located
articles. Each article is mapped to an observation with source_type=official_feed,
geometry from the article's source location, and quality_flags.sentiment from the
article's sentiment score.

The eventregistry Python SDK is the canonical client; this adapter uses httpx
directly to match the codebase convention (all adapters use httpx, no SDKs).
The polling cadence (every 60s) is the caller's responsibility — this adapter
exposes pull_articles() for the ingestion loop to call on schedule.

Degrades gracefully (returns empty, logs warning) when API key missing.
"""

import hashlib
import json
import logging

import httpx
from sqlalchemy.orm import Session

from app.lib.idempotency import check_and_record
from app.lib.time import from_iso, now_ms
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.streaming.producer import ProducerManager

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
_BASE_URL = "https://api.eventregistry.org/api/v1"
_DEFAULT_KEYWORDS = [
    "flood", "earthquake", "hurricane", "wildfire",
    "landslide", "tsunami", "cyclone", "disaster",
]
_SENTINEL_GEOMETRY = "POINT(0 0)"
_SENTINEL_UNCERTAINTY = 9_999_999.0


class EventRegistryAdapter:
    """Adapter for Event Registry minuteStreamArticles API.

    config keys: api_key (str), keywords (list[str]),
    location_uri (str, optional — e.g. "http://en.wikipedia.org/wiki/India").
    """

    def __init__(self, config: dict, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.api_key: str | None = config.get("api_key")
        self.keywords: list[str] = config.get("keywords", _DEFAULT_KEYWORDS)
        self.location_uri: str | None = config.get("location_uri")
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

    async def __aenter__(self) -> "EventRegistryAdapter":
        await self._get_client()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def pull_articles(self) -> list[dict]:
        """Pull recent geo-located articles matching disaster keywords.

        Returns empty list if api_key missing or API error.
        """
        if not self.api_key:
            logger.warning("Event Registry api_key missing, skipping pull")
            return []

        client = await self._get_client()
        params: dict[str, str | int] = {
            "apiKey": self.api_key,
            "mandatorySourceLocation": "true",
            "keyword": " OR ".join(self.keywords),
            "articlesCount": 100,
        }
        if self.location_uri:
            params["locationUri"] = self.location_uri

        try:
            resp = await client.get(
                f"{_BASE_URL}/minuteStreamArticles", params=params,
            )
            if resp.status_code != 200:
                logger.warning(
                    "Event Registry API %d: %s",
                    resp.status_code, resp.text[:200],
                )
                return []
            data = resp.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Event Registry API error: %s", exc)
            return []

        articles = data.get("articles") or []
        if not articles:
            # minuteStreamArticles may nest under recentActivity
            articles = (
                data.get("recentActivity", {}).get("articles", [])
            )
        return articles

    def _extract_geometry(self, article: dict) -> tuple[str, float]:
        """Return (wkt, uncertainty_m) from article source location."""
        source = article.get("source") or {}
        location = source.get("location") or {}
        lat = location.get("lat")
        lon = location.get("lon")
        if lat is not None and lon is not None:
            return f"POINT({lon} {lat})", 10000.0  # ~10km city-level
        return _SENTINEL_GEOMETRY, _SENTINEL_UNCERTAINTY

    def map_to_observation(
        self, article: dict, org_id: str, incident_id: str,
    ) -> dict:
        """Map an Event Registry article to an observation dict."""
        title = article.get("title", "")

        geometry_wkt, uncertainty = self._extract_geometry(article)
        observed_at = (
            from_iso(article["date"]) if article.get("date") else now_ms()
        )
        article_uri = article.get("uri", generate_ulid())
        source_id = f"event_registry:{article_uri}"

        sentiment = article.get("sentiment")
        sentiment_score = (
            sentiment if isinstance(sentiment, (int, float)) else None
        )

        raw = json.dumps(
            article, sort_keys=True, default=str, separators=(",", ":"),
        )
        raw_hash = "sha256:" + hashlib.sha256(raw.encode()).hexdigest()

        return {
            "observation_id": generate_ulid(),
            "event_type": "news_article",
            "phenomenon": "disaster_news",
            "value": sentiment_score,
            "unit": "sentiment" if sentiment_score is not None else None,
            "geometry_wkt": geometry_wkt,
            "geometry_uncertainty": uncertainty,
            "observed_at": observed_at,
            "valid_from": observed_at,
            "valid_until": None,
            "received_at": now_ms(),
            "source_id": source_id,
            "source_type": SourceType.official_feed.value,
            "collection_method": "event_registry_api",
            "source_reliability": 0.8,
            "freshness": 1.0,
            "corroboration_state": CorroborationState.uncorroborated.value,
            "model_uncertainty": None,
            "quality_flags": {
                "title": title,
                "sentiment": sentiment_score,
                "language": article.get("lang", ""),
                "source_title": article.get("source", {}).get("title", ""),
                "url": article.get("url", ""),
                "platform": "event_registry",
            },
            "access_policy": AccessPolicy.internal.value,
            "provenance_chain": {
                "platform": "event_registry",
                "article_uri": article_uri,
                "url": article.get("url", ""),
            },
            "raw_data_hash": raw_hash,
            "model_version": None,
            "supersedes": None,
            "duplicate_group": None,
            "org_id": org_id,
            "incident_id": incident_id,
        }

    async def sync(
        self, db: Session, producer: ProducerManager,
        org_id: str, incident_id: str,
    ) -> int:
        """Pull articles, dedup, publish to Kafka.

        Returns the number of new observations published.
        """
        articles = await self.pull_articles()
        if not articles:
            return 0

        count = 0
        for article in articles:
            article_uri = article.get("uri")
            if not article_uri:
                continue
            if not check_and_record(db, "event_registry", article_uri):
                continue
            obs = self.map_to_observation(article, org_id, incident_id)
            await producer.send("observations.raw", obs)
            count += 1

        logger.info(
            "Event Registry: published %d/%d articles", count, len(articles),
        )
        return count


__all__ = ["EventRegistryAdapter"]
