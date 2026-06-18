"""Recommendation rules (DESIGN §6). Stub; Task #6 implements rule engine.

``generate_recommendations(db, event_id) -> list[Recommendation]``
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.assessment import Recommendation


def generate_recommendations(db: Session, event_id: uuid.UUID) -> list[Recommendation]:
    """Generate recommendations from current assessments. Stub: returns []."""
    return []
