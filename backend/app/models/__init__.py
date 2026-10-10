"""Model package — exports all SQLAlchemy models and mixins.

Mixins are defined here (before model imports) to avoid circular imports.
Models import Base from app.db and enums from app.models.enums.
"""

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TenancyMixin:
    """org_id + incident_id tenancy columns for incident-scoped tables."""

    org_id: Mapped[str] = mapped_column(String, index=True)
    incident_id: Mapped[str] = mapped_column(String, index=True)


class TimestampMixin:
    """created_at + updated_at as BigInteger UTC epoch milliseconds."""

    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)


# Import models so Base.metadata is populated for Alembic autogenerate.
from app.models.alert import (
    Alert,
    AlertDecision,
    CommandApproval,
    CommandSigningKey,
)
from app.models.coordination import (
    CredentialState,
    EmergencyOverrideRecord,
    EvaluationJob,
    QuarantineRecord,
)
from app.models.entities import (
    Bridge,
    Building,
    CellTower,
    Decision,
    Hazard,
    Hospital,
    OperationalTask,
    PowerSubstation,
    Responder,
    RoadSegment,
    Sensor,
    Shelter,
    Vehicle,
    Zone,
)
from app.models.events import Event
from app.models.fusion_replay import (
    FusionReplayErrorRecord,
    FusionReplayInputRecord,
    FusionReplayOutputRecord,
    FusionReplayRun,
)
from app.models.hypotheses import Hypothesis
from app.models.incident import Incident
from app.models.observation import Observation
from app.models.recommendation import Recommendation
from app.models.relationships import GraphEdge
from app.models.scenarios import Scenario
from app.models.user import User

__all__ = [
    "Alert",
    "AlertDecision",
    "Base",
    "Bridge",
    "Building",
    "CellTower",
    "CommandApproval",
    "CommandSigningKey",
    "CredentialState",
    "Decision",
    "EmergencyOverrideRecord",
    "EvaluationJob",
    "Event",
    "FusionReplayErrorRecord",
    "FusionReplayInputRecord",
    "FusionReplayOutputRecord",
    "FusionReplayRun",
    "GraphEdge",
    "Hazard",
    "Hospital",
    "Hypothesis",
    "Incident",
    "Observation",
    "OperationalTask",
    "PowerSubstation",
    "QuarantineRecord",
    "Recommendation",
    "Responder",
    "RoadSegment",
    "Scenario",
    "Sensor",
    "Shelter",
    "TenancyMixin",
    "TimestampMixin",
    "User",
    "Vehicle",
    "Zone",
]
