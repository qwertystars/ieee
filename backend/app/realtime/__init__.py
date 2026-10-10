"""Realtime module — WebSocket manager and polling fallback router."""
import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from app.realtime.manager import WebSocketManager, manager, router

logger = logging.getLogger("app.realtime")

__all__ = ["WebSocketManager", "manager", "router", "schedule_broadcast"]


def schedule_broadcast(coro: Coroutine[Any, Any, None], app: Any) -> None:
    """Schedule a broadcast coroutine on the main event loop (fire-and-forget).

    Safe to call from sync route handlers running in a thread pool. Silently
    skips if the event loop is not available (e.g., in tests without lifespan).
    """
    try:
        loop = app.state.event_loop
        asyncio.run_coroutine_threadsafe(coro, loop)
    except AttributeError:
        logger.debug("event_loop not set on app.state; skipping broadcast")
    except Exception as exc:
        logger.warning("broadcast schedule failed: %s", exc)
