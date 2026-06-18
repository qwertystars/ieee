from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.demo_data import BASE_ALERTS, dashboard_summary, map_layers, require_event

router = APIRouter(tags=["dashboard"])


@router.get("/events/{event_id}/dashboard-summary")
def get_dashboard_summary(event_id: str) -> dict[str, Any]:
    require_event(event_id)
    return dashboard_summary()


@router.get("/events/{event_id}/map-layers")
def get_map_layers(event_id: str, bbox: str | None = None) -> dict[str, Any]:
    require_event(event_id)
    return map_layers()


@router.get("/events/{event_id}/alerts")
def list_alerts(event_id: str) -> list[dict[str, Any]]:
    require_event(event_id)
    return BASE_ALERTS
