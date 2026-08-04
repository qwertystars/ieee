"""X/Twitter adapter — pull tweets from API v2 into observations.

Uses GET /2/tweets/search/recent with Bearer Token auth. Filters by
keywords and optional point_radius/bounding_box. Each tweet is processed
through the NLP pipeline for urgency, category, and PII redaction before
publishing to observations.raw.

All observations land as access_policy=sensitive,
corroboration_state=uncorroborated (draft) until human/fusion confirmation.
Degrades gracefully (returns empty, logs warning) when bearer token missing.
"""

import hashlib
import json
import logging

import httpx
from sqlalchemy.orm import Session

from app.lib.idempotency import (
    check_and_record,
    record_published_raw_event,
    stable_ingestion_claim,
)
from app.lib.time import from_iso, now_ms
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.perception.nlp import CitizenReportProcessor
from app.streaming.producer import ProducerManager

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
_MAX_PAGES = 10
_BASE_URL = "https://api.twitter.com/2/tweets/search/recent"
_TWEET_FIELDS = "created_at,author_id,text,geo,entities"
_PLACE_FIELDS = "full_name,bounding_box,country"
_EXPANSIONS = "geo.place_id"


class TwitterAdapter:
    """Adapter for X/Twitter API v2 recent search.

    config keys: bearer_token (str), keywords (list[str]),
    bounding_box (list[west,south,east,north]) or
    point_radius (dict with lon, lat, radius_km).
    """

    def __init__(self, config: dict, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.bearer_token: str | None = config.get("bearer_token")
        self.keywords: list[str] = config.get("keywords", [])
        self.bounding_box: list[float] | None = config.get("bounding_box")
        self.point_radius: dict | None = config.get("point_radius")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._nlp = CitizenReportProcessor()
        self._places: dict[str, dict] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {}
            if self.bearer_token:
                headers["Authorization"] = f"Bearer {self.bearer_token}"
            self._client = httpx.AsyncClient(
                timeout=self.timeout, headers=headers,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "TwitterAdapter":
        await self._get_client()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    def _build_query(self) -> str:
        """Build Twitter v2 query from keywords and geo filters."""
        parts: list[str] = []
        if self.keywords:
            parts.append("(" + " OR ".join(self.keywords) + ")")
        if self.bounding_box and len(self.bounding_box) == 4:
            w, s, e, n = self.bounding_box
            parts.append(f"bounding_box:[{w} {s} {e} {n}]")
        if self.point_radius:
            lon = self.point_radius.get("lon")
            lat = self.point_radius.get("lat")
            r = self.point_radius.get("radius_km", 25)
            if lon is not None and lat is not None:
                parts.append(f"point_radius:[{lon} {lat} {r}km]")
        return " ".join(parts) if parts else "flood OR earthquake"

    async def pull_observations(self) -> list[dict]:
        """Pull recent tweets matching the configured query.

        Returns empty list if bearer token missing or API error.
        """
        if not self.bearer_token:
            logger.warning("Twitter bearer credential missing, skipping pull")
            return []

        client = await self._get_client()
        params: dict[str, str | int] = {
            "query": self._build_query(),
            "max_results": 100,
            "tweet.fields": _TWEET_FIELDS,
            "place.fields": _PLACE_FIELDS,
            "expansions": _EXPANSIONS,
        }
        tweets: list[dict] = []
        next_token: str | None = None
        pages = 0
        while pages < _MAX_PAGES:
            if next_token:
                params["next_token"] = next_token
            try:
                resp = await client.get(_BASE_URL, params=params)
                if resp.status_code != 200:
                    logger.warning(
                        "Twitter API %d: %s",
                        resp.status_code, resp.text[:200],
                    )
                    break
                data = resp.json()
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                logger.warning("Twitter API error: %s", exc)
                break
            tweets.extend(data.get("data", []))
            for place in data.get("includes", {}).get("places", []):
                self._places[place["id"]] = place
            next_token = data.get("meta", {}).get("next_token")
            if not next_token:
                break
            pages += 1
        return tweets

    def _extract_geometry(self, tweet: dict) -> tuple[str, float]:
        """Return (wkt, uncertainty_m) from tweet place bounding box.

        Falls back to POINT(0 0) with huge uncertainty when no place.
        """
        geo = tweet.get("geo") or {}
        place_id = geo.get("place_id")
        if place_id and place_id in self._places:
            bbox = (
                self._places[place_id]
                .get("bounding_box", {})
                .get("bbox")
            )
            if bbox and len(bbox) == 4:
                west, south, east, north = bbox
                lon = (west + east) / 2
                lat = (south + north) / 2
                uncertainty_m = (
                    max(abs(east - west), abs(north - south)) * 111_000
                )
                return f"POINT({lon} {lat})", uncertainty_m
        return "POINT(0 0)", 9_999_999.0

    def map_to_observation(
        self, tweet: dict, org_id: str, incident_id: str,
    ) -> dict:
        """Map a tweet to an observation dict with NLP processing."""
        text = tweet.get("text", "")
        report = self._nlp.process_report(text=text)

        geometry_wkt, uncertainty = self._extract_geometry(tweet)
        observed_at = (
            from_iso(tweet["created_at"]) if tweet.get("created_at")
            else now_ms()
        )
        tweet_id = tweet.get("id", generate_ulid())
        source_id = f"twitter:{tweet_id}"

        raw = json.dumps(
            tweet, sort_keys=True, default=str, separators=(",", ":"),
        )
        raw_hash = "sha256:" + hashlib.sha256(raw.encode()).hexdigest()

        return {
            "observation_id": generate_ulid(),
            "event_type": "social_media_post",
            "phenomenon": report.category.value,
            "value": None,
            "unit": None,
            "geometry_wkt": geometry_wkt,
            "geometry_uncertainty": uncertainty,
            "observed_at": observed_at,
            "valid_from": observed_at,
            "valid_until": None,
            "received_at": now_ms(),
            "source_id": source_id,
            "external_id": tweet_id,
            "source_type": SourceType.social_media.value,
            "collection_method": "twitter_api_v2",
            "source_reliability": 0.5,
            "freshness": 1.0,
            "corroboration_state": CorroborationState.uncorroborated.value,
            "model_uncertainty": None,
            "quality_flags": {
                "text": report.redacted_text,
                "urgency": report.urgency.value,
                "category": report.category.value,
                "language": report.language,
                "credibility": report.credibility,
                "place_names": report.geolocation.place_names,
                "platform": "twitter",
            },
            "access_policy": AccessPolicy.sensitive.value,
            "provenance_chain": {
                "platform": "twitter",
                "tweet_id": tweet_id,
                "author_id": tweet.get("author_id", ""),
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
        """Pull tweets, process through NLP, dedup, publish to Kafka.

        Returns the number of new observations published.
        """
        tweets = await self.pull_observations()
        if not tweets:
            return 0

        count = 0
        for tweet in tweets:
            tweet_id = tweet.get("id")
            if not tweet_id:
                continue
            obs = self.map_to_observation(tweet, org_id, incident_id)
            if not check_and_record(
                db,
                "twitter",
                tweet_id,
                org_id=org_id,
                incident_id=incident_id,
                payload=stable_ingestion_claim(obs),
                commit=False,
            ):
                continue
            try:
                await producer.send("observations.raw", obs)
                record_published_raw_event(db, obs)
                db.commit()
            except (OSError, RuntimeError, TimeoutError):
                db.rollback()
                raise
            count += 1

        logger.info("Twitter: published %d/%d tweets", count, len(tweets))
        return count


__all__ = ["TwitterAdapter"]
