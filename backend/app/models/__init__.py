"""SQLAlchemy models package.

Importing this package registers every model on ``Base.metadata`` so Alembic
autogeneration and ``create_all`` see the full schema.
"""
from __future__ import annotations

from app.models.assessment import AreaAssessment, Recommendation
from app.models.audit import Alert, AuditLog
from app.models.datasource import DataSource, RawIngestedRecord
from app.models.event import DisasterEvent
from app.models.infrastructure import Hospital, RoadStatus, Shelter
from app.models.observation import IncidentReport, NormalizedObservation
from app.models.response import ResponseTeam, Task
from app.models.user import User

__all__ = [
    "User",
    "DisasterEvent",
    "DataSource",
    "RawIngestedRecord",
    "NormalizedObservation",
    "IncidentReport",
    "AreaAssessment",
    "Recommendation",
    "Shelter",
    "Hospital",
    "RoadStatus",
    "ResponseTeam",
    "Task",
    "AuditLog",
    "Alert",
]
