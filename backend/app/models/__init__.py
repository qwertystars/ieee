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
from app.models.observation import Observation  # noqa: E402, F401
from app.models.entities import (  # noqa: E402, F401
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
from app.models.relationships import GraphEdge  # noqa: E402, F401
from app.models.hypotheses import Hypothesis  # noqa: E402, F401
from app.models.scenarios import Scenario  # noqa: E402, F401
from app.models.events import Event  # noqa: E402, F401
from app.models.user import User  # noqa: E402, F401

__all__ = [
    "Base",
    "TenancyMixin",
    "TimestampMixin",
    "Observation",
    "Hazard",
    "Zone",
    "Building",
    "RoadSegment",
    "Bridge",
    "PowerSubstation",
    "CellTower",
    "Hospital",
    "Shelter",
    "Responder",
    "Vehicle",
    "Sensor",
    "OperationalTask",
    "Decision",
    "GraphEdge",
    "Hypothesis",
    "Scenario",
    "Event",
    "User",
]
