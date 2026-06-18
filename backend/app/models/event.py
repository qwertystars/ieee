"""DisasterEvent model (DESIGN §4)."""
from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import DisasterType
from app.models.mixins import TimestampMixin, uuid_pk


class DisasterEvent(Base, TimestampMixin):
    __tablename__ = "disaster_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[DisasterType] = mapped_column(
        SAEnum(DisasterType, name="disaster_type"), nullable=False, default=DisasterType.flood
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_region: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
