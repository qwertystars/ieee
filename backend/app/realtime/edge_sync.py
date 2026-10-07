"""Durable edge synchronization with acknowledgement and fail-closed conflicts."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import BigInteger, Index, Integer, String, and_, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base
from app.lib.audit import write_audit
from app.lib.observability import telemetry_span
from app.lib.observability_metrics import record_offline_sync
from app.lib.time import now_ms

logger = logging.getLogger(__name__)
MAX_QUEUE_AGE_MS = 24 * 60 * 60 * 1000
MAX_CLOCK_SKEW_MS = 30 * 1000
CRITICAL_TYPES = frozenset({"task", "task_state", "task_assignment", "public_warning", "resource_commitment", "alert"})


class EdgeSyncApplied(Base):
    """Append-only receipt ledger for idempotent edge mutations."""

    __tablename__ = "edge_sync_applied"
    __table_args__ = (
        Index(
            "uq_edge_sync_applied_org_incident_hash",
            "org_id",
            "incident_id",
            "content_hash",
            unique=True,
        ),
        Index("uq_edge_sync_applied_org_idempotency", "org_id", "idempotency_key", unique=True),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(String(26), unique=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(26))
    content_hash: Mapped[str] = mapped_column(String(64))
    item_type: Mapped[str] = mapped_column(String)
    sequence: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB)
    org_id: Mapped[str] = mapped_column(String, index=True)
    incident_id: Mapped[str] = mapped_column(String, index=True)
    applied_at: Mapped[int] = mapped_column(BigInteger)


class EdgeSyncState(Base):
    """Per-incident receipt counters retained across process restarts."""

    __tablename__ = "edge_sync_state"
    org_id: Mapped[str] = mapped_column(String, primary_key=True)
    incident_id: Mapped[str] = mapped_column(String, primary_key=True)
    last_sync_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_batch_received: Mapped[int] = mapped_column(Integer, default=0)
    last_batch_pending: Mapped[int] = mapped_column(Integer, default=0)


def compute_content_hash(payload: dict[str, Any]) -> str:
    """Return the SHA-256 hash of a canonical JSON payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _offline_metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("offline")
    if not isinstance(metadata, dict):
        metadata = {"device_id": item.get("device_id"), "device_sequence": item.get("device_sequence")}
    return metadata


def _critical(item: dict[str, Any], payload: dict[str, Any]) -> bool:
    values = {str(item.get("item_type", "")), str(payload.get("entity_type", "")), str(payload.get("conflict_class", ""))}
    return bool(values & CRITICAL_TYPES) or any(token in str(item.get("url", "")).lower() for token in ("/tasks/", "/alerts/", "/resources/"))


