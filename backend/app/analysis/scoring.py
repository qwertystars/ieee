"""Area scoring (DESIGN §6). Stub; Task #5 implements the 7-component model.

``score_area(db, event_id, area_geom) -> ScoreDict`` with 7 components + overall +
level + explanation. Scores 0..100; level is a PriorityLevel value.
"""
from __future__ import annotations

import uuid
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from app.models.enums import PriorityLevel


class ScoreDict(TypedDict, total=False):
    hazard_score: float
    exposure_score: float
    access_score: float
    infrastructure_score: float
    vulnerability_score: float
    trend_score: float
    report_score: float
    overall_priority_score: float
    priority_level: str
    components: dict[str, Any]
    summary: str


def score_area(db: Session, event_id: uuid.UUID, area_geom: Any) -> ScoreDict:
    """Compute component + overall scores for an area. Stub: zeros / unknown."""
    return {
        "hazard_score": 0.0,
        "exposure_score": 0.0,
        "access_score": 0.0,
        "infrastructure_score": 0.0,
        "vulnerability_score": 0.0,
        "trend_score": 0.0,
        "report_score": 0.0,
        "overall_priority_score": 0.0,
        "priority_level": PriorityLevel.unknown.value,
        "components": {},
        "summary": "",
    }
