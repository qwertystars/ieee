"""Alert model — a warning or notification generated during an incident.

Alerts are scoped to an Incident (via incident_id FK) and carry an optional
geometry (area), a severity level, a confidence vector, and a human-review
workflow (draft -> approved/dismissed/modified).
"""

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry

from app.db import Base


class Alert(Base):
    """An alert generated during an incident, pending or post human review."""

    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_org_id", "org_id"),
        Index("ix_alerts_incident_id", "incident_id"),
        Index("ix_alerts_org_incident", "org_id", "incident_id"),
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_severity", "severity"),
        Index("ix_alerts_area", "area", postgresql_using="gist"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String)
    incident_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("incidents.id")
    )
    alert_type: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(Text)
    area: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True
    )
    severity: Mapped[str] = mapped_column(String)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_vector: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String, default="draft")
    created_by: Mapped[str] = mapped_column(String)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    review_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
