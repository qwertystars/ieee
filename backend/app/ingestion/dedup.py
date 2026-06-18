"""Deduplication / clustering (DESIGN §6). Stub; Task #4 implements clustering."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session


def find_cluster(db: Session, obs: Any) -> uuid.UUID | None:
    """Find an existing cluster (distance+time+category+text). Stub: None (no match)."""
    return None
