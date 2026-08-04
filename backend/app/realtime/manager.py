from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import anyio
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.realtime.fanout import RedisFanout

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Connection:
    websocket: WebSocket
    role: str
    org_id: str | None = None


class WebSocketManager:
    """Process-local socket delivery backed by shared Redis fanout."""

    def __init__(
        self,
        publisher: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self._connections: dict[str, set[_Connection]] = defaultdict(set)
        self._lock = anyio.Lock()
        self._instance_id = uuid.uuid4().hex
        self._publisher = publisher
        self._fanout = RedisFanout(self.handle_shared_message)

    async def start(self, task_group: anyio.abc.TaskGroup) -> None:
        """Start the shared Redis subscriber for this backend instance."""
        self._publisher = self._fanout.publish
        task_group.start_soon(self._fanout.subscribe)

    async def connect(
        self,
        websocket: WebSocket,
        incident_id: str,
        role: str,
        org_id: str | None = None,
    ) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[incident_id].add(_Connection(websocket, role, org_id))
        logger.info("ws.connect", extra={"incident_id": incident_id})

    async def disconnect(self, websocket: WebSocket, incident_id: str) -> None:
        async with self._lock:
            connections = self._connections.get(incident_id)
            if connections is None:
                return
            removed = {
                connection
                for connection in connections
                if connection.websocket is websocket
            }
            connections.difference_update(removed)
            if not connections:
                self._connections.pop(incident_id, None)

    async def broadcast(
        self,
        incident_id: str,
        message: dict[str, Any],
        org_id: str | None = None,
    ) -> None:
        await self._broadcast_local(incident_id, message, org_id)
        if self._publisher is not None and org_id is not None:
            await self._publisher(
                {
                    "origin": self._instance_id,
                    "incident_id": incident_id,
                    "org_id": org_id,
                    "message": message,
                }
            )

    async def handle_shared_message(self, envelope: dict[str, Any]) -> None:
        origin = envelope.get("origin")
        if not isinstance(origin, str) or origin == self._instance_id:
            return
        incident_id = envelope.get("incident_id")
        message = envelope.get("message")
        org_id = envelope.get("org_id")
        if (
            not isinstance(incident_id, str)
            or not isinstance(org_id, str)
            or not isinstance(message, dict)
        ):
            return
        await self._broadcast_local(incident_id, message, org_id)

    async def _broadcast_local(
        self,
        incident_id: str,
        message: dict[str, Any],
        org_id: str | None,
    ) -> None:
        async with self._lock:
            connections = list(self._connections.get(incident_id, set()))
        dead: list[_Connection] = []
        for connection in connections:
            if org_id is not None and connection.org_id not in (None, org_id):
                continue
            filtered = _filter_message(message, connection.role)
            if filtered is None:
                continue
            try:
                await connection.websocket.send_json(filtered)
            except (OSError, RuntimeError, WebSocketDisconnect):
                dead.append(connection)
        if dead:
            async with self._lock:
                bucket = self._connections.get(incident_id)
                if bucket is not None:
                    bucket.difference_update(dead)
                    if not bucket:
                        self._connections.pop(incident_id, None)

    async def broadcast_observation(
        self,
        incident_id: str,
        observation: dict[str, Any],
        org_id: str | None = None,
    ) -> None:
        await self.broadcast(
            incident_id,
            {"type": "new_observation", "payload": observation},
            org_id,
        )

    async def broadcast_hypothesis(
        self,
        incident_id: str,
        hypothesis: dict[str, Any],
        org_id: str | None = None,
    ) -> None:
        await self.broadcast(
            incident_id,
            {"type": "hypothesis_changed", "payload": hypothesis},
            org_id,
        )

    async def broadcast_plan(
        self,
        incident_id: str,
        plan: dict[str, Any],
        org_id: str | None = None,
    ) -> None:
        await self.broadcast(
            incident_id,
            {"type": "plan_updated", "payload": plan},
            org_id,
        )

    def get_connection_count(self, incident_id: str) -> int:
        connections = self._connections.get(incident_id)
        if not connections:
            return 0
        closed = {
            connection
            for connection in connections
            if getattr(connection.websocket, "client_state", None)
            is WebSocketState.DISCONNECTED
            or getattr(connection.websocket, "application_state", None)
            is WebSocketState.DISCONNECTED
        }
        if closed:
            connections.difference_update(closed)
            if not connections:
                self._connections.pop(incident_id, None)
        return len(connections)


manager = WebSocketManager()

from app.realtime.routes import _filter_message, router

__all__ = ["WebSocketManager", "manager", "router"]
