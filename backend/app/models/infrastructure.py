"""Shelter, Hospital, and RoadStatus models (DESIGN §4)."""
from __future__ import annotations

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import RoadStatusEnum
from app.models.mixins import uuid_pk


class Shelter(Base):
    __tablename__ = "shelters"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    total_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_occupancy: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    food_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    water_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    medical_support: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accessibility_support: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @property
    def available_capacity(self) -> int:
        return max(0, (self.total_capacity or 0) - (self.current_occupancy or 0))


class Hospital(Base):
    __tablename__ = "hospitals"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    emergency_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="operational")
    access_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RoadStatus(Base):
    __tablename__ = "road_statuses"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("disaster_events.id"), nullable=True, index=True
    )
    road_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326), nullable=True
    )
    status: Mapped[RoadStatusEnum] = mapped_column(
        SAEnum(RoadStatusEnum, name="road_status_enum"),
        nullable=False,
        default=RoadStatusEnum.unknown,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
