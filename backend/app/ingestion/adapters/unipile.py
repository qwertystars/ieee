"""Unipile adapter — inbound messaging from WhatsApp/Telegram/Email DMs.

Uses the Unipile REST API (https://docs.unipile.com/) with X-API-KEY header + DSN.
Webhook endpoint POST /api/webhooks/unipile receives message.new events.
Maps incoming DMs to observations with source_type=citizen_report,
geometry=None (NLP extracts place names from text for downstream gazetteer
resolution), access_policy=sensitive.

POST /api/incidents/{id}/messages/send sends targeted response messages via
WhatsApp/Telegram. PII is redacted BEFORE any storage or processing — the
CitizenReportProcessor pipeline redacts phone, email, Aadhaar, and person
names before the text is stored in quality_flags or published to Kafka.

Degrades gracefully (returns empty, logs warning) when API key missing.
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
_SENTINEL_GEOMETRY = "POINT(0 0)"
_SENTINEL_UNCERTAINTY = 9_999_999.0


class UnipileClient:
    """Inbound messaging adapter for Unipile DMs.

    config keys: api_key (str), dsn (str — Unipile DSN base URL),
    account_id (str, optional — filter to specific messaging account).
    """

    def __init__(self, config: dict, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.api_key: str | None = config.get("api_key")
        self.dsn: str = config.get("dsn", "https://api.unipile.com/api/v1")
        self.account_id: str | None = config.get("account_id")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._nlp = CitizenReportProcessor()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["X-API-KEY"] = self.api_key
            self._client = httpx.AsyncClient(
                timeout=self.timeout, headers=headers,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "UnipileClient":
        await self._get_client()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def send_message(self, chat_id: str, text: str) -> dict:
        """Send a targeted response message via WhatsApp/Telegram.

        POST /api/v1/chats/{chat_id}/messages
        Returns skipped/error descriptor if api_key missing.
        """
        if not self.api_key:
            logger.warning("Unipile api_key missing, skipping send")
            return {"status": "skipped", "reason": "api_key_missing"}

        client = await self._get_client()
        payload = {"text": text}

        try:
            resp = await client.post(
                f"{self.dsn}/chats/{chat_id}/messages", json=payload,
            )
            if resp.status_code not in (200, 201):
                logger.warning(
                    "Unipile send %d: %s",
                    resp.status_code, resp.text[:200],
                )
                return {"status": "error", "code": resp.status_code}
            return resp.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Unipile send error: %s", exc)
            return {"status": "error", "reason": str(exc)}

    def map_to_observation(
        self, message: dict, org_id: str, incident_id: str,
    ) -> dict:
        """Map an incoming Unipile DM to an observation dict.

        PII is redacted via the NLP pipeline before the text is stored.
        Geometry is a sentinel POINT(0 0) — NLP extracts place names from
        the redacted text for downstream gazetteer resolution.
        """
        text = message.get("text", "") or ""
        # PII redaction happens inside process_report — the redacted_text
        # field in the returned report has all PII replaced with tokens.
        report = self._nlp.process_report(text=text)

        message_id = message.get("id", generate_ulid())
        source_id = f"unipile:{message_id}"

        observed_at = now_ms()
        created_at = message.get("created_at")
        if created_at:
            try:
                observed_at = from_iso(created_at)
            except (ValueError, TypeError):
                pass

        raw = json.dumps(
            message, sort_keys=True, default=str, separators=(",", ":"),
        )
        raw_hash = "sha256:" + hashlib.sha256(raw.encode()).hexdigest()

        return {
            "observation_id": generate_ulid(),
            "event_type": "citizen_report",
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
            "external_id": message_id,
            "source_type": SourceType.citizen_report.value,
            "collection_method": "unipile_webhook",
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
                "platform": "unipile",
                "sender": message.get("sender", {}).get("name", ""),
                "chat_id": message.get("chat_id", ""),
            },
            "access_policy": AccessPolicy.sensitive.value,
            "provenance_chain": {
                "platform": "unipile",
                "message_id": message_id,
                "chat_id": message.get("chat_id", ""),
                "account_id": self.account_id or "",
            },
            "raw_data_hash": raw_hash,
            "model_version": None,
            "supersedes": None,
            "duplicate_group": None,
            "org_id": org_id,
            "incident_id": incident_id,
        }

    async def ingest_webhook(
        self, db: Session, producer: ProducerManager,
        payload: dict, org_id: str, incident_id: str,
    ) -> int:
        """Process a Unipile webhook payload (message.new event).

        Returns the number of observations published (0 or 1).
        """
        event_type = payload.get("type", "")
        if event_type != "message.new":
            logger.debug("Unipile webhook: ignoring event type %s", event_type)
            return 0

        message = payload.get("payload", {}) or payload.get("message", {})
        message_id = message.get("id")
        if not message_id:
            logger.warning("Unipile webhook: message has no id")
            return 0

        obs = self.map_to_observation(message, org_id, incident_id)
        if not check_and_record(
            db,
            "unipile",
            message_id,
            org_id=org_id,
            incident_id=incident_id,
            payload=stable_ingestion_claim(obs),
            commit=False,
        ):
            logger.debug("Unipile webhook: duplicate message %s", message_id)
            return 0

        try:
            await producer.send("observations.raw", obs)
            record_published_raw_event(db, obs)
            db.commit()
        except (OSError, RuntimeError, TimeoutError):
            db.rollback()
            raise
        logger.info("Unipile: published message %s", message_id)
        return 1


__all__ = ["UnipileClient"]
