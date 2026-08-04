from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from pydantic.types import JsonValue
from sqlalchemy import BigInteger, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.lib.ulid import generate_ulid

CANONICAL_SCHEMA_VERSION = "1.0"
LEGACY_SERIALIZATION_VERSION = "legacy-v1"
CANONICAL_SERIALIZATION_VERSION = "rfc8785-v2"
_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def is_schema_compatible(version: str, supported: str = CANONICAL_SCHEMA_VERSION) -> bool:
    version_major, version_separator, version_minor = version.partition(".")
    supported_major, supported_separator, supported_minor = supported.partition(".")
    return (
        version_separator == "."
        and supported_separator == "."
        and version_major.isdigit()
        and version_minor.isdigit()
        and supported_major.isdigit()
        and supported_minor.isdigit()
        and int(version_major) == int(supported_major)
    )


def validate_ulid(value: str) -> str:
    if _ULID_RE.fullmatch(value) is None:
        raise ValueError("value must be an uppercase ULID")
    return value


class Visibility(StrEnum):
    public = "public"
    internal = "internal"
    sensitive = "sensitive"


class ReviewStatus(StrEnum):
    draft = "draft"
    reviewed = "reviewed"
    official = "official"


class ModelProvenance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    feature_schema_version: str = Field(min_length=1)
    preprocessing_version: str = Field(min_length=1)
    calibration_version: str = Field(min_length=1)
    output_schema_version: str = Field(min_length=1)


class RawEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(default_factory=generate_ulid)
    org_id: str = Field(min_length=1)
    incident_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    source_time_ms: StrictInt = Field(ge=0)
    receipt_time_ms: StrictInt = Field(ge=0)
    sequence: int = Field(ge=1)
    payload: dict[str, JsonValue]
    provenance: ModelProvenance | None = None
    visibility: Visibility = Visibility.internal
    review_status: ReviewStatus = ReviewStatus.draft
    schema_version: str = CANONICAL_SCHEMA_VERSION

    @field_validator("event_id")
    @classmethod
    def _validate_event_id(cls, value: str) -> str:
        return validate_ulid(value)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        major, separator, minor = value.partition(".")
        if separator != "." or not major.isdigit() or not minor.isdigit():
            raise ValueError("schema_version must be MAJOR.MINOR")
        return value

    def canonical_bytes(self) -> bytes:
        from app.lib.audit import canonical_json_bytes

        return canonical_json_bytes(self.model_dump(mode="json"))

    def canonical_hash(self) -> str:
        from app.lib.audit import sha256_hex

        return f"sha256:{sha256_hex(self.canonical_bytes())}"


class Prediction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prediction_id: str = Field(default_factory=generate_ulid)
    org_id: str = Field(min_length=1)
    incident_id: str = Field(min_length=1)
    source_event_ids: tuple[str, ...] = Field(min_length=1)
    source_observation_ids: tuple[str, ...] = ()
    generated_at_ms: int = Field(ge=0)
    valid_from_ms: int = Field(ge=0)
    valid_until_ms: int | None = Field(default=None, ge=0)
    output: dict[str, JsonValue]
    provenance: ModelProvenance
    visibility: Visibility = Visibility.internal
    review_status: ReviewStatus = ReviewStatus.draft
    schema_version: str = CANONICAL_SCHEMA_VERSION

    @field_validator("prediction_id")
    @classmethod
    def _validate_prediction_id(cls, value: str) -> str:
        return validate_ulid(value)

    @field_validator("source_event_ids", "source_observation_ids")
    @classmethod
    def _validate_source_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(validate_ulid(value) for value in values)


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str = Field(default_factory=generate_ulid)
    org_id: str = Field(min_length=1)
    incident_id: str = Field(min_length=1)
    input_event_ids: tuple[str, ...] = ()
    input_observation_ids: tuple[str, ...] = ()
    prediction_ids: tuple[str, ...] = ()
    decision_type: str = Field(min_length=1)
    decision: dict[str, JsonValue]
    rationale: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    decided_at_ms: int = Field(ge=0)
    provenance: ModelProvenance | None = None
    visibility: Visibility = Visibility.internal
    review_status: ReviewStatus = ReviewStatus.draft
    schema_version: str = CANONICAL_SCHEMA_VERSION

    @field_validator("decision_id")
    @classmethod
    def _validate_decision_id(cls, value: str) -> str:
        return validate_ulid(value)

    @field_validator("input_event_ids", "input_observation_ids", "prediction_ids")
    @classmethod
    def _validate_input_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(validate_ulid(value) for value in values)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_org_sequence", "org_id", "sequence"),
        UniqueConstraint("org_id", "sequence", name="uq_events_org_sequence"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, index=True)
    incident_id: Mapped[str] = mapped_column(String, index=True)
    actor: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    entity: Mapped[str] = mapped_column(String)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ts: Mapped[int] = mapped_column(BigInteger)
    prev_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    hash: Mapped[str] = mapped_column(String)
    event_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source_time_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    receipt_time_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    provenance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    visibility: Mapped[str | None] = mapped_column(String, nullable=True)
    review_status: Mapped[str | None] = mapped_column(String, nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String, nullable=True)
    serialization_version: Mapped[str] = mapped_column(
        String, nullable=False, default=CANONICAL_SERIALIZATION_VERSION
    )


