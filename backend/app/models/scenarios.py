"""Scenario model — best/expected/worst branch simulations."""

from sqlalchemy import BigInteger, Enum as SAEnum, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import ScenarioLabel, ScenarioStatus


class Scenario(Base):
    """A scenario simulation (best/expected/worst) with parameters and results."""

    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, index=True)
    incident_id: Mapped[str] = mapped_column(String, index=True)
    label: Mapped[ScenarioLabel] = mapped_column(
        SAEnum(ScenarioLabel, native_enum=False)
    )
    probability: Mapped[float] = mapped_column(Float)
    params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_geojson: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ScenarioStatus] = mapped_column(
        SAEnum(ScenarioStatus, native_enum=False)
    )
    created_at: Mapped[int] = mapped_column(BigInteger)
    completed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
