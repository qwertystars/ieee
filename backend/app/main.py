"""FastAPI application entrypoint (DESIGN §2 boot contract).

Wires all routers, the ingestion router, the auth router, and the realtime
WebSocket. This file is owned by FOUNDATION and MUST NOT be edited by feature
workers — they add behavior inside their own route/engine modules.
"""
from __future__ import annotations

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.auth.router import router as auth_router
from app.config import settings
from app.ingestion.router import router as ingestion_router
from app.realtime.manager import manager

app = FastAPI(
    title="Disaster Situational Awareness & Response Platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All REST routes live under /api (DESIGN §8).
app.include_router(api_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(ingestion_router, prefix="/api")


@app.get("/healthz", tags=["health"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/events/{event_id}")
async def ws_events(websocket: WebSocket, event_id: str) -> None:
    """Realtime channel for an event (DESIGN §6 / §9)."""
    await manager.connect(event_id, websocket)
    try:
        while True:
            # Keep the connection open; inbound messages are ignored for now.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(event_id, websocket)
    except Exception:
        manager.disconnect(event_id, websocket)
