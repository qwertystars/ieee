"""Tests for the Ayrshare outbound adapter.

Tests:
- test_post_alert: mock POST /api/post, verify broadcast to 13 networks
- test_post_comment: mock POST /api/comments, verify community engagement
- test_get_analytics: mock GET /api/analytics/{id}, verify metrics retrieval
- test_missing_api_key: graceful degradation when api_key missing
- test_api_error: graceful handling on HTTP error
- test_build_alert_payload: verify alert dict -> post payload formatting
"""

import asyncio
from typing import Any

import httpx

from app.ingestion.adapters.ayrshare import AyrshareClient


def _make_alert(
    alert_id: str = "01HXXXXXXXXXXXXXXXXXXXXXX",
    severity: str = "severe",
    title: str = "Flood Warning",
    message: str = "Heavy rainfall expected. Move to higher ground.",
    recommended_action: str = "Evacuate low-lying areas.",
) -> dict[str, Any]:
    """Build a minimal approved Alert dict."""
    return {
        "id": alert_id,
        "severity": severity,
        "title": title,
        "message": message,
        "recommended_action": recommended_action,
    }


def test_post_alert():
    """Mock POST /api/post, verify broadcast to 13 networks."""

    async def _test():
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["headers"] = dict(request.headers)
            captured["json"] = request.read().decode()
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "id": "post_123",
                    "post": "Flood Warning",
                    "platforms": ["twitter", "facebook"],
                },
            )

        client = AyrshareClient({"api_key": "test_token"})
        # Headers must match what _get_client() would set
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=5.0,
            headers={"Authorization": "Bearer test_token"},
        )
        try:
            result = await client.post_alert(
                "Flood Warning: evacuate now", title="Emergency Alert",
            )
            assert result["status"] == "success"
            assert result["id"] == "post_123"
            # Verify Bearer token header was sent
            assert captured["headers"]["authorization"] == "Bearer test_token"
            # Verify URL
            assert "/api/post" in captured["url"]
        finally:
            await client.close()

    asyncio.run(_test())


def test_post_comment():
    """Mock POST /api/comments, verify community engagement."""

    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"status": "success", "id": "comment_456"},
            )

        client = AyrshareClient({"api_key": "test_token"})
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0,
        )
        try:
            result = await client.post_comment(
                "post_123", "Shelter open at Main Street School",
            )
            assert result["status"] == "success"
            assert result["id"] == "comment_456"
        finally:
            await client.close()

    asyncio.run(_test())


def test_get_analytics():
    """Mock GET /api/analytics/{id}, verify metrics retrieval."""

    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "post_123",
                    "metrics": {
                        "twitter": {"likes": 50, "retweets": 20},
                        "facebook": {"likes": 100, "comments": 15},
                    },
                },
            )

        client = AyrshareClient({"api_key": "test_token"})
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0,
        )
        try:
            result = await client.get_analytics("post_123")
            assert result["id"] == "post_123"
            assert result["metrics"]["twitter"]["likes"] == 50
            assert result["metrics"]["facebook"]["likes"] == 100
        finally:
            await client.close()

    asyncio.run(_test())


def test_missing_api_key():
    """Graceful degradation when api_key missing."""

    async def _test():
        client = AyrshareClient({})

        # post_alert returns skipped descriptor
        result = await client.post_alert("test")
        assert result["status"] == "skipped"
        assert result["reason"] == "api_key_missing"

        # post_comment returns skipped descriptor
        result = await client.post_comment("post_1", "test")
        assert result["status"] == "skipped"

        # get_analytics returns skipped descriptor
        result = await client.get_analytics("post_1")
        assert result["status"] == "skipped"

        await client.close()

    asyncio.run(_test())


def test_api_error():
    """Graceful handling on HTTP error (returns error descriptor)."""

    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Internal Server Error")

        client = AyrshareClient({"api_key": "test_token"})
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0,
        )
        try:
            result = await client.post_alert("test message")
            assert result["status"] == "error"
            assert result["code"] == 500

            result = await client.post_comment("post_1", "comment")
            assert result["status"] == "error"

            result = await client.get_analytics("post_1")
            assert result["status"] == "error"
        finally:
            await client.close()

    asyncio.run(_test())


def test_build_alert_payload():
    """Verify alert dict -> Ayrshare post payload formatting."""
    client = AyrshareClient({"api_key": "k"})
    alert = _make_alert()
    payload = client.build_alert_payload(alert, area_desc="Rivertown downtown")

    assert "[SEVERE]" in payload["post"]
    assert "Flood Warning" in payload["post"]
    assert "Rivertown downtown" in payload["post"]
    assert "Evacuate low-lying areas." in payload["post"]
    assert payload["title"] == "Flood Warning"
    assert "twitter" in payload["platforms"]
    assert len(payload["platforms"]) == 13
    assert payload["alert_id"] == alert["id"]
    assert payload["alert_hash"].startswith("sha256:")
