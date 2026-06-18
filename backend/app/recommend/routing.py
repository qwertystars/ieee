"""Safe routing (DESIGN §6). Stub; Task #6 implements NetworkX Dijkstra.

``safe_route(db, event_id, start, dest) -> RouteDict`` — avoids blocked/dangerous roads.
``start``/``dest`` are (lon, lat) tuples or GeoJSON Point dicts.
"""
from __future__ import annotations

import uuid
from typing import Any, TypedDict

from sqlalchemy.orm import Session


class RouteDict(TypedDict, total=False):
    found: bool
    distance_m: float
    geometry: dict[str, Any] | None
    avoided: list[str]
    reason: str


def safe_route(db: Session, event_id: uuid.UUID, start: Any, dest: Any) -> RouteDict:
    """Compute a hazard-avoiding route. Stub: not found, empty geometry."""
    return {
        "found": False,
        "distance_m": 0.0,
        "geometry": None,
        "avoided": [],
        "reason": "routing not yet implemented",
    }
