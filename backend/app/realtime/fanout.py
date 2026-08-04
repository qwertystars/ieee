from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import anyio
import redis.asyncio as redis_async
from redis.exceptions import RedisError

from app.config import settings
from app.deps import get_redis

logger = logging.getLogger(__name__)


class RedisFanout:
    """Redis Pub/Sub transport for cross-instance realtime envelopes."""

    def __init__(self, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self._handler = handler

    async def publish(self, envelope: dict[str, Any]) -> None:
        try:
            await anyio.to_thread.run_sync(self._publish_sync, envelope)
        except (OSError, RedisError, RuntimeError, TimeoutError):
            logger.warning("realtime fanout unavailable; local delivery only")

    async def subscribe(self) -> None:
        while True:
            client = redis_async.from_url(
                settings.REDIS_URL,
                socket_connect_timeout=1,
                socket_timeout=1,
                decode_responses=True,
            )
            pubsub = client.pubsub()
            try:
                await pubsub.subscribe(settings.REALTIME_FANOUT_CHANNEL)
                while True:
                    event = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1,
                    )
                    if event is None:
                        continue
                    data = event.get("data")
                    if not isinstance(data, str):
                        continue
                    try:
                        envelope = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(envelope, dict):
                        await self._handler(envelope)
            except (OSError, RedisError, TimeoutError):
                await anyio.sleep(1)
            finally:
                await pubsub.aclose()
                await client.aclose()

    @staticmethod
    def _publish_sync(envelope: dict[str, Any]) -> None:
        client = get_redis()
        if client is None:
            return
        client.publish(
            settings.REALTIME_FANOUT_CHANNEL,
            json.dumps(envelope, separators=(",", ":")),
        )
