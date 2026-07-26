"""WebSocket manager + polling fallback router for realtime incident updates.

Provides:
- WebSocketManager: in-memory pub/sub keyed by incident_id
- manager: module-level singleton
- router: FastAPI APIRouter with WS endpoint + GET polling fallback
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models.observation import Observation

logger = logging.getLogger(__name__)

router = APIRouter()


class WebSocketManager:
    """In-memory WebSocket connection registry keyed by incident_id.

    Connections are stored in a defaultdict(set). All mutation goes through
    an asyncio.Lock so concurrent connect/disconnect cannot corrupt state.
    """

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, incident_id: str) -> None:
        """Accept a WebSocket and register it under incident_id."""
        await websocket.accept()
        async with self._lock:
            self._connections[incident_id].add(websocket)
        logger.info(
            "ws.connect",
            extra={"incident_id": incident_id},
        )

    async def disconnect(self, websocket: WebSocket, incident_id: str) -> None:
        """Remove a WebSocket from the incident_id registry."""
        async with self._lock:
            conns = self._connections.get(incident_id)
            if conns is None:
                return
            conns.discard(websocket)
            if not conns:
                self._connections.pop(incident_id, None)

    async def broadcast(self, incident_id: str, message: dict[str, object]) -> None:
        """Send a JSON message to every connection for incident_id.

        Dead connections are removed after the send attempt.
        """
        async with self._lock:
            conns = list(self._connections.get(incident_id, set()))

        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                bucket = self._connections.get(incident_id)
                if bucket is not None:
                    for ws in dead:
                        bucket.discard(ws)
                    if not bucket:
                        self._connections.pop(incident_id, None)

    async def broadcast_observation(
        self, incident_id: str, observation: dict[str, object]
    ) -> None:
        await self.broadcast(
            incident_id,
            {"type": "new_observation", "payload": observation},
        )

    async def broadcast_hypothesis(
        self, incident_id: str, hypothesis: dict[str, object]
    ) -> None:
        await self.broadcast(
            incident_id,
            {"type": "hypothesis_changed", "payload": hypothesis},
        )

    async def broadcast_plan(
        self, incident_id: str, plan: dict[str, object]
    ) -> None:
        await self.broadcast(
            incident_id,
            {"type": "plan_updated", "payload": plan},
        )

    def get_connection_count(self, incident_id: str) -> int:
        """Return the number of live connections for incident_id."""
        return len(self._connections.get(incident_id, set()))


manager = WebSocketManager()


@router.websocket("/ws/realtime/{incident_id}")
async def realtime_ws(
    websocket: WebSocket,
    incident_id: str,
    token: str = Query(..., description="JWT Bearer token"),
) -> None:
    """WebSocket endpoint streaming realtime updates for one incident.

    Validates the JWT from the `token` query param before accepting the
    connection. Closes with code 4001 if the token is invalid or missing.
    """
    from app.auth.jwt import JWTError, decode_token

    try:
        decode_token(token)
    except JWTError:
        await websocket.close(code=4001)
        return

    await manager.connect(websocket, incident_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket, incident_id)


@router.get("/api/incidents/{incident_id}/updates")
def polling_updates(
    incident_id: str,
    since: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Polling fallback: return observations newer than `since` (epoch ms).

    Clients without WebSocket support poll this endpoint with their last
    `observed_at` watermark as `since`.
    """
    stmt = (
        select(Observation)
        .where(Observation.incident_id == incident_id)
        .where(Observation.observed_at > since)
        .order_by(Observation.observed_at.asc())
    )
    rows = db.execute(stmt).scalars().all()
    observations = [_serialize_observation(o) for o in rows]
    return {
        "incident_id": incident_id,
        "since": since,
        "count": len(observations),
        "observations": observations,
    }


def _serialize_observation(obs: Observation) -> dict[str, object]:
    """Project an Observation row into a JSON-safe dict for the polling API."""
    return {
        "observation_id": obs.observation_id,
        "incident_id": obs.incident_id,
        "event_type": obs.event_type,
        "phenomenon": obs.phenomenon,
        "value": obs.value,
        "unit": obs.unit,
        "observed_at": obs.observed_at,
        "received_at": obs.received_at,
        "source_id": obs.source_id,
        "source_type": obs.source_type.value if obs.source_type else None,
        "corroboration_state": (
            obs.corroboration_state.value if obs.corroboration_state else None
        ),
        "access_policy": (
            obs.access_policy.value if obs.access_policy else None
        ),
    }
