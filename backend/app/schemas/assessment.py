"""AreaAssessment and Recommendation schemas (DESIGN §5)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import (
    PriorityLevel,
    RecommendationStatus,
    RecommendationType,
    Urgency,
)
from app.schemas.common import OptionalGeometry, ORMBase


class AreaAssessmentBase(BaseModel):
    event_id: uuid.UUID | None = None
    area_name: str | None = None
    geometry: OptionalGeometry = None
    hazard_score: float | None = None
    exposure_score: float | None = None
    access_score: float | None = None
    infrastructure_score: float | None = None
    vulnerability_score: float | None = None
    trend_score: float | None = None
    report_score: float | None = None
    overall_priority_score: float | None = None
    priority_level: PriorityLevel = PriorityLevel.unknown
    summary: str | None = None
    components: dict | None = None


class AreaAssessmentCreate(AreaAssessmentBase):
    pass


class AreaAssessmentUpdate(BaseModel):
    area_name: str | None = None
    summary: str | None = None
    priority_level: PriorityLevel | None = None
    overall_priority_score: float | None = None
    components: dict | None = None


class AreaAssessmentRead(ORMBase):
    id: uuid.UUID
    event_id: uuid.UUID | None = None
    area_name: str | None = None
    geometry: OptionalGeometry = None
    hazard_score: float | None = None
    exposure_score: float | None = None
    access_score: float | None = None
    infrastructure_score: float | None = None
    vulnerability_score: float | None = None
    trend_score: float | None = None
    report_score: float | None = None
    overall_priority_score: float | None = None
    priority_level: PriorityLevel
    summary: str | None = None
    components: dict | None = None
    updated_at: datetime


class RecommendationBase(BaseModel):
    event_id: uuid.UUID | None = None
    area_assessment_id: uuid.UUID | None = None
    recommendation_type: RecommendationType
    title: str | None = None
    description: str | None = None
    reasoning: str | None = None
    supporting_data: dict | None = None
    confidence_score: float | None = None
    urgency: Urgency = Urgency.medium
    status: RecommendationStatus = RecommendationStatus.draft
    assigned_to: uuid.UUID | None = None


class RecommendationCreate(RecommendationBase):
    pass


class RecommendationUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    reasoning: str | None = None
    status: RecommendationStatus | None = None
    urgency: Urgency | None = None
    assigned_to: uuid.UUID | None = None


class RecommendationRead(ORMBase):
    id: uuid.UUID
    event_id: uuid.UUID | None = None
    area_assessment_id: uuid.UUID | None = None
    recommendation_type: RecommendationType
    title: str | None = None
    description: str | None = None
    reasoning: str | None = None
    supporting_data: dict | None = None
    confidence_score: float | None = None
    urgency: Urgency
    status: RecommendationStatus
    assigned_to: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
