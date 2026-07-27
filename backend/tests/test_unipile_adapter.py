"""Tests for the Unipile inbound messaging adapter.

Tests:
- test_send_message: mock POST /api/v1/chats/{id}/messages, verify outbound send
- test_map_to_observation: verify DM -> observation dict mapping with PII redaction
- test_pii_redaction: verify PII is redacted before storage in quality_flags
- test_ingest_webhook: verify message.new webhook processing + dedup
- test_ingest_webhook_ignores_other_events: non-message.new events return 0
- test_missing_api_key: graceful degradation when api_key missing
- test_api_error: graceful handling on HTTP error
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx

from app.ingestion.adapters.unipile import UnipileClient


def _make_message(
    message_id: str = "msg_001",
    text: str = "Flood on Main Street, need help urgently",
    chat_id: str = "chat_abc",
    sender_name: str = "John Doe",
    created_at: str = "2026-07-26T10:00:00Z",
) -> dict[str, Any]:
    """Build a minimal Unipile message dict."""
    return {
        "id": message_id,
        "text": text,
        "chat_id": chat_id,
        "created_at": created_at,
        "sender": {"name": sender_name, "id": "user_123"},
    }


def _make_webhook_payload(message: dict) -> dict[str, Any]:
    """Build a Unipile webhook payload wrapping a message."""
    return {
        "type": "message.new",
        "payload": message,
    }


def test_send_message():
    """Mock POST /api/v1/chats/{id}/messages, verify outbound send."""

    async def _test():
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["headers"] = dict(request.headers)
            captured["body"] = request.read().decode()
            return httpx.Response(
                200, json={"status": "ok", "message_id": "out_001"},
            )

        client = UnipileClient({"api_key": "test_key", "dsn": "https://api.unipile.com/api/v1"})
        # Headers must match what _get_client() would set
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=5.0,
            headers={"X-API-KEY": "test_key"},
        )
        try:
            result = await client.send_message("chat_abc", "Help is on the way")
            assert result["status"] == "ok"
            assert result["message_id"] == "out_001"
            assert "chats/chat_abc/messages" in captured["url"]
            assert captured["headers"]["x-api-key"] == "test_key"
        finally:
            await client.close()

    asyncio.run(_test())


def test_map_to_observation():
    """Verify DM -> observation dict mapping."""
    msg = _make_message(text="Flood on Main Street, need help urgently")
    client = UnipileClient({"api_key": "k"})
    obs = client.map_to_observation(msg, "org_1", "inc_1")

    assert obs["event_type"] == "citizen_report"
    assert obs["source_type"] == "citizen_report"
    assert obs["collection_method"] == "unipile_webhook"
    assert obs["org_id"] == "org_1"
    assert obs["incident_id"] == "inc_1"
    assert obs["corroboration_state"] == "uncorroborated"
    assert obs["access_policy"] == "sensitive"
    assert obs["raw_data_hash"].startswith("sha256:")
    assert obs["source_id"] == "unipile:msg_001"
    assert obs["source_reliability"] == 0.5
    assert obs["freshness"] == 1.0
    assert obs["valid_from"] == obs["observed_at"]
    assert obs["valid_until"] is None
    assert obs["quality_flags"]["platform"] == "unipile"
    assert obs["quality_flags"]["chat_id"] == "chat_abc"
    assert obs["provenance_chain"]["message_id"] == "msg_001"
    assert obs["provenance_chain"]["chat_id"] == "chat_abc"
    # Geometry is sentinel — NLP extracts place names for downstream resolution
    assert "POINT(0 0)" in obs["geometry_wkt"]
    assert obs["geometry_uncertainty"] == 9_999_999.0


def test_pii_redaction():
    """Verify PII is redacted before storage in quality_flags.text."""
    # Message contains an Indian phone number and email (PHONE_RE matches +91 format)
    msg = _make_message(
        text="Call me at +91-9876543210 or email john@example.com — flood on Main St",
    )
    client = UnipileClient({"api_key": "k"})
    obs = client.map_to_observation(msg, "org_1", "inc_1")

    stored_text = obs["quality_flags"]["text"]
    # PII must be redacted — phone and email replaced with tokens
    assert "+91-9876543210" not in stored_text
    assert "john@example.com" not in stored_text
    assert "[PHONE]" in stored_text
    assert "[EMAIL]" in stored_text
    # Non-PII content preserved
    assert "flood" in stored_text.lower()


def test_ingest_webhook():
    """Verify message.new webhook processing + dedup + publish."""

    async def _test():
        msg = _make_message()
        payload = _make_webhook_payload(msg)

        client = UnipileClient({"api_key": "k"})

        db = MagicMock()
        producer = MagicMock()
        producer.send = AsyncMock()

        # Patch check_and_record to return True (first time)
        import app.ingestion.adapters.unipile as mod
        original = mod.check_and_record
        mod.check_and_record = lambda d, s, e: True
        try:
            count = await client.ingest_webhook(
                db, producer, payload, "org_1", "inc_1",
            )
            assert count == 1
            assert producer.send.call_count == 1
            call_args = producer.send.call_args_list[0]
            assert call_args.args[0] == "observations.raw"
            obs = call_args.args[1]
            assert obs["source_type"] == "citizen_report"
            assert obs["source_id"] == "unipile:msg_001"
            assert obs["access_policy"] == "sensitive"
        finally:
            mod.check_and_record = original
            await client.close()

    asyncio.run(_test())


def test_ingest_webhook_ignores_other_events():
    """Non-message.new events return 0 (no publish)."""

    async def _test():
        client = UnipileClient({"api_key": "k"})
        db = MagicMock()
        producer = MagicMock()
        producer.send = AsyncMock()

        count = await client.ingest_webhook(
            db, producer,
            {"type": "message.seen", "payload": {"id": "x"}},
            "org_1", "inc_1",
        )
        assert count == 0
        assert producer.send.call_count == 0
        await client.close()

    asyncio.run(_test())


def test_ingest_webhook_duplicate():
    """Duplicate message_id is deduped (check_and_record returns False)."""

    async def _test():
        msg = _make_message()
        payload = _make_webhook_payload(msg)

        client = UnipileClient({"api_key": "k"})
        db = MagicMock()
        producer = MagicMock()
        producer.send = AsyncMock()

        import app.ingestion.adapters.unipile as mod
        original = mod.check_and_record
        mod.check_and_record = lambda d, s, e: False  # Already seen
        try:
            count = await client.ingest_webhook(
                db, producer, payload, "org_1", "inc_1",
            )
            assert count == 0
            assert producer.send.call_count == 0
        finally:
            mod.check_and_record = original
            await client.close()

    asyncio.run(_test())


def test_missing_api_key():
    """Graceful degradation when api_key missing."""

    async def _test():
        client = UnipileClient({})

        result = await client.send_message("chat_1", "test")
        assert result["status"] == "skipped"
        assert result["reason"] == "api_key_missing"

        await client.close()

    asyncio.run(_test())


def test_api_error():
    """Graceful handling on HTTP error (returns error descriptor)."""

    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Internal Server Error")

        client = UnipileClient({"api_key": "test_key"})
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0,
        )
        try:
            result = await client.send_message("chat_1", "test")
            assert result["status"] == "error"
            assert result["code"] == 500
        finally:
            await client.close()

    asyncio.run(_test())
