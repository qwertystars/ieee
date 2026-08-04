"""Tests for social media ingestion adapters (Twitter, Reddit, Instagram, YouTube).

Tests per adapter:
- pull_observations returns items from mock HTTP response
- map_to_observation produces correct observation dict (sensitive, social_media)
- missing credentials -> empty list (graceful degradation, no crash)
- PII in text is redacted before storage in quality_flags.text

API route test:
- POST /api/incidents/{id}/ingest/social-media?source_type=X returns 202 after
  durable publish succeeds
- Invalid source_type returns 422
"""

import asyncio
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ingestion.adapters.instagram import InstagramAdapter
from app.ingestion.adapters.reddit import RedditAdapter
from app.ingestion.adapters.twitter import TwitterAdapter
from app.ingestion.adapters.youtube import YouTubeAdapter

_PII_TEXT = (
    "flood water rising rapidly near downtown. "
    "call +91-9876543210 or email john@example.com for help"
)


# ── Fixture builders ─────────────────────────────────────────────────────────


def _make_tweet(tid: str = "tw_001", text: str = "Flood on Main Street, need help") -> dict:
    return {"id": tid, "text": text, "created_at": "2026-07-26T10:00:00Z",
            "author_id": "user_123", "geo": {}}


def _make_reddit_post(pid: str = "rp_001", title: str = "Flood hits Rivertown",
                     body: str = "Water rising fast") -> dict:
    return {"id": pid, "title": title, "selftext": body,
            "created_utc": 1782000000, "author": "user_reddit",
            "subreddit": "flooding", "score": 42,
            "permalink": "/r/flooding/comments/rp_001"}


def _make_instagram_media(mid: str = "ig_001",
                         caption: str = "Flood scene at downtown") -> dict:
    return {"id": mid, "caption": caption,
            "timestamp": "2026-07-26T10:00:00Z",
            "permalink": "https://instagram.com/p/ig_001",
            "media_type": "IMAGE", "media_url": "https://example.org/img.jpg"}


def _make_youtube_video(vid: str = "yt_001", title: str = "Flood rescue ops",
                        description: str = "Live footage from downtown") -> dict:
    return {"id": {"videoId": vid},
            "snippet": {"title": title, "description": description,
                        "publishedAt": "2026-07-26T10:00:00Z",
                        "channelId": "ch_123", "channelTitle": "NewsChannel"}}


# ── Shared assertions ─────────────────────────────────────────────────────────


def _assert_common_obs(obs: dict, source_prefix: str, method: str,
                       platform: str) -> None:
    assert obs["event_type"] == "social_media_post"
    assert obs["source_type"] == "social_media"
    assert obs["collection_method"] == method
    assert obs["org_id"] == "org_1"
    assert obs["incident_id"] == "inc_1"
    assert obs["corroboration_state"] == "uncorroborated"
    assert obs["access_policy"] == "sensitive"
    assert obs["raw_data_hash"].startswith("sha256:")
    assert obs["source_id"].startswith(source_prefix)
    assert obs["quality_flags"]["platform"] == platform


def _assert_pii_redacted(stored_text: str) -> None:
    assert "+91-9876543210" not in stored_text
    assert "john@example.com" not in stored_text
    assert "[PHONE]" in stored_text
    assert "[EMAIL]" in stored_text
    assert "flood" in stored_text.lower()


# ── Twitter ──────────────────────────────────────────────────────────────────


def test_twitter_pull_returns_observations() -> None:
    async def _test() -> None:
        tweet = _make_tweet()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [tweet], "meta": {}})

        adapter = TwitterAdapter({"bearer_token": "tok"})
        adapter._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0,
            headers={"Authorization": "Bearer tok"},
        )
        try:
            tweets = await adapter.pull_observations()
            assert len(tweets) == 1
            assert tweets[0]["id"] == "tw_001"
            obs = adapter.map_to_observation(tweets[0], "org_1", "inc_1")
            _assert_common_obs(obs, "twitter:", "twitter_api_v2", "twitter")
        finally:
            await adapter.close()

    asyncio.run(_test())


def test_twitter_missing_credentials_returns_empty() -> None:
    async def _test() -> None:
        adapter = TwitterAdapter({})
        assert await adapter.pull_observations() == []
        await adapter.close()

    asyncio.run(_test())


def test_twitter_pii_redacted() -> None:
    tweet = _make_tweet(text=_PII_TEXT)
    adapter = TwitterAdapter({"bearer_token": "tok"})
    obs = adapter.map_to_observation(tweet, "org_1", "inc_1")
    _assert_pii_redacted(obs["quality_flags"]["text"])


# ── Reddit ───────────────────────────────────────────────────────────────────


def test_reddit_pull_returns_observations() -> None:
    async def _test() -> None:
        post = _make_reddit_post()

        def handler(request: httpx.Request) -> httpx.Response:
            if "access_token" in str(request.url):
                return httpx.Response(200, json={"access_token": "tok_123"})
            return httpx.Response(
                200, json={"data": {"children": [{"data": post}]}}
            )

        adapter = RedditAdapter({
            "client_id": "cid", "client_secret": "csec",
            "subreddits": ["flooding"],
        })
        adapter._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0,
            headers={"User-Agent": "ResQNet-SAGE/1.0"},
        )
        try:
            posts = await adapter.pull_observations()
            assert len(posts) == 1
            assert posts[0]["id"] == "rp_001"
            obs = adapter.map_to_observation(posts[0], "org_1", "inc_1")
            _assert_common_obs(obs, "reddit:", "reddit_api", "reddit")
        finally:
            await adapter.close()

    asyncio.run(_test())


