"""ResponseTeam and Task schemas (DESIGN §5)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import TaskStatus, TeamType, Urgency
from app.schemas.common import OptionalGeometry, ORMBase


class ResponseTeamBase(BaseModel):
    name: str
    team_type: TeamType
    current_location: OptionalGeometry = None
    status: str = "available"
    capacity: int | None = None
    assigned_task_id: uuid.UUID | None = None


class ResponseTeamCreate(ResponseTeamBase):
    pass


class ResponseTeamUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    capacity: int | None = None
    current_location: OptionalGeometry = None
    assigned_task_id: uuid.UUID | None = None


class ResponseTeamRead(ORMBase):
    id: uuid.UUID
    name: str
    team_type: TeamType
    current_location: OptionalGeometry = None
    status: str
    capacity: int | None = None
    assigned_task_id: uuid.UUID | None = None
    updated_at: datetime


class TaskBase(BaseModel):
    event_id: uuid.UUID | None = None
    recommendation_id: uuid.UUID | None = None
    assigned_team_id: uuid.UUID | None = None
    title: str | None = None
    description: str | None = None
    location: OptionalGeometry = None
    priority: Urgency = Urgency.medium
    status: TaskStatus = TaskStatus.assigned


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    assigned_team_id: uuid.UUID | None = None
    priority: Urgency | None = None
    status: TaskStatus | None = None
    location: OptionalGeometry = None


class TaskRead(ORMBase):
    id: uuid.UUID
    event_id: uuid.UUID | None = None
    recommendation_id: uuid.UUID | None = None
    assigned_team_id: uuid.UUID | None = None
    title: str | None = None
    description: str | None = None
    location: OptionalGeometry = None
    priority: Urgency
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