class RawEventRecord(Base):
    __tablename__ = "raw_events"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "source_id", "external_id", name="uq_raw_events_source_external"
        ),
        Index("ix_raw_events_org_incident", "org_id", "incident_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, index=True)
    incident_id: Mapped[str] = mapped_column(String, index=True)
    source_id: Mapped[str] = mapped_column(String)
    external_id: Mapped[str] = mapped_column(String)
    event_type: Mapped[str] = mapped_column(String)
    source_time_ms: Mapped[int] = mapped_column(BigInteger)
    receipt_time_ms: Mapped[int] = mapped_column(BigInteger)
    sequence: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict] = mapped_column(JSONB)
    provenance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    visibility: Mapped[str] = mapped_column(String)
    review_status: Mapped[str] = mapped_column(String)
    schema_version: Mapped[str] = mapped_column(String)
    canonical_hash: Mapped[str] = mapped_column(String(71))


class PredictionRecord(Base):
    __tablename__ = "predictions"
    __table_args__ = (Index("ix_predictions_org_incident", "org_id", "incident_id"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, index=True)
    incident_id: Mapped[str] = mapped_column(String, index=True)
    source_event_ids: Mapped[list] = mapped_column(JSONB)
    source_observation_ids: Mapped[list] = mapped_column(JSONB)
    generated_at_ms: Mapped[int] = mapped_column(BigInteger)
    valid_from_ms: Mapped[int] = mapped_column(BigInteger)
    valid_until_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    output: Mapped[dict] = mapped_column(JSONB)
    provenance: Mapped[dict] = mapped_column(JSONB)
    visibility: Mapped[str] = mapped_column(String)
    review_status: Mapped[str] = mapped_column(String)
    schema_version: Mapped[str] = mapped_column(String)
    canonical_hash: Mapped[str] = mapped_column(String(71))


class CanonicalDecisionRecord(Base):
    __tablename__ = "canonical_decisions"
    __table_args__ = (Index("ix_canonical_decisions_org_incident", "org_id", "incident_id"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, index=True)
    incident_id: Mapped[str] = mapped_column(String, index=True)
    input_event_ids: Mapped[list] = mapped_column(JSONB)
    input_observation_ids: Mapped[list] = mapped_column(JSONB)
    prediction_ids: Mapped[list] = mapped_column(JSONB)
    decision_type: Mapped[str] = mapped_column(String)
    decision: Mapped[dict] = mapped_column(JSONB)
    rationale: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String)
    decided_at_ms: Mapped[int] = mapped_column(BigInteger)
    provenance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    visibility: Mapped[str] = mapped_column(String)
    review_status: Mapped[str] = mapped_column(String)
    schema_version: Mapped[str] = mapped_column(String)
    canonical_hash: Mapped[str] = mapped_column(String(71))


class AuditChainHead(Base):
    __tablename__ = "audit_chain_heads"

    org_id: Mapped[str] = mapped_column(String, primary_key=True)
    last_sequence: Mapped[int] = mapped_column(BigInteger)
    last_hash: Mapped[str] = mapped_column(String)
    updated_at: Mapped[int] = mapped_column(BigInteger)


__all__ = [
    "CANONICAL_SCHEMA_VERSION",
    "CANONICAL_SERIALIZATION_VERSION",
    "LEGACY_SERIALIZATION_VERSION",
    "AuditChainHead",
    "CanonicalDecisionRecord",
    "Decision",
    "Event",
    "ModelProvenance",
    "Prediction",
    "PredictionRecord",
    "RawEvent",
    "RawEventRecord",
    "ReviewStatus",
    "Visibility",
    "is_schema_compatible",
    "validate_ulid",
]
