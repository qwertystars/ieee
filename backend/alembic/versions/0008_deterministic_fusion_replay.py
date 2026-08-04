"""Persist deterministic fusion replay lineage, inputs, outputs, and errors."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fusion_replay_runs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("incident_id", sa.String(), nullable=False),
        sa.Column("algorithm_version", sa.String(), nullable=False),
        sa.Column("config_version", sa.String(), nullable=False),
        sa.Column("runtime_version", sa.String(), nullable=False),
        sa.Column("library_versions", JSONB(), nullable=False),
        sa.Column("model_versions", JSONB(), nullable=False),
        sa.Column("serialization_version", sa.String(), nullable=False),
        sa.Column("lineage_hash", sa.String(71), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("as_of_ms", sa.BigInteger(), nullable=False),
        sa.Column("input_hash", sa.String(71), nullable=False),
        sa.Column("decision_hash", sa.String(71), nullable=False),
        sa.Column("output_hash", sa.String(71), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "ix_fusion_replay_runs_org_incident",
        "fusion_replay_runs",
        ["org_id", "incident_id"],
    )
    op.create_table(
        "fusion_replay_inputs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("run_id", sa.String(26), sa.ForeignKey("fusion_replay_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(26), nullable=False),
        sa.Column("canonical_hash", sa.String(71), nullable=False),
        sa.Column("canonical_event", JSONB(), nullable=False),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_fusion_replay_inputs_ordinal"),
    )
    op.create_index("ix_fusion_replay_inputs_run", "fusion_replay_inputs", ["run_id"])
    op.create_table(
        "fusion_replay_outputs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("run_id", sa.String(26), sa.ForeignKey("fusion_replay_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("output_type", sa.String(), nullable=False),
        sa.Column("output_key", sa.String(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("decision_hash", sa.String(71), nullable=False),
        sa.Column("output_hash", sa.String(71), nullable=False),
        sa.Column("lineage_hash", sa.String(71), nullable=False),
        sa.UniqueConstraint("run_id", "output_type", "output_key", name="uq_fusion_replay_outputs_key"),
    )
    op.create_index("ix_fusion_replay_outputs_run", "fusion_replay_outputs", ["run_id"])
    op.create_table(
        "fusion_replay_errors",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("run_id", sa.String(26), sa.ForeignKey("fusion_replay_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(26), nullable=True),
        sa.Column("error_type", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_fusion_replay_errors_run", "fusion_replay_errors", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_fusion_replay_errors_run", table_name="fusion_replay_errors")
    op.drop_table("fusion_replay_errors")
    op.drop_index("ix_fusion_replay_outputs_run", table_name="fusion_replay_outputs")
    op.drop_table("fusion_replay_outputs")
    op.drop_index("ix_fusion_replay_inputs_run", table_name="fusion_replay_inputs")
    op.drop_table("fusion_replay_inputs")
    op.drop_index("ix_fusion_replay_runs_org_incident", table_name="fusion_replay_runs")
    op.drop_table("fusion_replay_runs")
