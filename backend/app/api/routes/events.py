from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.demo_data import BASE_EVENT, require_event

router = APIRouter(tags=["events"])


@router.get("/events")
def list_events(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    events = [BASE_EVENT]
    return events[offset : offset + limit]


@router.get("/events/{event_id}")
def get_event(event_id: str) -> dict[str, Any]:
    require_event(event_id)
    return BASE_EVENT
