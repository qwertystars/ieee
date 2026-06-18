"""AreaAssessment and Recommendation models (DESIGN §4)."""
from __future__ import annotations

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import (
    PriorityLevel,
    RecommendationStatus,
    RecommendationType,
    Urgency,
)
from app.models.mixins import TimestampMixin, uuid_pk


class AreaAssessment(Base):
    __tablename__ = "area_assessments"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("disaster_events.id"), nullable=True, index=True
    )
    area_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True
    )
    hazard_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    exposure_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    access_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    infrastructure_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    vulnerability_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    report_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    overall_priority_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    priority_level: Mapped[PriorityLevel] = mapped_column(
        SAEnum(PriorityLevel, name="priority_level"),
        nullable=False,
        default=PriorityLevel.unknown,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    components: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Recommendation(Base, TimestampMixin):
    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("disaster_events.id"), nullable=True, index=True
    )
    area_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("area_assessments.id"), nullable=True
    )
    recommendation_type: Mapped[RecommendationType] = mapped_column(
        SAEnum(RecommendationType, name="recommendation_type"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    supporting_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    urgency: Mapped[Urgency] = mapped_column(
        SAEnum(Urgency, name="urgency"), nullable=False, default=Urgency.medium
    )
    status: Mapped[RecommendationStatus] = mapped_column(
        SAEnum(RecommendationStatus, name="recommendation_status"),
        nullable=False,
        default=RecommendationStatus.draft,
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("response_teams.id"), nullable=True
    )
