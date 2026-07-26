"""Reddit adapter — pull posts from disaster subreddits into observations.

Uses Reddit OAuth2 (client_credentials grant) to fetch new posts from
configured subreddits via the Reddit API. Each post is processed through
the NLP pipeline for urgency, category, and PII redaction before publishing
to observations.raw.

All observations land as access_policy=sensitive,
corroboration_state=uncorroborated (draft) until human/fusion confirmation.
Degrades gracefully (returns empty, logs warning) when credentials missing.
Geometry is None (POINT(0 0) sentinel) — NLP extracts place names for
downstream gazetteer resolution.
"""

import hashlib
import json
import logging

import httpx
from sqlalchemy.orm import Session

from app.lib.idempotency import check_and_record
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.perception.nlp import CitizenReportProcessor
from app.streaming.producer import ProducerManager

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_BASE_URL = "https://oauth.reddit.com"
_DEFAULT_SUBREDDITS = ["disasterresponse", "emergency", "flooding"]
_SENTINEL_GEOMETRY = "POINT(0 0)"
_SENTINEL_UNCERTAINTY = 9_999_999.0


class RedditAdapter:
    """Adapter for Reddit OAuth2 API.

    config keys: client_id (str), client_secret (str), user_agent (str),
    subreddits (list[str]), keywords (list[str], optional filter).
    """

    def __init__(self, config: dict, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.client_id: str | None = config.get("client_id")
        self.client_secret: str | None = config.get("client_secret")
        self.user_agent: str = config.get(
            "user_agent", "ResQNet-SAGE/1.0"
        )
        self.subreddits: list[str] = config.get(
            "subreddits", _DEFAULT_SUBREDDITS
        )
        self.keywords: list[str] = config.get("keywords", [])
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._nlp = CitizenReportProcessor()
        self._access_token: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent},
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "RedditAdapter":
        await self._get_client()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def _authenticate(self) -> bool:
        """Obtain OAuth2 access token via client_credentials grant.

        Returns False if credentials missing or auth fails.
        """
        if not self.client_id or not self.client_secret:
            logger.warning("Reddit credentials missing, skipping auth")
            return False
        client = await self._get_client()
        try:
            resp = await client.post(
                _TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
            )
            if resp.status_code != 200:
                logger.warning("Reddit auth failed: %d", resp.status_code)
                return False
            self._access_token = resp.json().get("access_token")
            return self._access_token is not None
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Reddit auth error: %s", exc)
            return False

    def _matches_keywords(self, post: dict) -> bool:
        """Return True if post title/selftext contains any keyword."""
        if not self.keywords:
            return True
        text = (
            post.get("title", "") + " " + post.get("selftext", "")
        ).lower()
        return any(kw.lower() in text for kw in self.keywords)

    async def pull_observations(self) -> list[dict]:
        """Pull new posts from configured subreddits.

        Returns empty list if credentials missing or API error.
        """
        if not await self._authenticate():
            return []

        client = await self._get_client()
        headers = {"Authorization": f"Bearer {self._access_token}"}
        posts: list[dict] = []
        for subreddit in self.subreddits:
            url = f"{_BASE_URL}/r/{subreddit}/new"
            params = {"limit": 100, "sort": "new"}
            try:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code != 200:
                    logger.warning(
                        "Reddit r/%s returned %d", subreddit, resp.status_code
                    )
                    continue
                children = resp.json().get("data", {}).get("children", [])
                for child in children:
                    post = child.get("data", {})
                    if self._matches_keywords(post):
                        posts.append(post)
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                logger.warning("Reddit r/%s error: %s", subreddit, exc)
                continue
        return posts

    def map_to_observation(
        self, post: dict, org_id: str, incident_id: str,
    ) -> dict:
        """Map a Reddit post to an observation dict with NLP processing."""
        title = post.get("title", "")
        body = post.get("selftext", "")
        text = f"{title}. {body}".strip() if body else title
        report = self._nlp.process_report(text=text)

        observed_at = int(post.get("created_utc", 0)) * 1000 or now_ms()
        post_id = post.get("id", generate_ulid())
        source_id = f"reddit:{post_id}"

        raw = json.dumps(
            post, sort_keys=True, default=str, separators=(",", ":"),
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
            "source_type": SourceType.social_media.value,
            "collection_method": "reddit_api",
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
                "platform": "reddit",
                "subreddit": post.get("subreddit", ""),
                "score": post.get("score", 0),
            },
            "access_policy": AccessPolicy.sensitive.value,
            "provenance_chain": {
                "platform": "reddit",
                "post_id": post_id,
                "author": post.get("author", ""),
                "permalink": post.get("permalink", ""),
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
        """Pull posts, process through NLP, dedup, publish to Kafka.

        Returns the number of new observations published.
        """
        posts = await self.pull_observations()
        if not posts:
            return 0

        count = 0
        for post in posts:
            post_id = post.get("id")
            if not post_id:
                continue
            if not check_and_record(db, "reddit", post_id):
                continue
            obs = self.map_to_observation(post, org_id, incident_id)
            await producer.send("observations.raw", obs)
            count += 1

        logger.info("Reddit: published %d/%d posts", count, len(posts))
        return count


__all__ = ["RedditAdapter"]
