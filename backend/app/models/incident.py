"""Incident model — a disaster event being tracked and responded to.

An Incident is the top-level container for alerts, recommendations, observations,
and entity data within a response effort. It is org-scoped (org_id) and carries
an optional geometry (e.g. the affected area boundary).
"""

from sqlalchemy import BigInteger, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry

from app.db import Base


class Incident(Base):
    """A disaster incident being tracked by the platform."""

    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_org_id", "org_id"),
        Index("ix_incidents_status", "status"),
        Index("ix_incidents_severity", "severity"),
        Index("ix_incidents_start_time", "start_time"),
        Index("ix_incidents_geometry", "geometry", postgresql_using="gist"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    disaster_type: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="active")
    declaration_level: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True
    )
    start_time: Mapped[int] = mapped_column(BigInteger)
    expected_end: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)
