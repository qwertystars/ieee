"""tasks routes stub (DESIGN §8). Feature workers fill endpoints here.

Exposes `router` aggregated by app/api/router.py and mounted under /api by main.py.
Do NOT edit main.py or api/router.py to add endpoints — add them to this router.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.demo_data import BASE_TASKS, now_iso, require_event

router = APIRouter(tags=["tasks"])


@router.get("/events/{event_id}/tasks")
def list_tasks(event_id: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    require_event(event_id)
    return deepcopy(BASE_TASKS[offset : offset + limit])


@router.post("/events/{event_id}/tasks", status_code=201)
def create_task(event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    require_event(event_id)
    timestamp = now_iso()
    task: dict[str, Any] = {
        "id": f"99000000-0000-4000-8000-{len(BASE_TASKS) + 1:012d}",
        "event_id": event_id,
        "recommendation_id": payload.get("recommendation_id"),
        "assigned_team_id": payload.get("assigned_team_id"),
        "title": payload.get("title"),
        "description": payload.get("description"),
        "location": payload.get("location"),
        "priority": payload.get("priority", "medium"),
        "status": payload.get("status", "assigned"),
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    BASE_TASKS.append(task)
    return deepcopy(task)


@router.patch("/tasks/{task_id}")
def update_task(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    for task in BASE_TASKS:
        if task["id"] == task_id:
            if "status" in payload:
                task["status"] = payload["status"]
            if "assigned_team_id" in payload:
                task["assigned_team_id"] = payload["assigned_team_id"]
            task["updated_at"] = now_iso()
            return deepcopy(task)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
