from __future__ import annotations

from geoalchemy2 import Geometry
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.types import JsonValue
from sqlalchemy import BigInteger, Float, ForeignKey, Index, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.models.events import (
    CANONICAL_SCHEMA_VERSION,
    ModelProvenance,
    RawEvent,
    ReviewStatus,
    Visibility,
    validate_ulid,
)


class NormalizedObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str = Field(default_factory=generate_ulid)
    raw_event_id: str
    org_id: str = Field(min_length=1)
    incident_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    phenomenon: str = Field(min_length=1)
    value: float | None = None
    unit: str | None = None
    source_time_ms: int = Field(ge=0)
    receipt_time_ms: int = Field(ge=0)
    sequence: int = Field(ge=1)
    payload_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    provenance: ModelProvenance | None = None
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    visibility: Visibility = Visibility.internal
    review_status: ReviewStatus = ReviewStatus.draft
    schema_version: str = CANONICAL_SCHEMA_VERSION

    @field_validator("observation_id", "raw_event_id")
    @classmethod
    def _validate_lineage_id(cls, value: str) -> str:
        return validate_ulid(value)

    @classmethod
    def from_raw_event(cls, event: RawEvent) -> NormalizedObservation:
        value = event.payload.get("value")
        numeric_value = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        phenomenon = event.payload.get("phenomenon")
        unit = event.payload.get("unit")
        return cls(
            raw_event_id=event.event_id,
            org_id=event.org_id,
            incident_id=event.incident_id,
            source_id=event.source_id,
            event_type=event.event_type,
            phenomenon=phenomenon if isinstance(phenomenon, str) and phenomenon else event.event_type,
            value=numeric_value,
            unit=unit if isinstance(unit, str) else None,
            source_time_ms=event.source_time_ms,
            receipt_time_ms=event.receipt_time_ms,
            sequence=event.sequence,
            payload_hash=event.canonical_hash(),
            provenance=event.provenance,
            attributes=event.payload,
            visibility=event.visibility,
            review_status=event.review_status,
            schema_version=event.schema_version,
        )


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        Index("ix_observations_source_id", "source_id"),
        Index("ix_observations_org_id", "org_id"),
        Index("ix_observations_incident_id", "incident_id"),
        Index("ix_observations_observed_at", "observed_at"),
        Index("ix_observations_corroboration", "corroboration_state"),
        Index("ix_observations_geometry", "geometry", postgresql_using="gist"),
    )

    observation_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    event_type: Mapped[str] = mapped_column(String)
    phenomenon: Mapped[str] = mapped_column(String)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry: Mapped[object] = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326))
    geometry_uncertainty: Mapped[float] = mapped_column(Float)
    observed_at: Mapped[int] = mapped_column(BigInteger)
    valid_from: Mapped[int] = mapped_column(BigInteger)
    valid_until: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    received_at: Mapped[int] = mapped_column(BigInteger)
    source_id: Mapped[str] = mapped_column(String)
    source_type: Mapped[SourceType] = mapped_column(SAEnum(SourceType, native_enum=False))
    collection_method: Mapped[str] = mapped_column(String)
    source_reliability: Mapped[float] = mapped_column(Float)
    freshness: Mapped[float] = mapped_column(Float)
    corroboration_state: Mapped[CorroborationState] = mapped_column(
        SAEnum(CorroborationState, native_enum=False)
    )
    model_uncertainty: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_flags: Mapped[dict] = mapped_column(JSONB)
    access_policy: Mapped[AccessPolicy] = mapped_column(SAEnum(AccessPolicy, native_enum=False))
    provenance_chain: Mapped[dict] = mapped_column(JSONB)
    raw_data_hash: Mapped[str] = mapped_column(String)
    model_version: Mapped[str | None] = mapped_column(String, nullable=True)
    supersedes: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("observations.observation_id"), nullable=True
    )
    duplicate_group: Mapped[str | None] = mapped_column(String(26), nullable=True)
    org_id: Mapped[str] = mapped_column(String)
    incident_id: Mapped[str] = mapped_column(String)
    raw_event_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    source_time_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    receipt_time_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(71), nullable=True)
    provenance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    visibility: Mapped[str | None] = mapped_column(String, nullable=True)
    review_status: Mapped[str | None] = mapped_column(String, nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String, nullable=True)


__all__ = ["NormalizedObservation", "Observation"]
