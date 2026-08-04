from sqlalchemy import BigInteger, Boolean, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EmergencyOverrideRecord(Base):
    __tablename__ = "emergency_overrides"
    __table_args__ = (
        Index("ix_emergency_overrides_org_target", "org_id", "target_user_id"),
        Index("ix_emergency_overrides_expiry", "expires_at_ms"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, nullable=False)
    target_user_id: Mapped[str] = mapped_column(String(26), nullable=False)
    granted_by: Mapped[str] = mapped_column(String(26), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    granted_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    revoked_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class CredentialState(Base):
    __tablename__ = "credential_states"
    __table_args__ = (
        UniqueConstraint("credential_hash", name="uq_credential_states_hash"),
        Index("ix_credential_states_org_expiry", "org_id", "expires_at_ms"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str | None] = mapped_column(String, nullable=True)
    credential_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)


class QuarantineRecord(Base):
    __tablename__ = "coordination_quarantine"
    __table_args__ = (
        Index("ix_coordination_quarantine_org_subject", "org_id", "subject_id"),
        Index("ix_coordination_quarantine_expiry", "expires_at_ms"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, nullable=False)
    subject_type: Mapped[str] = mapped_column(String, nullable=False)
    subject_id: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    released_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class EvaluationJob(Base):
    __tablename__ = "evaluation_jobs"
    __table_args__ = (
        Index("ix_evaluation_jobs_org_status", "org_id", "status"),
        Index("ix_evaluation_jobs_expiry", "expires_at_ms"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[str] = mapped_column(String(26), nullable=False)
    job_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    claimed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
