"""Shelter allocation (DESIGN §6). Stub; Task #6 implements allocation.

``allocate_shelters(db, event_id, evac_area, people) -> AllocationDict``
"""
from __future__ import annotations

import uuid
from typing import Any, TypedDict

from sqlalchemy.orm import Session


class AllocationDict(TypedDict, total=False):
    total_people: int
    allocations: list[dict[str, Any]]
    unmet: int


def allocate_shelters(
    db: Session, event_id: uuid.UUID, evac_area: Any, people: int
) -> AllocationDict:
    """Allocate evacuees to shelters by capacity/proximity. Stub: all unmet."""
    return {"total_people": people, "allocations": [], "unmet": people}
