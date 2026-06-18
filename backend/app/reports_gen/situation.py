"""Situation report generation (DESIGN §6 / §8). Stub; Task #8 implements text+PDF.

``build_situation_report(db, event_id, fmt) -> bytes | str``
- fmt == "text" -> str
- fmt == "pdf"  -> bytes (reportlab)
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session


def build_situation_report(db: Session, event_id: uuid.UUID, fmt: str = "text") -> bytes | str:
    """Build a situation report. Stub: minimal placeholder text/bytes."""
    placeholder = f"Situation report for event {event_id} — not yet implemented."
    if fmt == "pdf":
        return placeholder.encode("utf-8")
    return placeholder
