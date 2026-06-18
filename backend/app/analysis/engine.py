"""Assessment engine (DESIGN §6). Stub; Task #5 implements recompute.

``recompute_assessments(db, event_id) -> list[AreaAssessment]``
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.assessment import AreaAssessment


def recompute_assessments(db: Session, event_id: uuid.UUID) -> list[AreaAssessment]:
    """Recompute all area assessments for an event. Stub: returns []."""
    return []
