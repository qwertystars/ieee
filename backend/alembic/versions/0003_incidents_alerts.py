"""add incidents, alerts, recommendations tables.

Revision ID: 0003
Revises: 0002b
Create Date: 2026-07-26

Creates 3 new domain tables: incidents (top-level disaster event), alerts
(warnings scoped to an incident), and recommendations (action suggestions
scoped to an incident, optionally linked to an alert). All carry org_id
tenancy, ULID primary keys, and BigInteger UTC epoch millisecond timestamps.
GiST spatial indexes on geometry/area; composite (org_id, incident_id)
indexes on alerts and recommendations.
"""

import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0003"
down_revision = "0002b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. incidents — top-level disaster event.
    op.create_table(
        "incidents",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("disaster_type", sa.String, nullable=False),
        sa.Column("severity", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("declaration_level", sa.String, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "geometry",
            Geometry(geometry_type="GEOMETRY", srid=4326),
            nullable=True,
        ),
        sa.Column("start_time", sa.BigInteger, nullable=False),
        sa.Column("expected_end", sa.BigInteger, nullable=True),
        sa.Column("config", JSONB, nullable=True),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
    )
    op.create_index("ix_incidents_org_id", "incidents", ["org_id"])
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_severity", "incidents", ["severity"])
    op.create_index("ix_incidents_start_time", "incidents", ["start_time"])
    op.create_index(
        "ix_incidents_geometry", "incidents", ["geometry"], postgresql_using="gist"
    )

    # 2. alerts — warning scoped to an incident.
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column(
            "incident_id", sa.String(26), sa.ForeignKey("incidents.id"), nullable=False
        ),
        sa.Column("alert_type", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column(
            "area",
            Geometry(geometry_type="GEOMETRY", srid=4326),
            nullable=True,
        ),
        sa.Column("severity", sa.String, nullable=False),
        sa.Column("recommended_action", sa.Text, nullable=True),
        sa.Column("confidence_vector", JSONB, nullable=True),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("created_by", sa.String, nullable=False),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        sa.Column("reviewed_by", sa.String, nullable=True),
        sa.Column("review_rationale", sa.Text, nullable=True),
        sa.Column("reviewed_at", sa.BigInteger, nullable=True),
    )
    op.create_index("ix_alerts_org_id", "alerts", ["org_id"])
    op.create_index("ix_alerts_incident_id", "alerts", ["incident_id"])
    op.create_index("ix_alerts_org_incident", "alerts", ["org_id", "incident_id"])
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index(
        "ix_alerts_area", "alerts", ["area"], postgresql_using="gist"
    )

    # 3. recommendations — action suggestion scoped to an incident + optional alert.
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column(
            "incident_id",
            sa.String(26),
            sa.ForeignKey("incidents.id"),
            nullable=False,
        ),
        sa.Column(
            "alert_id", sa.String(26), sa.ForeignKey("alerts.id"), nullable=True
        ),
        sa.Column("recommendation_type", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("supporting_evidence", JSONB, nullable=True),
        sa.Column("contradicting_evidence", JSONB, nullable=True),
        sa.Column("confidence_vector", JSONB, nullable=True),
        sa.Column("urgency", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("assigned_team_id", sa.String, nullable=True),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
    )
    op.create_index("ix_recommendations_org_id", "recommendations", ["org_id"])
    op.create_index(
        "ix_recommendations_incident_id", "recommendations", ["incident_id"]
    )
    op.create_index(
        "ix_recommendations_org_incident",
        "recommendations",
        ["org_id", "incident_id"],
    )
    op.create_index("ix_recommendations_status", "recommendations", ["status"])
    op.create_index("ix_recommendations_urgency", "recommendations", ["urgency"])


def downgrade() -> None:
    op.drop_table("recommendations")
    op.drop_table("alerts")
    op.drop_table("incidents")
