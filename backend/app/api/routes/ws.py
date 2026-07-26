"""WebSocket routes — real WebSocket is in app.realtime.manager.router.

This file is kept for backward compatibility. The real WebSocket endpoint
(/ws/realtime/{incident_id} with JWT validation) and polling endpoint
(/api/incidents/{id}/updates) are registered via manager.router in main.py.
"""
from fastapi import APIRouter

router = APIRouter(tags=["websocket"])
