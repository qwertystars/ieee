"""Instagram adapter — pull hashtag posts into observations.

Uses the Instagram Graph API v22 for hashtag search. Note: Instagram
removed geo location from the Graph API in v22, so geometry is a sentinel
POINT(0 0) — NLP extracts place names from captions for downstream
gazetteer resolution.

Each post caption is processed through the NLP pipeline for urgency,
category, and PII redaction before publishing to observations.raw.

All observations land as access_policy=sensitive,
corroboration_state=uncorroborated (draft) until human/fusion confirmation.
Degrades gracefully (returns empty, logs warning) when access token missing.
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
_BASE_URL = "https://graph.facebook.com/v22.0"
_MEDIA_FIELDS = "id,caption,timestamp,permalink,media_type,media_url"
_SENTINEL_GEOMETRY = "POINT(0 0)"
_SENTINEL_UNCERTAINTY = 9_999_999.0


class InstagramAdapter:
    """Adapter for Instagram Graph API v22 hashtag search.

    config keys: access_token (str), user_id (str),
    hashtags (list[str] without the # prefix).
    """

    def __init__(self, config: dict, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.access_token: str | None = config.get("access_token")
        self.user_id: str | None = config.get("user_id")
        self.hashtags: list[str] = config.get("hashtags", [])
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

    async def __aenter__(self) -> "InstagramAdapter":
        await self._get_client()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def _resolve_hashtag_id(self, hashtag: str) -> str | None:
        """Resolve a hashtag name to its IG hashtag ID."""
        client = await self._get_client()
        params = {
            "user_id": self.user_id,
            "q": hashtag,
            "access_token": self.access_token,
        }
        try:
            resp = await client.get(
                f"{_BASE_URL}/ig_hashtag_search", params=params,
            )
            if resp.status_code != 200:
                logger.warning(
                    "Instagram hashtag search '%s' returned %d",
                    hashtag, resp.status_code,
                )
                return None
            data = resp.json().get("data", [])
            return data[0].get("id") if data else None
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Instagram hashtag search error: %s", exc)
            return None

    async def _pull_recent_media(self, hashtag_id: str) -> list[dict]:
        """Pull recent media for a hashtag ID."""
        client = await self._get_client()
        params = {
            "user_id": self.user_id,
            "fields": _MEDIA_FIELDS,
            "access_token": self.access_token,
        }
        try:
            resp = await client.get(
                f"{_BASE_URL}/{hashtag_id}/recent_media", params=params,
            )
            if resp.status_code != 200:
                logger.warning(
                    "Instagram recent_media returned %d", resp.status_code,
                )
                return []
            return resp.json().get("data", [])
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Instagram recent_media error: %s", exc)
            return []

    async def pull_observations(self) -> list[dict]:
        """Pull recent media posts matching configured hashtags.

        Returns empty list if access token missing or API error.
        """
        if not self.access_token or not self.user_id:
            logger.warning("Instagram credentials missing, skipping pull")
            return []

        media: list[dict] = []
        for hashtag in self.hashtags:
            hashtag_id = await self._resolve_hashtag_id(hashtag)
            if hashtag_id is None:
                continue
            media.extend(await self._pull_recent_media(hashtag_id))
        return media

    def map_to_observation(
        self, media: dict, org_id: str, incident_id: str,
    ) -> dict:
        """Map an Instagram media post to an observation dict with NLP."""
        caption = media.get("caption", "")
        report = self._nlp.process_report(text=caption)

        observed_at = (
            from_iso(media["timestamp"]) if media.get("timestamp")
            else now_ms()
        )
        media_id = media.get("id", generate_ulid())
        source_id = f"instagram:{media_id}"

        raw = json.dumps(
            media, sort_keys=True, default=str, separators=(",", ":"),
        )
        raw_hash = "sha256:" + hashlib.sha256(raw.encode()).hexdigest()

        return {
            "observation_id": generate_ulid(),
            "event_type": "social_media_post",
            "phenomenon": report.category.value,
            "value": None,
            "unit": None,
            "geometry_wkt": _SENTINEL_GEOMETRY,
            "geometry_uncertainty": _SENTINEL_UNCERTAINTY,
            "observed_at": observed_at,
            "valid_from": observed_at,
            "valid_until": None,
            "received_at": now_ms(),
            "source_id": source_id,
            "external_id": media_id,
            "source_type": SourceType.social_media.value,
            "collection_method": "instagram_graph_api",
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
                "platform": "instagram",
                "media_type": media.get("media_type", ""),
                "permalink": media.get("permalink", ""),
            },
            "access_policy": AccessPolicy.sensitive.value,
            "provenance_chain": {
                "platform": "instagram",
                "media_id": media_id,
                "permalink": media.get("permalink", ""),
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
        """Pull media, process through NLP, dedup, publish to Kafka.

        Returns the number of new observations published.
        """
        media_list = await self.pull_observations()
        if not media_list:
            return 0

        count = 0
        for media in media_list:
            media_id = media.get("id")
            if not media_id:
                continue
            obs = self.map_to_observation(media, org_id, incident_id)
            if not check_and_record(
                db,
                "instagram",
                media_id,
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

        logger.info("Instagram: published %d/%d posts", count, len(media_list))
        return count


__all__ = ["InstagramAdapter"]
