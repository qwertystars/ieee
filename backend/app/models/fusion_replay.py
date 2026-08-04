"""Durable records for deterministic fusion replays."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FusionReplayRun(Base):
    """One immutable replay execution and its pinned implementation lineage."""

    __tablename__ = "fusion_replay_runs"
    __table_args__ = (
        Index("ix_fusion_replay_runs_org_incident", "org_id", "incident_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, nullable=False)
    incident_id: Mapped[str] = mapped_column(String, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String, nullable=False)
    config_version: Mapped[str] = mapped_column(String, nullable=False)
    runtime_version: Mapped[str] = mapped_column(String, nullable=False)
    library_versions: Mapped[list] = mapped_column(JSONB, nullable=False)
    model_versions: Mapped[list] = mapped_column(JSONB, nullable=False)
    serialization_version: Mapped[str] = mapped_column(String, nullable=False)
    lineage: Mapped[dict] = mapped_column(JSONB, nullable=False)
    float_tolerance: Mapped[float] = mapped_column(nullable=False)
    lineage_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    as_of_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    decision_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)


class FusionReplayInputRecord(Base):
    """Canonical input event retained for one replay run."""

    __tablename__ = "fusion_replay_inputs"
    __table_args__ = (
        UniqueConstraint("run_id", "ordinal", name="uq_fusion_replay_inputs_ordinal"),
        Index("ix_fusion_replay_inputs_run", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("fusion_replay_runs.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    event_id: Mapped[str] = mapped_column(String(26), nullable=False)
    canonical_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    canonical_event: Mapped[dict] = mapped_column(JSONB, nullable=False)


class FusionReplayOutputRecord(Base):
    """Canonical output retained without overwriting another lineage."""

    __tablename__ = "fusion_replay_outputs"
    __table_args__ = (
        UniqueConstraint("run_id", "output_type", "output_key", name="uq_fusion_replay_outputs_key"),
        Index("ix_fusion_replay_outputs_run", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("fusion_replay_runs.id", ondelete="CASCADE"), nullable=False
    )
    output_type: Mapped[str] = mapped_column(String, nullable=False)
    output_key: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    decision_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    lineage_hash: Mapped[str] = mapped_column(String(71), nullable=False)


class FusionReplayErrorRecord(Base):
    """Structured failure retained instead of being swallowed or lost."""

    __tablename__ = "fusion_replay_errors"
    __table_args__ = (Index("ix_fusion_replay_errors_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("fusion_replay_runs.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String, nullable=False)
    event_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    error_type: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)


__all__ = [
    "FusionReplayErrorRecord",
    "FusionReplayInputRecord",
    "FusionReplayOutputRecord",
    "FusionReplayRun",
]
