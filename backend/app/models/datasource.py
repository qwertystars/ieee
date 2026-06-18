"""DataSource and RawIngestedRecord models (DESIGN §4)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import DataSourceType, ProcessingStatus
from app.models.mixins import TimestampMixin, uuid_pk


class DataSource(Base, TimestampMixin):
    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[DataSourceType] = mapped_column(
        SAEnum(DataSourceType, name="data_source_type"), nullable=False
    )
    provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    refresh_interval_s: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class RawIngestedRecord(Base):
    __tablename__ = "raw_ingested_records"

    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("data_sources.id"), nullable=True
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("disaster_events.id"), nullable=True
    )
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        SAEnum(ProcessingStatus, name="processing_status"),
        nullable=False,
        default=ProcessingStatus.pending,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
