"""Ingestion pipeline orchestration (DESIGN §6).

Frozen signatures:
    ingest_record(db, source_id, event_id, raw_payload) -> RawIngestedRecord
    process_record(db, raw) -> list[NormalizedObservation]   # normalize→dedup→verify→store
    run_source(db, source_id) -> int                          # pull+process; returns #obs

Stub implementations persist the raw record but do not yet derive observations.
Task #4 fills in process_record/run_source using normalize/dedup/verify.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.datasource import RawIngestedRecord
from app.models.observation import NormalizedObservation


def ingest_record(
    db: Session,
    source_id: uuid.UUID | None,
    event_id: uuid.UUID | None,
    raw_payload: dict[str, Any],
) -> RawIngestedRecord:
    """Persist a raw incoming payload for later processing."""
    record = RawIngestedRecord(
        source_id=source_id,
        event_id=event_id,
        raw_payload=raw_payload,
    )
    db.add(record)
    db.flush()
    return record


def process_record(db: Session, raw: RawIngestedRecord) -> list[NormalizedObservation]:
    """Normalize → dedup → verify → store. Stub: returns [] (no-op)."""
    return []


def run_source(db: Session, source_id: uuid.UUID) -> int:
    """Pull from a source and process all records. Stub: returns 0 observations."""
    return 0
