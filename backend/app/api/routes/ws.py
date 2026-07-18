"""WebSocket routes — /ws/events/{incident_id} for real-time updates."""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("app.ws")

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/events/{incident_id}")
async def events_ws(websocket: WebSocket, incident_id: str) -> None:
    """WebSocket for real-time event updates scoped to an incident.

    Accepts the connection, sends a connected acknowledgment, then keeps
    the connection alive. Real Redpanda consumer fanout comes later.
    """
    await websocket.accept()
    await websocket.send_json(
        {"type": "connected", "incident_id": incident_id}
    )
    try:
        while True:
            # Keep connection alive — await client messages (ping/pong).
            # Real event fanout will push from the server side.
            data = await websocket.receive_text()
            # Echo back as a ping acknowledgment for now.
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for incident_id=%s", incident_id)