def test_reddit_missing_credentials_returns_empty() -> None:
    async def _test() -> None:
        adapter = RedditAdapter({})
        assert await adapter.pull_observations() == []
        await adapter.close()

    asyncio.run(_test())


def test_reddit_pii_redacted() -> None:
    post = _make_reddit_post(title=_PII_TEXT, body="")
    adapter = RedditAdapter({"client_id": "cid", "client_secret": "csec"})
    obs = adapter.map_to_observation(post, "org_1", "inc_1")
    _assert_pii_redacted(obs["quality_flags"]["text"])


# ── Instagram ─────────────────────────────────────────────────────────────────


def test_instagram_pull_returns_observations() -> None:
    async def _test() -> None:
        media = _make_instagram_media()

        def handler(request: httpx.Request) -> httpx.Response:
            if "ig_hashtag_search" in str(request.url):
                return httpx.Response(200, json={"data": [{"id": "ht_001"}]})
            return httpx.Response(200, json={"data": [media]})

        adapter = InstagramAdapter(
            {"access_token": "tok", "user_id": "uid", "hashtags": ["flood"]}
        )
        adapter._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0,
        )
        try:
            media_list = await adapter.pull_observations()
            assert len(media_list) == 1
            assert media_list[0]["id"] == "ig_001"
            obs = adapter.map_to_observation(media_list[0], "org_1", "inc_1")
            _assert_common_obs(obs, "instagram:", "instagram_graph_api", "instagram")
        finally:
            await adapter.close()

    asyncio.run(_test())


def test_instagram_missing_credentials_returns_empty() -> None:
    async def _test() -> None:
        adapter = InstagramAdapter({})
        assert await adapter.pull_observations() == []
        await adapter.close()

    asyncio.run(_test())


def test_instagram_pii_redacted() -> None:
    media = _make_instagram_media(caption=_PII_TEXT)
    adapter = InstagramAdapter({"access_token": "tok", "user_id": "uid"})
    obs = adapter.map_to_observation(media, "org_1", "inc_1")
    _assert_pii_redacted(obs["quality_flags"]["text"])


# ── YouTube ───────────────────────────────────────────────────────────────────


def test_youtube_pull_returns_observations() -> None:
    async def _test() -> None:
        video = _make_youtube_video()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"items": [video]})

        adapter = YouTubeAdapter({"api_key": "key", "keywords": ["flood"]})
        adapter._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=5.0,
        )
        try:
            videos = await adapter.pull_observations()
            assert len(videos) == 1
            assert videos[0]["id"]["videoId"] == "yt_001"
            obs = adapter.map_to_observation(videos[0], "org_1", "inc_1")
            _assert_common_obs(obs, "youtube:", "youtube_data_api_v3", "youtube")
        finally:
            await adapter.close()

    asyncio.run(_test())


def test_youtube_missing_credentials_returns_empty() -> None:
    async def _test() -> None:
        adapter = YouTubeAdapter({})
        assert await adapter.pull_observations() == []
        await adapter.close()

    asyncio.run(_test())


def test_youtube_pii_redacted() -> None:
    video = _make_youtube_video(title=_PII_TEXT, description="")
    adapter = YouTubeAdapter({"api_key": "key"})
    obs = adapter.map_to_observation(video, "org_1", "inc_1")
    _assert_pii_redacted(obs["quality_flags"]["text"])


# ── API route ─────────────────────────────────────────────────────────────────

_PASSWORD = "demo1234"
_ADMIN_EMAIL = "admin@demo.disaster"


def _login(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/auth/login", data={"username": email, "password": _PASSWORD},
    )
    assert resp.status_code == 200, f"login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_incident(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/incidents",
        json={"title": "Social Media Ingest Test", "disaster_type": "flood"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture(scope="module", autouse=True)
def _seed_users() -> Any:
    from app.auth.seed import seed_demo_users
    from app.db import SessionLocal

    db = SessionLocal()
    seed_demo_users(db)
    db.close()
    yield


@pytest.mark.parametrize("source_type", ["twitter", "reddit", "instagram", "youtube"])
def test_ingest_route_returns_202_after_durable_publish(
    source_type: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import ingest
    from app.main import app

    async def fake_run_ingestion(
        adapter_cls: type,
        config: dict[str, Any],
        org_id: str,
        incident_id: str,
    ) -> int:
        return 0

    monkeypatch.setattr(ingest, "_run_ingestion", fake_run_ingestion)

    with TestClient(app) as client:
        token = _login(client, _ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.post(
            f"/api/incidents/{inc_id}/ingest/social-media",
            params={"source_type": source_type},
            headers=_auth_header(token),
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["source_type"] == source_type
        assert body["incident_id"] == inc_id


def test_ingest_route_rejects_invalid_source_type() -> None:
    """Invalid source_type returns 422."""
    from app.main import app

    with TestClient(app) as client:
        token = _login(client, _ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.post(
            f"/api/incidents/{inc_id}/ingest/social-media",
            params={"source_type": "tiktok"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 422
