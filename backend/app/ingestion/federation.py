"""Federated data fabric — source management and delayed sync outbox.

SourceManager handles registration and status tracking of data sources.
OutboxManager handles delayed synchronization of offline observations.

Ownership discipline: federated sources are NOT centralized. Only owned and
aggregated sources have their observations inserted into the local
observations table during sync_outbox().
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String, Text, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, Session

from app.db import Base
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.models.observation import Observation
from app.models.source import Ownership, Source, SourceKind, SourceStatus


class OutboxEntry(Base):
    """A pending observation sync entry — created offline, inserted later."""

    __tablename__ = "federation_outbox"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    observation_id: Mapped[str] = mapped_column(String(26), index=True)
    source_id: Mapped[str] = mapped_column(String, index=True)
    org_id: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    sync_priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[int] = mapped_column(BigInteger)
    synced_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceManager:
    """Manage federated data sources — registration, status, listing."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def register_source(
        self,
        org_id: str,
        name: str,
        type: SourceKind,
        provider: str,
        config: dict,
        ownership: Ownership,
        access_policy: AccessPolicy,
        refresh_interval_s: int | None = None,
    ) -> str:
        """Register a new data source. Returns the source ULID."""
        source_id = generate_ulid()
        ts = now_ms()
        source = Source(
            id=source_id,
            org_id=org_id,
            name=name,
            type=type,
            provider=provider,
            refresh_interval_s=refresh_interval_s,
            status=SourceStatus.active,
            config=config,
            access_policy=access_policy,
            ownership=ownership,
            created_at=ts,
            updated_at=ts,
        )
        self.db.add(source)
        self.db.commit()
        return source_id

    def update_source_status(
        self, source_id: str, success: bool, error: str | None = None
    ) -> None:
        """Update source status after a sync attempt."""
        source = self.db.get(Source, source_id)
        if source is None:
            raise ValueError(f"source not found: {source_id}")
        ts = now_ms()
        if success:
            source.last_success_at = ts
            source.last_error = None
            source.status = SourceStatus.active
        else:
            source.last_error = error
            source.status = SourceStatus.error
        source.updated_at = ts
        self.db.commit()

    def list_sources(
        self,
        org_id: str,
        ownership_filter: Ownership | None = None,
    ) -> list[Source]:
        """List sources for an org, optionally filtered by ownership."""
        stmt = select(Source).where(Source.org_id == org_id)
        if ownership_filter is not None:
            stmt = stmt.where(Source.ownership == ownership_filter)
        return list(self.db.execute(stmt).scalars().all())


class OutboxManager:
    """Delayed sync outbox for offline observations.

    Observations created offline are queued here and inserted into the
    observations table when sync_outbox() is called. Federated sources
    are NOT centralized — their outbox entries are marked as skipped.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def add_to_outbox(
        self,
        observation_id: str,
        source_id: str,
        payload: dict,
        sync_priority: int = 0,
    ) -> str:
        """Queue an observation for delayed sync. Returns the outbox entry ULID."""
        entry = OutboxEntry(
            id=generate_ulid(),
            observation_id=observation_id,
            source_id=source_id,
            org_id=payload.get("org_id", ""),
            payload=payload,
            sync_priority=sync_priority,
            status="pending",
            created_at=now_ms(),
        )
        self.db.add(entry)
        self.db.commit()
        return entry.id

    def get_pending_outbox(self, limit: int = 100) -> list[OutboxEntry]:
        """Get pending entries ordered by priority (desc) then created_at."""
        stmt = (
            select(OutboxEntry)
            .where(OutboxEntry.status == "pending")
            .order_by(OutboxEntry.sync_priority.desc(), OutboxEntry.created_at.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def mark_synced(self, outbox_id: str) -> None:
        """Mark an outbox entry as synced."""
        entry = self.db.get(OutboxEntry, outbox_id)
        if entry is None:
            raise ValueError(f"outbox entry not found: {outbox_id}")
        entry.status = "synced"
        entry.synced_at = now_ms()
        self.db.commit()

    def _build_observation(self, payload: dict) -> Observation:
        """Construct an Observation from an outbox payload dict."""
        from geoalchemy2.elements import WKTElement

        data = dict(payload)
        geometry_wkt = data.pop("geometry_wkt")
        data["geometry"] = WKTElement(geometry_wkt, srid=4326)
        data["source_type"] = SourceType(data["source_type"])
        data["corroboration_state"] = CorroborationState(data["corroboration_state"])
        data["access_policy"] = AccessPolicy(data["access_policy"])
        return Observation(**data)

    def sync_outbox(self) -> int:
        """Process pending outbox items. Returns count of synced observations.

        Respects source ownership:
        - owned / aggregated: insert observation locally
        - federated: skip (data stays remote, queried on demand)
        """
        pending = self.get_pending_outbox(limit=100)
        synced = 0
        for entry in pending:
            source = self.db.get(Source, entry.source_id)
            if source is None:
                entry.status = "failed"
                entry.error = "source not found"
                entry.synced_at = now_ms()
                continue
            if source.ownership == Ownership.federated:
                entry.status = "skipped"
                entry.error = "federated source — not centralized"
                entry.synced_at = now_ms()
                continue
            # Idempotency: skip if observation already exists
            existing = self.db.get(Observation, entry.observation_id)
            if existing is not None:
                entry.status = "synced"
                entry.synced_at = now_ms()
                synced += 1
                continue
            try:
                obs = self._build_observation(entry.payload)
                self.db.add(obs)
                self.db.flush()
                entry.status = "synced"
                entry.synced_at = now_ms()
                synced += 1
            except Exception as e:
                self.db.rollback()
                fresh = self.db.get(OutboxEntry, entry.id)
                if fresh is not None:
                    fresh.status = "failed"
                    fresh.error = str(e)[:500]
        self.db.commit()
        return synced


__all__ = [
    "OutboxEntry",
    "SourceManager",
    "OutboxManager",
]
