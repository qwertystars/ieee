"""Realtime event emission (DESIGN §6 / §9).

``EventType`` holds the canonical event-type string constants. ``emit`` broadcasts
a typed payload to all subscribers of an event via the ConnectionManager singleton.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.realtime.manager import manager


class EventType:
    NEW_OBSERVATION = "new_observation"
    NEW_REPORT = "new_report"
    REPORT_VERIFIED = "report_verified"
    AREA_PRIORITY_CHANGED = "area_priority_changed"
    RECOMMENDATION_CREATED = "recommendation_created"
    RECOMMENDATION_APPROVED = "recommendation_approved"
    TASK_ASSIGNED = "task_assigned"
    TASK_STATUS_CHANGED = "task_status_changed"
    SHELTER_STATUS_CHANGED = "shelter_status_changed"
    ROAD_STATUS_CHANGED = "road_status_changed"
    TEAM_LOCATION_UPDATED = "team_location_updated"
    ALERT_CREATED = "alert_created"


async def emit(event_id: uuid.UUID | str, type: str, payload: Any) -> None:
    """Broadcast a realtime event to subscribers of ``event_id``."""
    message = {
        "type": type,
        "event_id": str(event_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    await manager.broadcast(event_id, message)
