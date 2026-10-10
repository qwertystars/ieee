"""YouTube adapter — pull disaster-related videos into observations.

Uses YouTube Data API v3 search.list with API key auth. Supports
location + locationRadius geo filters. Each video's title and description
is processed through the NLP pipeline for urgency, category, and PII
redaction before publishing to observations.raw.

All observations land as access_policy=sensitive,
corroboration_state=uncorroborated (draft) until human/fusion confirmation.
Degrades gracefully (returns empty, logs warning) when API key missing.
Geometry uses the search location centroid when provided; otherwise a
sentinel POINT(0 0) with high uncertainty.
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
_BASE_URL = "https://www.googleapis.com/youtube/v3/search"
_SENTINEL_GEOMETRY = "POINT(0 0)"
_SENTINEL_UNCERTAINTY = 9_999_999.0
_KM_PER_DEGREE = 111.0


class YouTubeAdapter:
    """Adapter for YouTube Data API v3 search.

    config keys: api_key (str), keywords (list[str]),
    location (dict with lat, lon) — optional,
    location_radius (str like "10km") — optional.
    """

    def __init__(self, config: dict, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.api_key: str | None = config.get("api_key")
        self.keywords: list[str] = config.get("keywords", [])
        self.location: dict | None = config.get("location")
        self.location_radius: str | None = config.get("location_radius")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._nlp = CitizenReportProcessor()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "YouTubeAdapter":
        await self._get_client()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    def _build_params(self) -> dict:
        """Build YouTube search.list query parameters."""
        params = {
            "part": "snippet",
            "type": "video",
            "maxResults": 50,
            "key": self.api_key,
        }
        if self.keywords:
            params["q"] = " ".join(self.keywords)
        if self.location and self.location_radius:
            lat = self.location.get("lat")
            lon = self.location.get("lon")
            if lat is not None and lon is not None:
                params["location"] = f"{lat},{lon}"
                params["locationRadius"] = self.location_radius
        return params

    def _geometry(self) -> tuple[str, float]:
        """Return (wkt, uncertainty_m) from search location.

        Uses the configured search location as the geometry centroid
        (all results are within locationRadius of it). Falls back to
        sentinel POINT(0 0) when no location is configured.
        """
        if self.location and self.location_radius:
            lat = self.location.get("lat")
            lon = self.location.get("lon")
            if lat is not None and lon is not None:
                radius_km = float(
                    self.location_radius.rstrip("km").rstrip("m")
                )
                return (
                    f"POINT({lon} {lat})",
                    radius_km * 1000.0,
                )
        return _SENTINEL_GEOMETRY, _SENTINEL_UNCERTAINTY

    async def pull_observations(self) -> list[dict]:
        """Pull recent videos matching the configured search.

        Returns empty list if API key missing or API error.
        """
        if not self.api_key:
            logger.warning("YouTube API key missing, skipping pull")
            return []

        client = await self._get_client()
        params = self._build_params()
        videos: list[dict] = []
        next_token: str | None = None
        pages = 0
        while pages < _MAX_PAGES:
            if next_token:
                params["pageToken"] = next_token
            try:
                resp = await client.get(_BASE_URL, params=params)
                if resp.status_code != 200:
                    logger.warning(
                        "YouTube API %d: %s",
                        resp.status_code, resp.text[:200],
                    )
                    break
                data = resp.json()
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                logger.warning("YouTube API error: %s", exc)
                break
            videos.extend(data.get("items", []))
            next_token = data.get("nextPageToken")
            if not next_token:
                break
            pages += 1
        return videos

    def map_to_observation(
        self, video: dict, org_id: str, incident_id: str,
    ) -> dict:
        """Map a YouTube video to an observation dict with NLP processing."""
        snippet = video.get("snippet", {})
        title = snippet.get("title", "")
        description = snippet.get("description", "")
        text = f"{title}. {description}".strip() if description else title
        report = self._nlp.process_report(text=text)

        geometry_wkt, uncertainty = self._geometry()
        observed_at = (
            from_iso(snippet["publishedAt"]) if snippet.get("publishedAt")
            else now_ms()
        )
        video_id = video.get("id", {}).get("videoId", generate_ulid())
        source_id = f"youtube:{video_id}"

        raw = json.dumps(
            video, sort_keys=True, default=str, separators=(",", ":"),
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
            "external_id": video_id,
            "source_type": SourceType.social_media.value,
            "collection_method": "youtube_data_api_v3",
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
                "platform": "youtube",
                "channel_id": snippet.get("channelId", ""),
                "channel_title": snippet.get("channelTitle", ""),
            },
            "access_policy": AccessPolicy.sensitive.value,
            "provenance_chain": {
                "platform": "youtube",
                "video_id": video_id,
                "channel_id": snippet.get("channelId", ""),
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
        """Pull videos, process through NLP, dedup, publish to Kafka.

        Returns the number of new observations published.
        """
        videos = await self.pull_observations()
        if not videos:
            return 0

        count = 0
        for video in videos:
            video_id = video.get("id", {}).get("videoId")
            if not video_id:
                continue
            obs = self.map_to_observation(video, org_id, incident_id)
            if not check_and_record(
                db,
                "youtube",
                video_id,
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

        logger.info("YouTube: published %d/%d videos", count, len(videos))
        return count


__all__ = ["YouTubeAdapter"]
