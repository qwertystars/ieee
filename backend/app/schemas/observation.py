"""NormalizedObservation and IncidentReport schemas (DESIGN §5)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import (
    ObservationType,
    ReportCategory,
    ReporterType,
    Urgency,
    VerificationStatus,
)
from app.schemas.common import OptionalGeometry, ORMBase


class NormalizedObservationBase(BaseModel):
    event_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    observation_type: ObservationType
    geometry: OptionalGeometry = None
    timestamp: datetime | None = None
    value: float | None = None
    unit: str | None = None
    description: str | None = None
    confidence_score: float | None = None
    metadata: dict | None = Field(default=None, alias="extra_metadata")


class NormalizedObservationCreate(NormalizedObservationBase):
    pass


class NormalizedObservationUpdate(BaseModel):
    description: str | None = None
    value: float | None = None
    confidence_score: float | None = None
    cluster_id: uuid.UUID | None = None


class NormalizedObservationRead(ORMBase):
    id: uuid.UUID
    event_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    observation_type: ObservationType
    geometry: OptionalGeometry = None
    timestamp: datetime | None = None
    value: float | None = None
    unit: str | None = None
    description: str | None = None
    confidence_score: float | None = None
    metadata: dict | None = Field(default=None, validation_alias="extra_metadata")
    cluster_id: uuid.UUID | None = None
    created_at: datetime


class IncidentReportBase(BaseModel):
    event_id: uuid.UUID | None = None
    reporter_type: ReporterType
    report_category: ReportCategory
    description: str | None = None
    geometry: OptionalGeometry = None
    photo_url: str | None = None
    urgency: Urgency = Urgency.medium


class IncidentReportCreate(IncidentReportBase):
    pass


class IncidentReportUpdate(BaseModel):
    description: str | None = None
    urgency: Urgency | None = None
    verification_status: VerificationStatus | None = None
    confidence_score: float | None = None


class IncidentReportRead(ORMBase):
    id: uuid.UUID
    event_id: uuid.UUID | None = None
    reporter_type: ReporterType
    report_category: ReportCategory
    description: str | None = None
    geometry: OptionalGeometry = None
    photo_url: str | None = None
    urgency: Urgency
    verification_status: VerificationStatus
    confidence_score: float | None = None
    pii_redacted_text: str | None = None
    cluster_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
