"""Recommendation model — an AI-generated or human-curated action suggestion.

Recommendations are scoped to an Incident (via incident_id FK) and optionally
linked to an Alert (via alert_id FK). They carry supporting/contradicting
evidence, a confidence vector, and a human-review workflow
(draft -> approved/dismissed/modified).
"""

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Recommendation(Base):
    """A recommended action during an incident, pending or post human review."""

    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_recommendations_org_id", "org_id"),
        Index("ix_recommendations_incident_id", "incident_id"),
        Index("ix_recommendations_org_incident", "org_id", "incident_id"),
        Index("ix_recommendations_status", "status"),
        Index("ix_recommendations_urgency", "urgency"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String)
    incident_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("incidents.id")
    )
    alert_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("alerts.id"), nullable=True
    )
    recommendation_type: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    supporting_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    contradicting_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence_vector: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    urgency: Mapped[str] = mapped_column(String, default="medium")
    status: Mapped[str] = mapped_column(String, default="draft")
    assigned_team_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)
