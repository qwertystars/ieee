"""Shelter, Hospital, RoadStatus schemas (DESIGN §5)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import RoadStatusEnum
from app.schemas.common import OptionalGeometry, ORMBase


class ShelterBase(BaseModel):
    name: str
    geometry: OptionalGeometry = None
    total_capacity: int = 0
    current_occupancy: int = 0
    food_status: str | None = None
    water_status: str | None = None
    medical_support: bool = False
    accessibility_support: bool = False
    status: str = "open"


class ShelterCreate(ShelterBase):
    pass


class ShelterUpdate(BaseModel):
    name: str | None = None
    total_capacity: int | None = None
    current_occupancy: int | None = None
    food_status: str | None = None
    water_status: str | None = None
    medical_support: bool | None = None
    accessibility_support: bool | None = None
    status: str | None = None


class ShelterRead(ORMBase):
    id: uuid.UUID
    name: str
    geometry: OptionalGeometry = None
    total_capacity: int
    current_occupancy: int
    available_capacity: int
    food_status: str | None = None
    water_status: str | None = None
    medical_support: bool
    accessibility_support: bool
    status: str
    updated_at: datetime


class HospitalBase(BaseModel):
    name: str
    geometry: OptionalGeometry = None
    emergency_capacity: int = 0
    status: str = "operational"
    access_status: str | None = None
    contact: str | None = None


class HospitalCreate(HospitalBase):
    pass


class HospitalUpdate(BaseModel):
    name: str | None = None
    emergency_capacity: int | None = None
    status: str | None = None
    access_status: str | None = None
    contact: str | None = None


class HospitalRead(ORMBase):
    id: uuid.UUID
    name: str
    geometry: OptionalGeometry = None
    emergency_capacity: int
    status: str
    access_status: str | None = None
    contact: str | None = None
    updated_at: datetime


class RoadStatusBase(BaseModel):
    event_id: uuid.UUID | None = None
    road_name: str | None = None
    geometry: OptionalGeometry = None
    status: RoadStatusEnum = RoadStatusEnum.unknown
    reason: str | None = None
    confidence_score: float | None = None


class RoadStatusCreate(RoadStatusBase):
    pass


class RoadStatusUpdate(BaseModel):
    status: RoadStatusEnum | None = None
    reason: str | None = None
    confidence_score: float | None = None


class RoadStatusRead(ORMBase):
    id: uuid.UUID
    event_id: uuid.UUID | None = None
    road_name: str | None = None
    geometry: OptionalGeometry = None
    status: RoadStatusEnum
    reason: str | None = None
    confidence_score: float | None = None
    updated_at: datetime
