"""Dashboard aggregate schemas (DESIGN §5 / §8)."""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    """High-level operational summary for an event."""

    event_id: uuid.UUID | None = None
    event_name: str | None = None
    status: str | None = None
    total_reports: int = 0
    unverified_reports: int = 0
    total_observations: int = 0
    active_recommendations: int = 0
    open_tasks: int = 0
    blocked_roads: int = 0
    affected_population: int | None = None
    shelters_open: int = 0
    shelter_capacity_available: int = 0
    priority_breakdown: dict[str, int] = {}
    active_alerts: int = 0
    last_updated: str | None = None


class MapLayers(BaseModel):
    """GeoJSON FeatureCollections per map layer (DESIGN §11 / §20)."""

    hazard: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    areas: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    reports: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    observations: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    roads: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    shelters: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    hospitals: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    teams: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    tasks: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    alerts: dict[str, Any] = {"type": "FeatureCollection", "features": []}
