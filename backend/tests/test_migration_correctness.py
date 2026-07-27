"""Integration test — migration correctness (schema matches models).

Verifies that every model's __tablename__ exists in the PostgreSQL
information_schema after `alembic upgrade head` (run by conftest.py).
Also checks key columns on critical tables to catch silent migration drift.

Uses the real PostgreSQL database via SessionLocal. No mocking.
"""

from __future__ import annotations

from sqlalchemy import text

from app.db import engine
from app.models import (
    Alert,
    Bridge,
    Building,
    CellTower,
    Decision,
    Event,
    GraphEdge,
    Hazard,
    Hospital,
    Hypothesis,
    Incident,
    Observation,
    OperationalTask,
    PowerSubstation,
    Recommendation,
    Responder,
    RoadSegment,
    Scenario,
    Sensor,
    Shelter,
    User,
    Vehicle,
    Zone,
)

# Every model that should have a table after migration 0001-0004.
EXPECTED_TABLES = sorted(
    {
        m.__tablename__
        for m in [
            Observation, Hazard, Zone, Building, RoadSegment, Bridge,
            PowerSubstation, CellTower, Hospital, Shelter, Responder,
            Vehicle, Sensor, OperationalTask, Decision, GraphEdge,
            Hypothesis, Scenario, Event, User, Incident, Alert,
            Recommendation,
        ]
    }
)

# Critical columns that must exist on specific tables.
EXPECTED_COLUMNS = {
    "observations": [
        "observation_id", "event_type", "phenomenon", "geometry",
        "observed_at", "source_id", "source_type", "org_id",
        "incident_id", "access_policy", "quality_flags",
    ],
    "events": [
        "id", "org_id", "incident_id", "actor", "action", "entity",
        "ts", "prev_hash", "hash",
    ],
    "incidents": [
        "id", "org_id", "title", "disaster_type", "severity", "status",
        "start_time", "created_at", "updated_at",
    ],
    "users": [
        "id", "email", "hashed_password", "role", "org_id", "created_at",
    ],
    "hypotheses": [
        "id", "org_id", "incident_id", "entity_type", "entity_id",
        "claim", "probability", "status",
    ],
}


def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t)"
        ),
        {"t": table_name},
    )
    return bool(result.scalar())


def _table_columns(conn, table_name: str) -> set[str]:
    result = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table_name},
    )
    return {row[0] for row in result}


def test_all_model_tables_exist() -> None:
    """Every model's __tablename__ must exist in the database schema."""
    with engine.connect() as conn:
        missing = [t for t in EXPECTED_TABLES if not _table_exists(conn, t)]
    assert not missing, (
        f"missing tables in schema: {missing}"
    )


def test_all_expected_columns_exist() -> None:
    """Critical tables must have all expected columns."""
    with engine.connect() as conn:
        for table, cols in EXPECTED_COLUMNS.items():
            actual = _table_columns(conn, table)
            missing = set(cols) - actual
            assert not missing, (
                f"table '{table}' missing columns: {missing}"
            )


def test_observations_has_geometry_column() -> None:
    """The observations table must have a PostGIS geometry column."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT type FROM geometry_columns "
                "WHERE f_table_name = 'observations' AND f_geometry_column = 'geometry'"
            )
        )
        row = result.first()
    assert row is not None, "observations.geometry not found in geometry_columns"
    assert row[0] == "GEOMETRY", f"expected GEOMETRY type, got {row[0]}"


def test_observations_has_gist_index() -> None:
    """The observations table must have a GiST index on geometry."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'observations' "
                "AND indexname = 'ix_observations_geometry'"
            )
        )
        row = result.first()
    assert row is not None, "ix_observations_geometry GiST index not found"


def test_idempotency_keys_table_exists() -> None:
    """The idempotency_keys table must exist (created by migration 0002b)."""
    with engine.connect() as conn:
        assert _table_exists(conn, "idempotency_keys")


def test_events_hash_chain_columns_exist() -> None:
    """The events table must have prev_hash and hash columns for the audit chain."""
    with engine.connect() as conn:
        cols = _table_columns(conn, "events")
    assert "prev_hash" in cols, "events.prev_hash column missing"
    assert "hash" in cols, "events.hash column missing"
