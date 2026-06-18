"""ResponseTeam and Task models (DESIGN §4)."""
from __future__ import annotations

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import TaskStatus, TeamType, Urgency
from app.models.mixins import TimestampMixin, uuid_pk


class ResponseTeam(Base):
    __tablename__ = "response_teams"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    team_type: Mapped[TeamType] = mapped_column(
        SAEnum(TeamType, name="team_type"), nullable=False
    )
    current_location: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="available")
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_task_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("disaster_events.id"), nullable=True, index=True
    )
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("recommendations.id"), nullable=True
    )
    assigned_team_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("response_teams.id"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    priority: Mapped[Urgency] = mapped_column(
        SAEnum(Urgency, name="urgency"), nullable=False, default=Urgency.medium
    )
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="task_status"), nullable=False, default=TaskStatus.assigned
    )
