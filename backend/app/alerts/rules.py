"""Alert rules (DESIGN §6 / §8). Stub; Task #8 implements alert evaluation.

``evaluate_alerts(db, event_id) -> list[Alert]``
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.audit import Alert


def evaluate_alerts(db: Session, event_id: uuid.UUID) -> list[Alert]:
    """Evaluate alert conditions for an event. Stub: returns []."""
    return []
