"""Alert model — a warning or notification generated during an incident.

Alerts are scoped to an Incident (via incident_id FK) and carry an optional
geometry (area), a severity level, a confidence vector, and a human-review
workflow (draft -> approved/dismissed/modified).
"""

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, String, Text, UniqueConstraint
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


class CommandSigningKey(Base):
    """An active Ed25519 verification key owned by one organization user."""

    __tablename__ = "command_signing_keys"
    __table_args__ = (
        UniqueConstraint("org_id", "key_id", name="uq_command_key_org_key"),
        Index("ix_command_key_org_user", "org_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    key_id: Mapped[str] = mapped_column(String(26), nullable=False)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    revoked_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class AlertDecision(Base):
    """Durable approval state for an alert command."""

    __tablename__ = "alert_decisions"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "incident_id", "alert_id", "command_type",
            name="uq_alert_decision_command",
        ),
        Index("ix_alert_decisions_org_incident", "org_id", "incident_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, nullable=False)
    incident_id: Mapped[str] = mapped_column(String(26), ForeignKey("incidents.id"), nullable=False)
    alert_id: Mapped[str] = mapped_column(String(26), ForeignKey("alerts.id"), nullable=False)
    command_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    created_by: Mapped[str] = mapped_column(String(26), nullable=False)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)


class CommandApproval(Base):
    """One signed approval for a durable alert command decision."""

    __tablename__ = "command_approvals"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "decision_id", "approver_id",
            name="uq_command_approval_approver",
        ),
        UniqueConstraint("org_id", "nonce", name="uq_command_approval_nonce"),
        Index("ix_command_approvals_decision", "org_id", "decision_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, nullable=False)
    incident_id: Mapped[str] = mapped_column(String(26), nullable=False)
    alert_id: Mapped[str] = mapped_column(String(26), nullable=False)
    decision_id: Mapped[str] = mapped_column(String(26), ForeignKey("alert_decisions.id"), nullable=False)
    approver_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    approver_role: Mapped[str] = mapped_column(String, nullable=False)
    key_id: Mapped[str] = mapped_column(String(26), nullable=False)
    nonce: Mapped[str] = mapped_column(String(26), nullable=False)
    signed_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
