"""AuditLog and Alert schemas (DESIGN §5 / §8)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OptionalGeometry, ORMBase


class AlertBase(BaseModel):
    event_id: uuid.UUID | None = None
    alert_type: str | None = None
    title: str | None = None
    message: str | None = None
    area: OptionalGeometry = None
    severity: str | None = None
    recommended_action: str | None = None
    confidence_score: float | None = None
    acknowledged: bool = False


class AlertCreate(AlertBase):
    pass


class AlertUpdate(BaseModel):
    acknowledged: bool | None = None
    severity: str | None = None
    recommended_action: str | None = None


class AlertRead(ORMBase):
    id: uuid.UUID
    event_id: uuid.UUID | None = None
    alert_type: str | None = None
    title: str | None = None
    message: str | None = None
    area: OptionalGeometry = None
    severity: str | None = None
    recommended_action: str | None = None
    confidence_score: float | None = None
    acknowledged: bool
    created_at: datetime


class AuditLogRead(ORMBase):
    id: uuid.UUID
    user_id: uuid.UUID | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    details: dict | None = None
    created_at: datetime
