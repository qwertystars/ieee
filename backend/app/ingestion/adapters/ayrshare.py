"""Ayrshare adapter — broadcast emergency alerts to 13 social networks.

Uses the Ayrshare REST API (https://docs.ayrshare.com/) with Bearer token auth.
POST /api/post broadcasts to all connected social networks simultaneously.
POST /api/comments adds community engagement comments to existing posts.
GET /api/analytics/{id} retrieves engagement metrics for a posted alert.

Used by the alert workflow to broadcast approved alerts. The social-post-api
Python package is the canonical SDK; this adapter uses httpx directly to match
the codebase convention (all adapters use httpx, no SDKs).

Degrades gracefully (returns skipped/error descriptor, logs warning) when
API key missing. Never raises on credential or network failure.
"""

import hashlib
import json
import logging

import httpx

from app.lib.time import now_ms
from app.lib.ulid import generate_ulid

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
_BASE_URL = "https://app.ayrshare.com/api"

# The 13 social networks Ayrshare supports for simultaneous broadcast.
_DEFAULT_PLATFORMS = [
    "twitter", "facebook", "instagram", "linkedin", "youtube",
    "tiktok", "telegram", "reddit", "pinterest", "googlebusiness",
    "threads", "discord", "tumblr",
]


class AyrshareClient:
    """Outbound Ayrshare client for multi-network social broadcasting.

    config keys: api_key (str), platforms (list[str], optional subset).
    """

    def __init__(self, config: dict, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.api_key: str | None = config.get("api_key")
        self.platforms: list[str] = config.get("platforms", _DEFAULT_PLATFORMS)
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                timeout=self.timeout, headers=headers,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "AyrshareClient":
        await self._get_client()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    def _skipped(self, reason: str) -> dict:
        return {
            "status": "skipped",
            "reason": reason,
            "message_id": generate_ulid(),
            "sent_at": now_ms(),
        }

    async def post_alert(
        self, text: str, title: str | None = None,
    ) -> dict:
        """Broadcast an emergency alert to all configured social networks.

        Returns the Ayrshare API response dict, or a skipped/error descriptor.
        """
        if not self.api_key:
            logger.warning("Ayrshare api_key missing, skipping post")
            return self._skipped("api_key_missing")

        client = await self._get_client()
        payload: dict = {
            "post": text,
            "platforms": self.platforms,
        }
        if title:
            payload["title"] = title

        try:
            resp = await client.post(f"{_BASE_URL}/post", json=payload)
            if resp.status_code not in (200, 201):
                logger.warning(
                    "Ayrshare POST /api/post %d: %s",
                    resp.status_code, resp.text[:200],
                )
                return {
                    "status": "error",
                    "code": resp.status_code,
                    "message_id": generate_ulid(),
                    "sent_at": now_ms(),
                }
            return resp.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Ayrshare POST /api/post error: %s", exc)
            return {
                "status": "error",
                "reason": str(exc),
                "message_id": generate_ulid(),
                "sent_at": now_ms(),
            }

    async def post_comment(self, post_id: str, text: str) -> dict:
        """Add a community engagement comment to an existing post."""
        if not self.api_key:
            logger.warning("Ayrshare api_key missing, skipping comment")
            return self._skipped("api_key_missing")

        client = await self._get_client()
        payload = {"id": post_id, "comment": text}

        try:
            resp = await client.post(f"{_BASE_URL}/comments", json=payload)
            if resp.status_code not in (200, 201):
                logger.warning(
                    "Ayrshare POST /api/comments %d: %s",
                    resp.status_code, resp.text[:200],
                )
                return {"status": "error", "code": resp.status_code}
            return resp.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Ayrshare POST /api/comments error: %s", exc)
            return {"status": "error", "reason": str(exc)}

    async def get_analytics(self, post_id: str) -> dict:
        """Retrieve engagement metrics for a previously posted alert."""
        if not self.api_key:
            logger.warning("Ayrshare api_key missing, skipping analytics")
            return self._skipped("api_key_missing")

        client = await self._get_client()
        try:
            resp = await client.get(f"{_BASE_URL}/analytics/{post_id}")
            if resp.status_code != 200:
                logger.warning(
                    "Ayrshare GET /api/analytics/%s %d: %s",
                    post_id, resp.status_code, resp.text[:200],
                )
                return {"status": "error", "code": resp.status_code}
            return resp.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Ayrshare GET /api/analytics error: %s", exc)
            return {"status": "error", "reason": str(exc)}

    def build_alert_payload(
        self, alert: dict, area_desc: str | None = None,
    ) -> dict:
        """Build an Ayrshare post payload from an approved Alert dict.

        Produces a text-first alert suitable for simultaneous broadcast.
        The caller (alert workflow) passes an approved Alert serialized
        as a dict; this helper formats it for the /api/post endpoint.
        """
        severity = alert.get("severity", "unknown")
        title = alert.get("title", "Emergency Alert")
        message = alert.get("message", "")
        parts = [f"[{severity.upper()}] {title}"]
        if area_desc:
            parts.append(f"Area: {area_desc}")
        parts.append(message)
        recommended = alert.get("recommended_action")
        if recommended:
            parts.append(f"Action: {recommended}")
        text = "\n\n".join(parts)
        raw = json.dumps(alert, sort_keys=True, default=str, separators=(",", ":"))
        return {
            "post": text,
            "title": title,
            "platforms": self.platforms,
            "alert_id": alert.get("id", generate_ulid()),
            "alert_hash": "sha256:" + hashlib.sha256(raw.encode()).hexdigest(),
        }


__all__ = ["AyrshareClient"]
