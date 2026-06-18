"""Confidence scoring (DESIGN §6). Stubs; Task #4 implements corroboration logic."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session


def initial_confidence(reporter_or_source_type: str) -> float:
    """Baseline confidence (0..1) for a new observation/report. Stub: 0.5."""
    return 0.5


def adjust_confidence(db: Session, obs: Any) -> float:
    """Adjust confidence using corroboration, age decay, conflict. Stub: passthrough."""
    return float(getattr(obs, "confidence_score", None) or 0.5)
