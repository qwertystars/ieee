"""Store-and-forward synchronization — monotonic sequence, dedupe, conflict surfacing.

When connectivity disappears, edge nodes continue local operation, appending
observations to a local outbox with monotonic sequence numbers. This module
synchronizes the outbox: dedup by content hash, sort by priority
(text > coordinates > task_state > imagery), detect conflicts on same-entity
edits, and surface them rather than silently overwriting. CRDT auto-merge for
selected collaborative fields (assigned_to, tags, labels).
"""

from __future__ import annotations

import logging

from sqlalchemy import BigInteger, String, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column, Session

from app.db import Base
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.realtime.edge_sync import EdgeSyncApplied, compute_content_hash

logger = logging.getLogger(__name__)

# Priority weights — lower = higher priority. text > coordinates > task_state > imagery.
_PRIORITY_ORDER: dict[str, int] = {
    "text": 0, "coordinates": 1, "task_state": 2, "imagery": 3,
}
_DEFAULT_PRIORITY = 2

# CRDT-mergeable collaborative fields. Conflicts auto-merge (union) instead of surfacing.
_CRDT_FIELDS = frozenset({"assigned_to", "tags", "labels"})


class SyncConflict(Base):
    """Surfaced conflict awaiting human resolution. Sync does NOT auto-overwrite."""

    __tablename__ = "sync_conflicts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String, index=True)
    incident_id: Mapped[str] = mapped_column(String, index=True)
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str] = mapped_column(String, index=True)
    local: Mapped[dict] = mapped_column(JSONB)
    remote: Mapped[dict] = mapped_column(JSONB)
    content_hash_local: Mapped[str] = mapped_column(String(64))
    content_hash_remote: Mapped[str] = mapped_column(String(64))
    detected_at: Mapped[int] = mapped_column(BigInteger)


def _priority_of(item: dict[str, object]) -> int:
    """Return the priority weight for an item based on its item_type."""
    itype = item.get("item_type", "")
    if itype in _PRIORITY_ORDER:
        return _PRIORITY_ORDER[itype]
    payload = item.get("payload") or {}
    kind = payload.get("content_kind")
    if isinstance(kind, str) and kind in _PRIORITY_ORDER:
        return _PRIORITY_ORDER[kind]
    return _DEFAULT_PRIORITY


