"""Source model — federated data source registry with ownership and access policies.

The ownership field is the core of the federated data fabric:
- owned: full data is stored locally (centralized)
- federated: queries forwarded to remote (NOT centralized)
- aggregated: only summaries received (partially centralized)

This prevents blind centralization of all data — federated sources keep
their data remote and are queried on demand.
"""

import enum

from sqlalchemy import BigInteger, Enum as SAEnum, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import AccessPolicy


class SourceKind(str, enum.Enum):
    """Type of federated data source."""

    cap_feed = "cap_feed"
    sensorthings = "sensorthings"
    ogc_features = "ogc_features"
    stac = "stac"
    hdx = "hdx"
    social_media = "social_media"
    citizen_report = "citizen_report"
    internal = "internal"


class SourceStatus(str, enum.Enum):
    """Operational status of a data source."""

    active = "active"
    error = "error"
    disabled = "disabled"


class Ownership(str, enum.Enum):
    """Ownership model — controls data centralization discipline."""

    owned = "owned"
    federated = "federated"
    aggregated = "aggregated"


class Source(Base):
    """A registered data source with ownership and access policy.

    The ownership field controls how data flows:
    - owned: full data is stored locally
    - federated: queries are forwarded to the remote source
    - aggregated: only summaries are received

    access_policy controls visibility of the source's data to consumers.
    """

    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    type: Mapped[SourceKind] = mapped_column(SAEnum(SourceKind, native_enum=False))
    provider: Mapped[str] = mapped_column(String)
    refresh_interval_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_success_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[SourceStatus] = mapped_column(SAEnum(SourceStatus, native_enum=False))
    config: Mapped[dict] = mapped_column(JSONB)
    access_policy: Mapped[AccessPolicy] = mapped_column(SAEnum(AccessPolicy, native_enum=False))
    ownership: Mapped[Ownership] = mapped_column(SAEnum(Ownership, native_enum=False))
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)


__all__ = ["Source", "SourceKind", "SourceStatus", "Ownership"]
