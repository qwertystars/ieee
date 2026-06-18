"""DisasterEvent schemas (DESIGN §5)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import DisasterType
from app.schemas.common import OptionalGeometry, ORMBase


class DisasterEventBase(BaseModel):
    name: str
    type: DisasterType = DisasterType.flood
    status: str = "active"
    start_time: datetime | None = None
    end_time: datetime | None = None
    description: str | None = None
    affected_region: OptionalGeometry = None


class DisasterEventCreate(DisasterEventBase):
    pass


class DisasterEventUpdate(BaseModel):
    name: str | None = None
    type: DisasterType | None = None
    status: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    description: str | None = None
    affected_region: OptionalGeometry = None


class DisasterEventRead(ORMBase):
    id: uuid.UUID
    name: str
    type: DisasterType
    status: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    description: str | None = None
    affected_region: OptionalGeometry = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
