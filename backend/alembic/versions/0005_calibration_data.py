"""add calibration_data table for conformal calibration samples.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-28

Creates the calibration_data table used by the calibration-validation
harness (T8). Each row stores one calibration sample (a feature vector X
and target y) scoped to an incident, model, and optional H3 zone. The
calibration route reads stored samples, fits a ConformalCalibrator, and
returns prediction intervals + Brier/ECE/coverage metrics.

Carries org_id tenancy, ULID primary key, BigInteger UTC epoch ms
timestamp, and a composite (org_id, incident_id) index for efficient
per-incident retrieval.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calibration_data",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column(
            "incident_id",
            sa.String(26),
            sa.ForeignKey("incidents.id"),
            nullable=False,
        ),
        sa.Column("model_id", sa.String, nullable=False),
        sa.Column("h3_zone", sa.String, nullable=True),
        sa.Column("X", JSONB, nullable=False),
        sa.Column("y", JSONB, nullable=False),
        sa.Column("created_at", sa.BigInteger, nullable=False),
    )
    op.create_index("ix_calibration_data_org_id", "calibration_data", ["org_id"])
    op.create_index(
        "ix_calibration_data_incident_id", "calibration_data", ["incident_id"]
    )
    op.create_index(
        "ix_calibration_data_org_incident",
        "calibration_data",
        ["org_id", "incident_id"],
    )
    op.create_index("ix_calibration_data_model_id", "calibration_data", ["model_id"])


def downgrade() -> None:
    op.drop_table("calibration_data")
