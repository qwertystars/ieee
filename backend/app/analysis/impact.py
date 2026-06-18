"""Impact estimation (DESIGN §6). Stub; Task #5 implements real estimation.

``estimate_impact(db, event_id, hazard_geom) -> ImpactDict``
"""
from __future__ import annotations

import uuid
from typing import Any, TypedDict

from sqlalchemy.orm import Session


class ImpactDict(TypedDict, total=False):
    population: int
    buildings: int
    schools: int
    hospitals: int
    shelters: int
    road_length_m: float


def estimate_impact(db: Session, event_id: uuid.UUID, hazard_geom: Any) -> ImpactDict:
    """Estimate exposure under a hazard geometry. Stub: zeroed dict."""
    return {
        "population": 0,
        "buildings": 0,
        "schools": 0,
        "hospitals": 0,
        "shelters": 0,
        "road_length_m": 0.0,
    }
