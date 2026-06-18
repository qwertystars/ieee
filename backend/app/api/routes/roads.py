"""roads routes stub (DESIGN §8). Feature workers fill endpoints here.

Exposes `router` aggregated by app/api/router.py and mounted under /api by main.py.
Do NOT edit main.py or api/router.py to add endpoints — add them to this router.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.demo_data import BASE_ROADS, now_iso, require_event

router = APIRouter(tags=["roads"])


@router.get("/events/{event_id}/roads/status")
def list_roads(event_id: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    require_event(event_id)
    return deepcopy(BASE_ROADS[offset : offset + limit])


@router.patch("/roads/{road_id}/status")
def update_road_status(road_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    next_status = payload.get("status")
    if not isinstance(next_status, str):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="status is required")
    for road in BASE_ROADS:
        if road["id"] == road_id:
            road["status"] = next_status
            if "reason" in payload:
                road["reason"] = payload["reason"]
            if "confidence_score" in payload:
                road["confidence_score"] = payload["confidence_score"]
            road["updated_at"] = now_iso()
            return deepcopy(road)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Road not found")
