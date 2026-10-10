"""Hypothesis model — probabilistic claims about entities."""

from sqlalchemy import BigInteger, Enum as SAEnum, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import HypothesisStatus


class Hypothesis(Base):
    """A probabilistic claim about an entity, with supporting/contradicting evidence."""

    __tablename__ = "hypotheses"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, index=True)
    incident_id: Mapped[str] = mapped_column(String, index=True)
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str] = mapped_column(String(26))
    claim: Mapped[str] = mapped_column(Text)
    probability: Mapped[float] = mapped_column(Float)
    supporting_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    contradicting_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[HypothesisStatus] = mapped_column(
        SAEnum(HypothesisStatus, native_enum=False)
    )
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)
