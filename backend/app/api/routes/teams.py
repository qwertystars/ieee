"""teams routes stub (DESIGN §8). Feature workers fill endpoints here.

Exposes `router` aggregated by app/api/router.py and mounted under /api by main.py.
Do NOT edit main.py or api/router.py to add endpoints — add them to this router.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.demo_data import BASE_TEAMS, now_iso, require_event

router = APIRouter(tags=["teams"])


@router.get("/events/{event_id}/teams")
def list_teams(event_id: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    require_event(event_id)
    return deepcopy(BASE_TEAMS[offset : offset + limit])


@router.patch("/teams/{team_id}/location")
def update_team_location(team_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    location = payload.get("current_location")
    if location is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="current_location is required")
    for team in BASE_TEAMS:
        if team["id"] == team_id:
            team["current_location"] = location
            team["updated_at"] = now_iso()
            return deepcopy(team)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")


@router.patch("/teams/{team_id}/status")
def update_team_status(team_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    next_status = payload.get("status")
    if not isinstance(next_status, str):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="status is required")
    for team in BASE_TEAMS:
        if team["id"] == team_id:
            team["status"] = next_status
            team["updated_at"] = now_iso()
            return deepcopy(team)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
