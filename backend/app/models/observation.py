"""NormalizedObservation and IncidentReport models (DESIGN §4)."""
from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import (
    ObservationType,
    ReportCategory,
    ReporterType,
    Urgency,
    VerificationStatus,
)
from app.models.mixins import TimestampMixin, uuid_pk


class NormalizedObservation(Base):
    __tablename__ = "normalized_observations"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("disaster_events.id"), nullable=True, index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("data_sources.id"), nullable=True
    )
    observation_type: Mapped[ObservationType] = mapped_column(
        SAEnum(ObservationType, name="observation_type"), nullable=False
    )
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True
    )
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IncidentReport(Base, TimestampMixin):
    __tablename__ = "incident_reports"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("disaster_events.id"), nullable=True, index=True
    )
    reporter_type: Mapped[ReporterType] = mapped_column(
        SAEnum(ReporterType, name="reporter_type"), nullable=False
    )
    report_category: Mapped[ReportCategory] = mapped_column(
        SAEnum(ReportCategory, name="report_category"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    photo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    urgency: Mapped[Urgency] = mapped_column(
        SAEnum(Urgency, name="urgency"), nullable=False, default=Urgency.medium
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, name="verification_status"),
        nullable=False,
        default=VerificationStatus.unverified,
    )
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pii_redacted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
