"""add missing entity columns + fix enum types.

Revision ID: 0002a
Revises: 0001
Create Date: 2026-07-26

Adds 33 ORM-defined columns missing from migration 0001 across the 13 entity
tables, converts 6 native PG ENUM columns to VARCHAR (matching the ORM's
native_enum=False), drops the now-unused enum types, and adds tenant-aware
composite indexes on (org_id, incident_id) plus a time-series index on
observations(observed_at, org_id).
"""

from alembic import op
import sqlalchemy as sa

from app.models.enums import (
    AccessPolicy,
    CorroborationState,
    HypothesisStatus,
    ScenarioLabel,
    ScenarioStatus,
    SourceType,
)


revision = "0002a"
down_revision = "0001"
branch_labels = None
depends_on = None


_ENTITY_TABLES = [
    "hazards", "zones", "buildings", "road_segments", "bridges",
    "power_substations", "cell_towers", "hospitals", "shelters",
    "responders", "vehicles", "sensors", "operational_tasks",
]

# (table, column, sql_type, nullable) — every ORM field not in migration 0001.
_MISSING_COLUMNS: list[tuple[str, str, sa.types.TypeEngine, bool]] = [
    ("hazards", "hazard_type", sa.String(), False),
    ("hazards", "severity", sa.String(), True),
    ("zones", "name", sa.String(), False),
    ("zones", "zone_type", sa.String(), True),
    ("buildings", "name", sa.String(), True),
    ("buildings", "building_type", sa.String(), True),
    ("road_segments", "name", sa.String(), True),
    ("road_segments", "status", sa.String(), True),
    ("bridges", "name", sa.String(), True),
    ("bridges", "status", sa.String(), True),
    ("power_substations", "name", sa.String(), True),
    ("power_substations", "status", sa.String(), True),
    ("cell_towers", "name", sa.String(), True),
    ("cell_towers", "status", sa.String(), True),
    ("hospitals", "name", sa.String(), False),
    ("hospitals", "status", sa.String(), True),
    ("hospitals", "capacity", sa.Integer(), True),
    ("shelters", "name", sa.String(), False),
    ("shelters", "status", sa.String(), True),
    ("shelters", "capacity", sa.Integer(), True),
    ("shelters", "occupancy", sa.Integer(), True),
    ("responders", "name", sa.String(), True),
    ("responders", "role", sa.String(), True),
    ("responders", "status", sa.String(), True),
    ("vehicles", "name", sa.String(), True),
    ("vehicles", "vehicle_type", sa.String(), True),
    ("vehicles", "status", sa.String(), True),
    ("sensors", "name", sa.String(), True),
    ("sensors", "sensor_type", sa.String(), True),
    ("sensors", "status", sa.String(), True),
    ("operational_tasks", "title", sa.String(), False),
    ("operational_tasks", "status", sa.String(), True),
    ("operational_tasks", "priority", sa.String(), True),
]

# (table, column, enum_type_name, enum_class) — 6 native PG enum columns.
_ENUM_COLUMNS: list[tuple[str, str, str, type]] = [
    ("observations", "source_type", "sourcetype", SourceType),
    ("observations", "corroboration_state", "corroborationstate", CorroborationState),
    ("observations", "access_policy", "accesspolicy", AccessPolicy),
    ("hypotheses", "status", "hypothesisstatus", HypothesisStatus),
    ("scenarios", "label", "scenariolabel", ScenarioLabel),
    ("scenarios", "status", "scenariostatus", ScenarioStatus),
]


def upgrade() -> None:
    # 1. Add missing entity columns.
    for table, col, sql_type, nullable in _MISSING_COLUMNS:
        op.add_column(table, sa.Column(col, sql_type, nullable=nullable))

    # 2. Alter enum columns from native PG enum to VARCHAR (ORM uses native_enum=False).
    for table, col, enum_name, _ in _ENUM_COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {col} TYPE VARCHAR "
            f"USING {col}::text"
        )

    # 3. Drop the 6 native PG enum types (no longer referenced).
    for _, _, enum_name, _ in _ENUM_COLUMNS:
        op.execute(f"DROP TYPE {enum_name}")

    # 4. Tenant-aware composite indexes on (org_id, incident_id).
    for table in _ENTITY_TABLES:
        op.create_index(
            f"ix_{table}_org_incident", table, ["org_id", "incident_id"]
        )

    # 5. Time-series index on observations.
    op.create_index(
        "ix_observations_observed_org",
        "observations",
        ["observed_at", "org_id"],
    )


def downgrade() -> None:
    # 1. Drop time-series index.
    op.drop_index("ix_observations_observed_org", table_name="observations")

    # 2. Drop composite indexes.
    for table in reversed(_ENTITY_TABLES):
        op.drop_index(f"ix_{table}_org_incident", table_name=table)

    # 3. Recreate native PG enum types.
    for _, _, enum_name, enum_cls in _ENUM_COLUMNS:
        values = ", ".join(f"'{v.value}'" for v in enum_cls)
        op.execute(f"CREATE TYPE {enum_name} AS ENUM ({values})")

    # 4. Alter columns back to native PG enum.
    for table, col, enum_name, _ in _ENUM_COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {col} TYPE {enum_name} "
            f"USING {col}::{enum_name}"
        )

    # 5. Drop added columns.
    for table, col, _, _ in reversed(_MISSING_COLUMNS):
        op.drop_column(table, col)
