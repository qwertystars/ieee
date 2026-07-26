"""Provenance types — DecisionProvenance model + ProvenanceInput dataclass.

Each provenance entry is hash-chained per recommendation_id (same pattern as
T3's events table). The chain provides tamper evidence: modifying any row
breaks the chain at that point.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import BigInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# The 10 required provenance fields for every decision (T49 spec).
REQUIRED_FIELDS: tuple[str, ...] = (
    "input_observation_ids",
    "data_versions",
    "model_versions",
    "optimization_parameters",
    "scenario_set",
    "constraints",
    "generated_alternatives",
    "operator_decision",
    "override_reason",
    "execution_outcome",
)


@dataclass(frozen=True, slots=True)
class ProvenanceInput:
    """The 10 provenance fields recorded for every recommendation.

    Grouping the 10 fields into a value object keeps ``record_decision`` to
    4 parameters (db, org_id, recommendation_id, provenance_input) instead
    of 13. All fields are required — ``None`` is rejected in ``__post_init__``.
    For unknown values at decision time, pass empty containers / empty string.
    """

    input_observation_ids: list[object]
    data_versions: dict[str, object]
    model_versions: dict[str, object]
    optimization_parameters: dict[str, object]
    scenario_set: list[object]
    constraints: dict[str, object]
    generated_alternatives: list[object]
    operator_decision: dict[str, object]
    override_reason: str
    execution_outcome: dict[str, object]

    def __post_init__(self) -> None:
        for name in REQUIRED_FIELDS:
            if getattr(self, name) is None:
                raise ValueError(f"provenance field '{name}' is required (got None)")


class DecisionProvenance(Base):
    """A single provenance entry in the hash-chained decision log.

    Each row stores all 10 provenance fields plus ``prev_hash`` and ``hash``
    for tamper-evident chaining. The chain is scoped per recommendation_id.
    """

    __tablename__ = "decision_provenance"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, index=True)
    recommendation_id: Mapped[str] = mapped_column(String, index=True)

    input_observation_ids: Mapped[list] = mapped_column(JSONB)
    data_versions: Mapped[dict] = mapped_column(JSONB)
    model_versions: Mapped[dict] = mapped_column(JSONB)
    optimization_parameters: Mapped[dict] = mapped_column(JSONB)
    scenario_set: Mapped[list] = mapped_column(JSONB)
    constraints: Mapped[dict] = mapped_column(JSONB)
    generated_alternatives: Mapped[list] = mapped_column(JSONB)
    operator_decision: Mapped[dict] = mapped_column(JSONB)
    override_reason: Mapped[str] = mapped_column(Text)
    execution_outcome: Mapped[dict] = mapped_column(JSONB)

    ts: Mapped[int] = mapped_column(BigInteger)
    prev_hash: Mapped[str] = mapped_column(String)
    hash: Mapped[str] = mapped_column(String)


__all__ = [
    "REQUIRED_FIELDS",
    "ProvenanceInput",
    "DecisionProvenance",
]