class EdgeSync:
    """Apply authenticated edge items in device-sequence order."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def sync(self, outbox_items: list[dict[str, Any]], db: Session, org_id: str, incident_id: str) -> dict[str, Any]:
        """Process a batch and return an acknowledgement for every input item."""
        unique = self.deduplicate(outbox_items)
        duplicate_ids = {str(item.get("item_id")) for item in outbox_items if item not in unique}
        ordered = sorted(unique, key=lambda item: (_offline_metadata(item).get("device_id", ""), _offline_metadata(item).get("device_sequence", 0)))
        acknowledgements: list[dict[str, Any]] = []
        applied = duplicates = conflicts = errors = 0
        for item in ordered:
            with telemetry_span("offline.sync", {"component": "edge-sync"}):
                result = self.apply_item(item, db, org_id, incident_id)
            acknowledgements.append(result)
            status = result["status"]
            record_offline_sync(str(status))
            if status in {"failed", "duplicate"}:
                self._audit(db, org_id, incident_id, str(result.get("item_id")), f"offline_sync_{status}", result, item.get("idempotency_key"))
            if status == "acked": applied += 1
            elif status == "duplicate": duplicates += 1
            elif status == "conflict": conflicts += 1
            else: errors += 1
        for item in outbox_items:
            if str(item.get("item_id")) in duplicate_ids:
                acknowledgements.append({"item_id": item.get("item_id"), "status": "duplicate", "reason": "duplicate_batch"})
        self._update_state(db, org_id, incident_id, len(outbox_items), duplicates + conflicts + errors)
        return {"received": len(outbox_items), "deduplicated": len(outbox_items) - len(unique), "applied": applied, "duplicates": duplicates, "conflicts": conflicts, "errors": errors, "acknowledgements": acknowledgements}

    def deduplicate(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove repeated content hashes within one delivery batch."""
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for item in items:
            payload = item.get("payload")
            if not isinstance(payload, dict):
                unique.append(item)
                continue
            digest = compute_content_hash(payload)
            if digest in seen:
                continue
            seen.add(digest)
            unique.append(item)
        return unique

    def apply_item(self, item: dict[str, Any], db: Session, org_id: str, incident_id: str) -> dict[str, Any]:
        """Validate, apply, and acknowledge one item without implicit overwrite."""
        item_id = item.get("item_id")
        payload = item.get("payload")
        metadata = _offline_metadata(item)
        if not isinstance(item_id, str) or not isinstance(payload, dict):
            return self._failed(item_id, "malformed_item")
        device_id = metadata.get("device_id")
        device_sequence = metadata.get("device_sequence")
        created_at = item.get("created_at")
        if not isinstance(device_id, str) or not device_id or not isinstance(device_sequence, int) or device_sequence < 1:
            return self._failed(item_id, "device_sequence_required")
        if not isinstance(created_at, int) or created_at < now_ms() - MAX_QUEUE_AGE_MS or created_at > now_ms() + MAX_CLOCK_SKEW_MS:
            return self._failed(item_id, "queue_age_or_clock_skew")
        computed_hash = compute_content_hash(payload)
        content_hash = item.get("content_hash") or computed_hash
        if not isinstance(content_hash, str) or len(content_hash) != 64 or content_hash != computed_hash:
            return self._failed(item_id, "content_hash_mismatch")
        idempotency_key = item.get("idempotency_key") or item_id
        if not isinstance(idempotency_key, str) or not idempotency_key:
            return self._failed(item_id, "idempotency_key_required")
        existing = db.execute(select(EdgeSyncApplied).where(EdgeSyncApplied.org_id == org_id, EdgeSyncApplied.item_id == item_id)).scalars().first()
        if existing is not None:
            return self._ack(item_id, "duplicate", "idempotent_replay", existing.sequence)
        existing_key = db.execute(select(EdgeSyncApplied).where(EdgeSyncApplied.org_id == org_id, EdgeSyncApplied.idempotency_key == idempotency_key)).scalars().first()
        if existing_key is not None:
            return self._ack(item_id, "duplicate", "idempotent_replay", existing_key.sequence)
        last_sequence = self._last_device_sequence(db, org_id, incident_id, device_id)
        if device_sequence <= last_sequence:
            return self._failed(item_id, "device_sequence_replay")
        if item.get("reinstalled") is True:
            return self._failed(item_id, "device_reenrollment_required")
        conflict = self._find_conflict(item, payload, db, org_id, incident_id)
        if conflict is not None:
            self._record_conflict(item, payload, conflict, db, org_id, incident_id)
            return self._ack(item_id, "conflict", "human_resolution_required", device_sequence)
        try:
            self._dispatch(item.get("item_type", "unknown"), payload, db, org_id, incident_id)
            stored_payload = {**payload, "_offline": {"device_id": device_id, "device_sequence": device_sequence, "idempotency_key": idempotency_key}}
            db.add(EdgeSyncApplied(item_id=item_id, idempotency_key=idempotency_key, content_hash=content_hash, item_type=str(item.get("item_type", "unknown")), sequence=device_sequence, payload=stored_payload, org_id=org_id, incident_id=incident_id, applied_at=now_ms()))
            db.commit()
        except (IntegrityError, KeyError, TypeError, ValueError) as error:
            db.rollback()
            logger.error("edge_sync.apply_failed", extra={"error_type": type(error).__name__})
            return self._failed(item_id, "apply_failed")
        self._audit(db, org_id, incident_id, item_id, "offline_sync_ack", {"status": "acked", "device_sequence": device_sequence}, item.get("idempotency_key"))
        return self._ack(item_id, "acked", "applied", device_sequence)

    def _last_device_sequence(self, db: Session, org_id: str, incident_id: str, device_id: str) -> int:
        rows = db.execute(select(EdgeSyncApplied).where(and_(EdgeSyncApplied.org_id == org_id, EdgeSyncApplied.incident_id == incident_id))).scalars().all()
        return max((row.payload.get("_offline", {}).get("device_sequence", 0) for row in rows if row.payload.get("_offline", {}).get("device_id") == device_id), default=0)

    def _find_conflict(self, item: dict[str, Any], payload: dict[str, Any], db: Session, org_id: str, incident_id: str) -> EdgeSyncApplied | None:
        entity_type = payload.get("entity_type") or item.get("item_type")
        entity_id = payload.get("entity_id") or payload.get("task_id")
        if not isinstance(entity_type, str) or not isinstance(entity_id, str):
            return None
        rows = db.execute(select(EdgeSyncApplied).where(and_(EdgeSyncApplied.org_id == org_id, EdgeSyncApplied.incident_id == incident_id)).order_by(EdgeSyncApplied.id.desc())).scalars().all()
        for row in rows:
            prior = row.payload or {}
            if prior.get("entity_type") == entity_type and prior.get("entity_id") == entity_id and row.content_hash != compute_content_hash(payload):
                return row
        return None

    def _record_conflict(self, item: dict[str, Any], payload: dict[str, Any], prior: EdgeSyncApplied, db: Session, org_id: str, incident_id: str) -> None:
        from app.realtime.sync import SyncConflict

        item_id = str(item.get("item_id"))
        existing = db.execute(select(SyncConflict).where(SyncConflict.org_id == org_id, SyncConflict.incident_id == incident_id, SyncConflict.item_id == item_id)).scalars().first()
        if existing is not None:
            return
        db.add(SyncConflict(item_id=item_id, org_id=org_id, incident_id=incident_id, entity_type=str(payload.get("entity_type", item.get("item_type", "unknown"))), entity_id=str(payload.get("entity_id", payload.get("task_id", "unknown"))), local=prior.payload, remote=payload, content_hash_local=prior.content_hash, content_hash_remote=compute_content_hash(payload), detected_at=now_ms()))
        db.commit()
        self._audit(db, org_id, incident_id, str(item.get("item_id")), "offline_sync_conflict", {"status": "conflict", "resolution": "human_resolution_required", "safety_critical": _critical(item, payload)}, item.get("idempotency_key"))

    def _dispatch(self, item_type: str, payload: dict[str, Any], db: Session, org_id: str, incident_id: str) -> None:
        if item_type == "observation":
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

    def _audit(self, db: Session, org_id: str, incident_id: str, item_id: str, action: str, after: dict[str, Any], external_id: Any) -> None:
        write_audit(db, org_id, incident_id, "edge-sync", action, f"outbox:{item_id}", after=after, event_type="offline.sync", source_id="edge-sync", external_id=external_id if isinstance(external_id, str) else item_id)

    @staticmethod
    def _ack(item_id: str | None, status: str, reason: str, server_sequence: int) -> dict[str, Any]:
        return {"item_id": item_id, "status": status, "reason": reason, "server_sequence": server_sequence}

    @staticmethod
    def _failed(item_id: Any, reason: str) -> dict[str, Any]:
        return {"item_id": item_id, "status": "failed", "reason": reason}

    def get_sync_status(self, incident_id: str, org_id: str | None = None) -> dict[str, Any]:
        """Return durable receipt counts for an incident."""
        state = self.db.execute(select(EdgeSyncState).where(EdgeSyncState.incident_id == incident_id, *( [EdgeSyncState.org_id == org_id] if org_id is not None else [] ))).scalars().first()
        applied_count = self.db.execute(select(func.count()).select_from(EdgeSyncApplied).where(EdgeSyncApplied.incident_id == incident_id, *( [EdgeSyncApplied.org_id == org_id] if org_id is not None else [] ))).scalar() or 0
        return {"incident_id": incident_id, "applied_count": applied_count, "pending_count": state.last_batch_pending if state else 0, "last_sync_at": state.last_sync_at if state else None}

    def _update_state(self, db: Session, org_id: str, incident_id: str, received: int, pending: int) -> None:
        state = db.execute(select(EdgeSyncState).where(EdgeSyncState.org_id == org_id, EdgeSyncState.incident_id == incident_id)).scalars().first()
        values = {"last_sync_at": now_ms(), "last_batch_received": received, "last_batch_pending": pending}
        if state is None: db.add(EdgeSyncState(incident_id=incident_id, org_id=org_id, **values))
        else:
            state.last_sync_at, state.last_batch_received, state.last_batch_pending = values["last_sync_at"], received, pending
        db.commit()


__all__ = ["MAX_CLOCK_SKEW_MS", "MAX_QUEUE_AGE_MS", "EdgeSync", "EdgeSyncApplied", "EdgeSyncState", "compute_content_hash"]
