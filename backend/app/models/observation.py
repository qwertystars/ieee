"""Observation model — 23-field rich observation schema (plus id/org_id/incident_id)."""

from sqlalchemy import BigInteger, Enum as SAEnum, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry

from app.db import Base
from app.models.enums import (
    AccessPolicy,
    CorroborationState,
    SourceType,
)


class Observation(Base):
    """A single normalized observation from any source.

    23 fields as specified in the task contract (observation_id through
    duplicate_group), plus org_id and incident_id for tenancy scoping.
    """

    __tablename__ = "observations"
    __table_args__ = (
        Index("ix_observations_source_id", "source_id"),
        Index("ix_observations_org_id", "org_id"),
        Index("ix_observations_incident_id", "incident_id"),
        Index("ix_observations_observed_at", "observed_at"),
        Index("ix_observations_corroboration", "corroboration_state"),
        Index(
            "ix_observations_geometry",
            "geometry",
            postgresql_using="gist",
        ),
    )

    # 1. identity
    observation_id: Mapped[str] = mapped_column(String(26), primary_key=True)

    # 2-3. what was observed
    event_type: Mapped[str] = mapped_column(String)
    phenomenon: Mapped[str] = mapped_column(String)

    # 4-5. quantitative value
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)

    # 6-7. spatial
    geometry: Mapped[object] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326)
    )
    geometry_uncertainty: Mapped[float] = mapped_column(Float)

    # 8-10. temporal (UTC epoch ms)
    observed_at: Mapped[int] = mapped_column(BigInteger)
    valid_from: Mapped[int] = mapped_column(BigInteger)
    valid_until: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # 11. ingestion time
    received_at: Mapped[int] = mapped_column(BigInteger)

    # 12-15. provenance
    source_id: Mapped[str] = mapped_column(String)
    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, native_enum=False)
    )
    collection_method: Mapped[str] = mapped_column(String)
    source_reliability: Mapped[float] = mapped_column(Float)

    # 16-17. quality / fusion
    freshness: Mapped[float] = mapped_column(Float)
    corroboration_state: Mapped[CorroborationState] = mapped_column(
        SAEnum(CorroborationState, native_enum=False)
    )

    # 18-19. uncertainty
    model_uncertainty: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    quality_flags: Mapped[dict] = mapped_column(JSONB)

    # 20. access control
    access_policy: Mapped[AccessPolicy] = mapped_column(
        SAEnum(AccessPolicy, native_enum=False)
    )

    # 21-23. lineage
    provenance_chain: Mapped[dict] = mapped_column(JSONB)
    raw_data_hash: Mapped[str] = mapped_column(String)
    model_version: Mapped[str | None] = mapped_column(String, nullable=True)

    # supersedes / duplicate_group (part of lineage block)
    supersedes: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("observations.observation_id"),
        nullable=True,
    )
    duplicate_group: Mapped[str | None] = mapped_column(
        String(26), nullable=True
    )

    # tenancy
    org_id: Mapped[str] = mapped_column(String)
    incident_id: Mapped[str] = mapped_column(String)