class StoreAndForwardSync:
    """Store-and-forward sync with priority ordering, dedup, conflict surfacing."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def sync_items(
        self, items: list[dict[str, object]], db: Session, org_id: str, incident_id: str,
    ) -> dict[str, object]:
        """Sync outbox items: assign sequences, dedup, sort by priority, apply.

        Returns: {received, deduplicated, applied, conflicts, errors, order}
        where `order` is the list of item_ids in applied priority order.
        """
        sequenced = self._assign_sequences(items, db, incident_id)
        unique = self._dedup(sequenced, db)
        ordered = self.sort_by_priority(unique)

        applied = 0
        conflicts: list[dict[str, object]] = []
        errors = 0
        order: list[str] = []
        for item in ordered:
            result = self._apply_one(item, db, org_id, incident_id)
            status = result.get("status")
            if status == "applied":
                applied += 1
                order.append(item.get("item_id") or "")
            elif status == "conflict":
                conflicts.append(result)
            elif status == "error":
                errors += 1
        return {
            "received": len(items),
            "deduplicated": len(items) - len(unique),
            "applied": applied,
            "conflicts": conflicts,
            "errors": errors,
            "order": order,
        }

    def sort_by_priority(self, items: list[dict[str, object]]) -> list[dict[str, object]]:
        """Sort by priority (text > coordinates > task_state > imagery).

        Ties broken by ascending sequence number.
        """
        return sorted(items, key=lambda i: (_priority_of(i), i.get("sequence", 0)))

    def detect_conflicts(self, item: dict[str, object], db: Session) -> dict[str, object] | None:
        """Check for conflicting edits on the same entity.

        Returns a conflict descriptor if a conflict exists, else None.
        Conflict = same (entity_type, entity_id) AND different content_hash.
        """
        payload = item.get("payload") or {}
        entity_type = payload.get("entity_type") or item.get("item_type", "")
        entity_id = payload.get("entity_id") or ""
        if not entity_type or not entity_id:
            return None

        content_hash = item.get("content_hash") or compute_content_hash(payload)
        candidates = db.execute(
            select(EdgeSyncApplied).order_by(EdgeSyncApplied.id.desc()).limit(100)
        ).scalars().all()

        for rec in candidates:
            rec_payload = rec.payload or {}
            if rec_payload.get("entity_id") != entity_id:
                continue
            if rec_payload.get("entity_type") != entity_type:
                continue
            if rec.content_hash == content_hash:
                return None  # Same content — dedup, not conflict.
            return {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "local": rec_payload,
                "remote": payload,
                "content_hash_local": rec.content_hash,
                "content_hash_remote": content_hash,
            }
        return None

    def resolve_conflict(self, local: dict[str, object], remote: dict[str, object]) -> dict[str, object]:
        """Return a conflict response. Does NOT auto-resolve or overwrite."""
        return {"status": "conflict", "local": local, "remote": remote}

    def _assign_sequences(self, items: list[dict[str, object]], db: Session, incident_id: str) -> list[dict[str, object]]:
        if not items:
            return items
        max_seq = (
            db.execute(
                select(func.max(EdgeSyncApplied.sequence))
                .where(EdgeSyncApplied.incident_id == incident_id)
            ).scalar()
            or 0
        )
        next_seq = max_seq + 1
        out: list[dict[str, object]] = []
        for item in items:
            if item.get("sequence") is None:
                item = {**item, "sequence": next_seq}
                next_seq += 1
            out.append(item)
        return out

    def _dedup(self, items: list[dict[str, object]], db: Session) -> list[dict[str, object]]:
        seen: set[str] = set()
        unique: list[dict[str, object]] = []
        for item in items:
            h = item.get("content_hash") or compute_content_hash(item.get("payload", {}))
            if h in seen:
                continue
            seen.add(h)
            already = db.execute(
                select(EdgeSyncApplied).where(EdgeSyncApplied.content_hash == h)
            ).scalars().first()
            if already is not None:
                continue
            unique.append(item)
        return unique

    def _apply_one(self, item: dict[str, object], db: Session, org_id: str, incident_id: str) -> dict[str, object]:
        content_hash = item.get("content_hash") or compute_content_hash(item.get("payload", {}))
        existing = db.execute(
            select(EdgeSyncApplied).where(EdgeSyncApplied.content_hash == content_hash)
        ).scalars().first()
        if existing is not None:
            return {"status": "duplicate"}

        conflict = self.detect_conflicts(item, db)
        if conflict is not None:
            all_keys = set(conflict["local"].keys()) | set(conflict["remote"].keys())
            diff_fields = {k for k in all_keys if conflict["local"].get(k) != conflict["remote"].get(k)}
            non_crdt_diffs = diff_fields - _CRDT_FIELDS

            if not non_crdt_diffs:
                # All differing fields are CRDT-mergeable — auto-merge.
                merged = self._merge_crdt_fields(conflict["local"], conflict["remote"])
                merged_payload = {**conflict["local"], **merged}
                merged_hash = compute_content_hash(merged_payload)
                if not self._record(item, db, org_id, incident_id, merged_hash, merged_payload):
                    return {"status": "duplicate"}
                return {"status": "applied", "merged": merged}

            # Surface the conflict — do NOT overwrite.
            resolution = self.resolve_conflict(conflict["local"], conflict["remote"])
            record = SyncConflict(
                org_id=org_id, incident_id=incident_id,
                entity_type=conflict["entity_type"], entity_id=conflict["entity_id"],
                local=conflict["local"], remote=conflict["remote"],
                content_hash_local=conflict["content_hash_local"],
                content_hash_remote=conflict["content_hash_remote"],
                detected_at=now_ms(),
            )
            try:
                db.add(record)
                db.commit()
            except IntegrityError:
                db.rollback()
                return {"status": "error"}
            return resolution

        if not self._record(item, db, org_id, incident_id, content_hash, item.get("payload", {})):
            return {"status": "duplicate"}
        return {"status": "applied"}

    def _record(self, item: dict[str, object], db: Session, org_id: str, incident_id: str, content_hash: str, payload: dict) -> bool:
        record = EdgeSyncApplied(
            item_id=item.get("item_id") or generate_ulid(),
            content_hash=content_hash,
            item_type=item.get("item_type", "unknown"),
            sequence=item.get("sequence", 0),
            payload=payload, org_id=org_id, incident_id=incident_id,
            applied_at=now_ms(),
        )
        try:
            db.add(record)
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            return False

    @staticmethod
    def _merge_crdt_fields(local: dict[str, object], remote: dict[str, object]) -> dict[str, object]:
        merged: dict[str, object] = {}
        for field in _CRDT_FIELDS:
            lv, rv = local.get(field), remote.get(field)
            l_set = set(lv) if isinstance(lv, list | tuple | set) else ({lv} if lv else set())
            r_set = set(rv) if isinstance(rv, list | tuple | set) else ({rv} if rv else set())
            if not l_set and not r_set:
                continue
            merged[field] = sorted(l_set | r_set)
        return merged


__all__ = ["StoreAndForwardSync", "SyncConflict"]
