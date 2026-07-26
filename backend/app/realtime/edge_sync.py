"""Edge-first sync — receives offline outbox items, deduplicates by content hash, applies in order.

Each edge node (field device) retains an append-only offline event queue (IndexedDB
outbox). When connectivity is restored, the node POSTs its outbox to /api/sync.
This module deduplicates by content hash (SHA-256 of payload), applies items in
sequence order, and tracks per-incident sync state.

Must NOT require internet for basic field operation — the client caches locally
and syncs when connected. This module is the server-side sync endpoint.
"""

from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import BigInteger, Integer, String, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column, Session

from app.db import Base
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid

logger = logging.getLogger(__name__)


class EdgeSyncApplied(Base):
    """Record of every applied outbox item — enforces cross-batch dedup by content_hash."""

    __tablename__ = "edge_sync_applied"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(String(26), unique=True, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    item_type: Mapped[str] = mapped_column(String)
    sequence: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB)
    org_id: Mapped[str] = mapped_column(String, index=True)
    incident_id: Mapped[str] = mapped_column(String, index=True)
    applied_at: Mapped[int] = mapped_column(BigInteger)


class EdgeSyncState(Base):
    """Per-incident sync state — last sync time and last batch stats."""

    __tablename__ = "edge_sync_state"

    incident_id: Mapped[str] = mapped_column(String, primary_key=True)
    org_id: Mapped[str] = mapped_column(String, index=True)
    last_sync_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_batch_received: Mapped[int] = mapped_column(Integer, default=0)
    last_batch_pending: Mapped[int] = mapped_column(Integer, default=0)


def compute_content_hash(payload: dict[str, object]) -> str:
    """SHA-256 hex digest of the canonical JSON encoding of payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class EdgeSync:
    """Edge-first sync endpoint logic.

    Receives outbox items from edge nodes, deduplicates by content hash,
    and applies in sequence order. Cross-batch dedup via EdgeSyncApplied table.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def sync(
        self,
        outbox_items: list[dict[str, object]],
        db: Session,
        org_id: str,
        incident_id: str,
    ) -> dict[str, object]:
        """Receive outbox items, deduplicate, apply in order.

        Returns: {received, deduplicated, applied, duplicates, errors}
        """
        unique_items = self.deduplicate(outbox_items)
        sorted_items = sorted(unique_items, key=lambda i: i.get("sequence", 0))

        applied = 0
        duplicates = 0
        errors = 0
        for item in sorted_items:
            result = self.apply_item(item, db, org_id, incident_id)
            if result == "applied":
                applied += 1
            elif result == "duplicate":
                duplicates += 1
            else:
                errors += 1

        pending = duplicates + errors
        self._update_state(db, org_id, incident_id, len(outbox_items), pending)
        return {
            "received": len(outbox_items),
            "deduplicated": len(outbox_items) - len(unique_items),
            "applied": applied,
            "duplicates": duplicates,
            "errors": errors,
        }

    def deduplicate(self, items: list[dict[str, object]]) -> list[dict[str, object]]:
        """Filter out items with duplicate content hashes within a batch."""
        seen: set[str] = set()
        unique: list[dict[str, object]] = []
        for item in items:
            h = item.get("content_hash") or compute_content_hash(item.get("payload", {}))
            if h in seen:
                continue
            seen.add(h)
            unique.append(item)
        return unique

    def apply_item(
        self,
        item: dict[str, object],
        db: Session,
        org_id: str,
        incident_id: str,
    ) -> str:
        """Apply a single outbox item. Returns 'applied', 'duplicate', or 'error'."""
        content_hash = item.get("content_hash") or compute_content_hash(
            item.get("payload", {})
        )

        # Cross-batch dedup: skip if content_hash already processed
        existing = db.execute(
            select(EdgeSyncApplied).where(EdgeSyncApplied.content_hash == content_hash)
        ).scalars().first()
        if existing is not None:
            return "duplicate"

        item_type = item.get("item_type", "unknown")
        payload = item.get("payload", {})
        try:
            self._dispatch(item_type, payload, db, org_id, incident_id)
        except Exception as e:
            db.rollback()
            logger.error(
                "edge_sync.apply_failed",
                extra={"item_id": item.get("item_id"), "error": str(e)},
            )
            return "error"

        record = EdgeSyncApplied(
            item_id=item.get("item_id") or generate_ulid(),
            content_hash=content_hash,
            item_type=item_type,
            sequence=item.get("sequence", 0),
            payload=payload,
            org_id=org_id,
            incident_id=incident_id,
            applied_at=now_ms(),
        )
        try:
            db.add(record)
            db.commit()
        except IntegrityError:
            db.rollback()
            return "duplicate"
        return "applied"

    def _dispatch(
        self,
        item_type: str,
        payload: dict,
        db: Session,
        org_id: str,
        incident_id: str,
    ) -> None:
        """Dispatch by item_type. observation -> insert, others -> audit log only."""
        if item_type == "observation":
            self._apply_observation(payload, db, org_id, incident_id)
        # task_update, status_update, etc. — recorded in EdgeSyncApplied for audit

    def _apply_observation(
        self, payload: dict, db: Session, org_id: str, incident_id: str
    ) -> None:
        """Insert an observation from the outbox payload."""
        from geoalchemy2.elements import WKTElement

        from app.models.enums import AccessPolicy, CorroborationState, SourceType
        from app.models.observation import Observation

        data = dict(payload)
        geometry_wkt = data.pop("geometry_wkt")
        data["geometry"] = WKTElement(geometry_wkt, srid=4326)
        data["source_type"] = SourceType(data["source_type"])
        data["corroboration_state"] = CorroborationState(data["corroboration_state"])
        data["access_policy"] = AccessPolicy(data["access_policy"])
        db.add(Observation(**data))
        db.flush()

    def get_sync_status(self, incident_id: str) -> dict[str, object]:
        """Return sync status: applied_count, pending_count, last_sync_at."""
        state = self.db.get(EdgeSyncState, incident_id)
        applied_count = (
            self.db.execute(
                select(func.count())
                .select_from(EdgeSyncApplied)
                .where(EdgeSyncApplied.incident_id == incident_id)
            ).scalar()
            or 0
        )
        return {
            "incident_id": incident_id,
            "applied_count": applied_count,
            "pending_count": state.last_batch_pending if state else 0,
            "last_sync_at": state.last_sync_at if state else None,
        }

    def _update_state(
        self,
        db: Session,
        org_id: str,
        incident_id: str,
        received: int,
        pending: int,
    ) -> None:
        """Update or create sync state for an incident."""
        state = db.get(EdgeSyncState, incident_id)
        ts = now_ms()
        if state is None:
            state = EdgeSyncState(
                incident_id=incident_id,
                org_id=org_id,
                last_sync_at=ts,
                last_batch_received=received,
                last_batch_pending=pending,
            )
            db.add(state)
        else:
            state.last_sync_at = ts
            state.last_batch_received = received
            state.last_batch_pending = pending
        db.commit()


__all__ = [
    "EdgeSync",
    "EdgeSyncApplied",
    "EdgeSyncState",
    "compute_content_hash",
]
