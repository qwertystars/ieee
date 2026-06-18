from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.demo_data import (
    RECOMMENDATIONS,
    approve_recommendation,
    dismiss_recommendation,
    require_event,
)

router = APIRouter(tags=["recommendations"])


@router.get("/events/{event_id}/recommendations")
def list_recommendations(event_id: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    require_event(event_id)
    return RECOMMENDATIONS[offset : offset + limit]


@router.post("/events/{event_id}/recommendations/{recommendation_id}/approve")
def approve(event_id: str, recommendation_id: str) -> dict[str, Any]:
    require_event(event_id)
    return approve_recommendation(recommendation_id)


@router.post("/events/{event_id}/recommendations/{recommendation_id}/dismiss")
def dismiss(event_id: str, recommendation_id: str) -> dict[str, Any]:
    require_event(event_id)
    return dismiss_recommendation(recommendation_id)
