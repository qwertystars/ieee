"""Core domain entities for the disaster response platform.

Each entity carries ULID id, org_id/incident_id tenancy, and BigInteger
timestamps. Entities with a spatial footprint use a GeoAlchemy2 Geometry
column (srid=4326). GiST indexes are created in the Alembic migration.
"""

from sqlalchemy import BigInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry

from app.db import Base


class _EntityMixin:
    """Common columns shared by all spatial/operational entities."""

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, index=True)
    incident_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)


_GEO = Geometry(geometry_type="GEOMETRY", srid=4326)


class Hazard(_EntityMixin, Base):
    """A hazard zone (flood, fire, chemical, etc.)."""

    __tablename__ = "hazards"

    hazard_type: Mapped[str] = mapped_column(String)
    severity: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry: Mapped[object] = mapped_column(_GEO)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Zone(_EntityMixin, Base):
    """An administrative or operational zone polygon."""

    __tablename__ = "zones"

    name: Mapped[str] = mapped_column(String)
    zone_type: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry: Mapped[object] = mapped_column(_GEO)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Building(_EntityMixin, Base):
    """A building footprint."""

    __tablename__ = "buildings"

    name: Mapped[str | None] = mapped_column(String, nullable=True)
    building_type: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry: Mapped[object] = mapped_column(_GEO)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class RoadSegment(_EntityMixin, Base):
    """A road segment (linestring) with status."""

    __tablename__ = "road_segments"

    name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry: Mapped[object] = mapped_column(_GEO)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Bridge(_EntityMixin, Base):
    """A bridge structure (point or linestring)."""

    __tablename__ = "bridges"

    name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry: Mapped[object] = mapped_column(_GEO)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class PowerSubstation(_EntityMixin, Base):
    """An electrical power substation."""

    __tablename__ = "power_substations"

    name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry: Mapped[object] = mapped_column(_GEO)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class CellTower(_EntityMixin, Base):
    """A cellular communications tower."""

    __tablename__ = "cell_towers"

    name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry: Mapped[object] = mapped_column(_GEO)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Hospital(_EntityMixin, Base):
    """A hospital facility."""

    __tablename__ = "hospitals"

    name: Mapped[str] = mapped_column(String)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    capacity: Mapped[int | None] = mapped_column(nullable=True)
    geometry: Mapped[object] = mapped_column(_GEO)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Shelter(_EntityMixin, Base):
    """An emergency shelter."""

    __tablename__ = "shelters"

    name: Mapped[str] = mapped_column(String)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    capacity: Mapped[int | None] = mapped_column(nullable=True)
    occupancy: Mapped[int | None] = mapped_column(nullable=True)
    geometry: Mapped[object] = mapped_column(_GEO)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Responder(_EntityMixin, Base):
    """A human responder (point location)."""

    __tablename__ = "responders"

    name: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry: Mapped[object] = mapped_column(_GEO)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Vehicle(_EntityMixin, Base):
    """A response vehicle (point location)."""

    __tablename__ = "vehicles"

    name: Mapped[str | None] = mapped_column(String, nullable=True)
    vehicle_type: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry: Mapped[object] = mapped_column(_GEO)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Sensor(_EntityMixin, Base):
    """A fixed or mobile sensor (stream gauge, weather station, etc.)."""

    __tablename__ = "sensors"

    name: Mapped[str | None] = mapped_column(String, nullable=True)
    sensor_type: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry: Mapped[object] = mapped_column(_GEO)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class OperationalTask(_EntityMixin, Base):
    """A task assigned to responders (point location)."""

    __tablename__ = "operational_tasks"

    title: Mapped[str] = mapped_column(String)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    priority: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry: Mapped[object | None] = mapped_column(_GEO, nullable=True)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Decision(_EntityMixin, Base):
    """A decision record (no geometry — purely a log of choices made)."""

    __tablename__ = "decisions"

    title: Mapped[str] = mapped_column(String)
    rationale: Mapped[str | None] = mapped_column(String, nullable=True)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
