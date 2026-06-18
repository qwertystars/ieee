"""WebSocket connection manager (DESIGN §6).

Provides ``ConnectionManager`` with ``connect/disconnect/broadcast(event_id, message)``
and a module-level singleton ``manager``. Per-event connection registries so a
broadcast only reaches subscribers of that event.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    @staticmethod
    def _key(event_id: uuid.UUID | str) -> str:
        return str(event_id)

    async def connect(self, event_id: uuid.UUID | str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[self._key(event_id)].add(websocket)

    def disconnect(self, event_id: uuid.UUID | str, websocket: WebSocket) -> None:
        conns = self._connections.get(self._key(event_id))
        if conns:
            conns.discard(websocket)
            if not conns:
                self._connections.pop(self._key(event_id), None)

    async def broadcast(self, event_id: uuid.UUID | str, message: Any) -> None:
        """Send a JSON-serializable message to all subscribers of an event."""
        conns = list(self._connections.get(self._key(event_id), set()))
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(event_id, ws)


# Singleton used across the app (DESIGN §6).
manager = ConnectionManager()
