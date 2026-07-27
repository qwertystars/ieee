"""init schema — observations, entities, graph_edges, hypotheses, scenarios, events.

Revision ID: 0001
Revises:
Create Date: 2026-07-18
"""

import sqlalchemy as sa
from geoalchemy2 import Geometry

from alembic import op
from app.models.enums import (
    AccessPolicy,
    CorroborationState,
    HypothesisStatus,
    ScenarioLabel,
    ScenarioStatus,
    SourceType,
)

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    op.execute("CREATE EXTENSION IF NOT EXISTS age;")
    op.execute("CREATE EXTENSION IF NOT EXISTS h3;")

    # observations
    op.create_table(
        "observations",
        sa.Column("observation_id", sa.String(26), primary_key=True),
        sa.Column("event_type", sa.String, nullable=False),
        sa.Column("phenomenon", sa.String, nullable=False),
        sa.Column("value", sa.Float, nullable=True),
        sa.Column("unit", sa.String, nullable=True),
        sa.Column("geometry", Geometry(geometry_type="GEOMETRY", srid=4326), nullable=False),
        sa.Column("geometry_uncertainty", sa.Float, nullable=False),
        sa.Column("observed_at", sa.BigInteger, nullable=False),
        sa.Column("valid_from", sa.BigInteger, nullable=False),
        sa.Column("valid_until", sa.BigInteger, nullable=True),
        sa.Column("received_at", sa.BigInteger, nullable=False),
        sa.Column("source_id", sa.String, nullable=False),
        sa.Column("source_type", sa.Enum(SourceType, name="sourcetype"), nullable=False),
        sa.Column("collection_method", sa.String, nullable=False),
        sa.Column("source_reliability", sa.Float, nullable=False),
        sa.Column("freshness", sa.Float, nullable=False),
        sa.Column("corroboration_state", sa.Enum(CorroborationState, name="corroborationstate"), nullable=False),
        sa.Column("model_uncertainty", sa.Float, nullable=True),
        sa.Column("quality_flags", sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column("access_policy", sa.Enum(AccessPolicy, name="accesspolicy"), nullable=False),
        sa.Column("provenance_chain", sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column("raw_data_hash", sa.String, nullable=False),
        sa.Column("model_version", sa.String, nullable=True),
        sa.Column("supersedes", sa.String(26), nullable=True),
        sa.Column("duplicate_group", sa.String(26), nullable=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("incident_id", sa.String, nullable=False),
        sa.ForeignKeyConstraint(["supersedes"], ["observations.observation_id"]),
    )
    op.create_index("ix_observations_source_id", "observations", ["source_id"])
    op.create_index("ix_observations_org_id", "observations", ["org_id"])
    op.create_index("ix_observations_incident_id", "observations", ["incident_id"])
    op.create_index("ix_observations_observed_at", "observations", ["observed_at"])
    op.create_index("ix_observations_corroboration", "observations", ["corroboration_state"])
    op.create_index("ix_observations_geometry", "observations", ["geometry"], postgresql_using="gist")

    # entities with geometry
    _entity_tables = [
        "hazards", "zones", "buildings", "road_segments", "bridges",
        "power_substations", "cell_towers", "hospitals", "shelters",
        "responders", "vehicles", "sensors", "operational_tasks",
    ]
    for table in _entity_tables:
        op.create_table(
            table,
            sa.Column("id", sa.String(26), primary_key=True),
            sa.Column("org_id", sa.String, nullable=False),
            sa.Column("incident_id", sa.String, nullable=False),
            sa.Column("created_at", sa.BigInteger, nullable=False),
            sa.Column("updated_at", sa.BigInteger, nullable=False),
            sa.Column("geometry", Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True),
            sa.Column("properties", sa.dialects.postgresql.JSONB, nullable=True),
        )
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])
        op.create_index(f"ix_{table}_incident_id", table, ["incident_id"])
        op.create_index(f"ix_{table}_geometry", table, ["geometry"], postgresql_using="gist")

    # decisions (no geometry)
    op.create_table(
        "decisions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("incident_id", sa.String, nullable=False),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("rationale", sa.String, nullable=True),
        sa.Column("properties", sa.dialects.postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_decisions_org_id", "decisions", ["org_id"])
    op.create_index("ix_decisions_incident_id", "decisions", ["incident_id"])

    # graph_edges
    op.create_table(
        "graph_edges",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source_type", sa.String, nullable=False),
        sa.Column("source_id", sa.String(26), nullable=False),
        sa.Column("edge_type", sa.String, nullable=False),
        sa.Column("target_type", sa.String, nullable=False),
        sa.Column("target_id", sa.String(26), nullable=False),
        sa.Column("properties", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("valid_from", sa.BigInteger, nullable=False),
        sa.Column("valid_until", sa.BigInteger, nullable=True),
    )
    op.create_index("ix_graph_edges_source", "graph_edges", ["source_type", "source_id"])
    op.create_index("ix_graph_edges_target", "graph_edges", ["target_type", "target_id"])
    op.create_index("ix_graph_edges_edge_type", "graph_edges", ["edge_type"])

    # hypotheses
    op.create_table(
        "hypotheses",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("incident_id", sa.String, nullable=False),
        sa.Column("entity_type", sa.String, nullable=False),
        sa.Column("entity_id", sa.String(26), nullable=False),
        sa.Column("claim", sa.Text, nullable=False),
        sa.Column("probability", sa.Float, nullable=False),
        sa.Column("supporting_evidence", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("contradicting_evidence", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("status", sa.Enum(HypothesisStatus, name="hypothesisstatus"), nullable=False),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
    )
    op.create_index("ix_hypotheses_org_id", "hypotheses", ["org_id"])
    op.create_index("ix_hypotheses_incident_id", "hypotheses", ["incident_id"])

    # scenarios
    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("incident_id", sa.String, nullable=False),
        sa.Column("label", sa.Enum(ScenarioLabel, name="scenariolabel"), nullable=False),
        sa.Column("probability", sa.Float, nullable=False),
        sa.Column("params", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("result_geojson", sa.Text, nullable=True),
        sa.Column("status", sa.Enum(ScenarioStatus, name="scenariostatus"), nullable=False),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("completed_at", sa.BigInteger, nullable=True),
    )
    op.create_index("ix_scenarios_org_id", "scenarios", ["org_id"])
    op.create_index("ix_scenarios_incident_id", "scenarios", ["incident_id"])

    # events (hash-chained audit)
    op.create_table(
        "events",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("incident_id", sa.String, nullable=False),
        sa.Column("actor", sa.String, nullable=False),
        sa.Column("action", sa.String, nullable=False),
        sa.Column("entity", sa.String, nullable=False),
        sa.Column("before", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("after", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("ts", sa.BigInteger, nullable=False),
        sa.Column("prev_hash", sa.String, nullable=True),
        sa.Column("hash", sa.String, nullable=False),
    )
    op.create_index("ix_events_org_id", "events", ["org_id"])
    op.create_index("ix_events_incident_id", "events", ["incident_id"])


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("scenarios")
    op.drop_table("hypotheses")
    op.drop_table("graph_edges")
    op.drop_table("decisions")
    for table in reversed([
        "operational_tasks", "sensors", "vehicles", "responders", "shelters",
        "hospitals", "cell_towers", "power_substations", "bridges",
        "road_segments", "buildings", "zones", "hazards",
    ]):
        op.drop_table(table)
    op.drop_table("observations")
