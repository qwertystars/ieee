"""add missing tables (users, sources, idempotency, reliability, sync, h3, provenance).

Revision ID: 0002b
Revises: 0002a
Create Date: 2026-07-26

Creates 13 tables previously created on demand via ensure_table() or
Base.metadata.create_all(). After this migration, all ensure_table/create_all
workarounds are removed from app/ — the schema lives entirely in Alembic.

Tables: users, sources, idempotency_keys, source_reliability,
federation_outbox, edge_sync_applied, edge_sync_state, sync_conflicts,
models, prompts, ai_calls, decision_provenance, h3_geo_index.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002b"
down_revision = "0002a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    # 1. users — may already exist (created by Base.metadata.create_all).
    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("id", sa.String(26), primary_key=True),
            sa.Column("email", sa.String, nullable=False),
            sa.Column("hashed_password", sa.String, nullable=False),
            sa.Column("role", sa.String, nullable=False),
            sa.Column("org_id", sa.String, nullable=False),
            sa.Column("created_at", sa.BigInteger, nullable=False),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
        op.create_index("ix_users_role", "users", ["role"])
        op.create_index("ix_users_org_id", "users", ["org_id"])

    # 2. sources
    op.create_table(
        "sources",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("provider", sa.String, nullable=False),
        sa.Column("refresh_interval_s", sa.Integer, nullable=True),
        sa.Column("last_success_at", sa.BigInteger, nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("config", JSONB, nullable=False),
        sa.Column("access_policy", sa.String, nullable=False),
        sa.Column("ownership", sa.String, nullable=False),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
    )
    op.create_index("ix_sources_org_id", "sources", ["org_id"])

    # 3. idempotency_keys
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("external_id", sa.String, nullable=False),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.UniqueConstraint("source", "external_id", name="uq_idempotency_source_external"),
    )

    # 4. source_reliability
    op.create_table(
        "source_reliability",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.String, nullable=False),
        sa.Column("phenomenon_type", sa.String, nullable=True),
        sa.Column("alpha", sa.Float, nullable=False),
        sa.Column("beta", sa.Float, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        sa.UniqueConstraint("source_id", "phenomenon_type", name="uq_reliability_source_phenomenon"),
    )
    op.create_index("ix_source_reliability_source_id", "source_reliability", ["source_id"])

    # 5. federation_outbox
    op.create_table(
        "federation_outbox",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("observation_id", sa.String(26), nullable=False),
        sa.Column("source_id", sa.String, nullable=False),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("sync_priority", sa.Integer, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("synced_at", sa.BigInteger, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index("ix_federation_outbox_observation_id", "federation_outbox", ["observation_id"])
    op.create_index("ix_federation_outbox_source_id", "federation_outbox", ["source_id"])
    op.create_index("ix_federation_outbox_org_id", "federation_outbox", ["org_id"])

    # 6. edge_sync_applied
    op.create_table(
        "edge_sync_applied",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.String(26), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("item_type", sa.String, nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("incident_id", sa.String, nullable=False),
        sa.Column("applied_at", sa.BigInteger, nullable=False),
    )
    op.create_index("ix_edge_sync_applied_item_id", "edge_sync_applied", ["item_id"], unique=True)
    op.create_index("ix_edge_sync_applied_content_hash", "edge_sync_applied", ["content_hash"], unique=True)
    op.create_index("ix_edge_sync_applied_org_id", "edge_sync_applied", ["org_id"])
    op.create_index("ix_edge_sync_applied_incident_id", "edge_sync_applied", ["incident_id"])

    # 7. edge_sync_state
    op.create_table(
        "edge_sync_state",
        sa.Column("incident_id", sa.String, primary_key=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("last_sync_at", sa.BigInteger, nullable=True),
        sa.Column("last_batch_received", sa.Integer, nullable=False),
        sa.Column("last_batch_pending", sa.Integer, nullable=False),
    )
    op.create_index("ix_edge_sync_state_org_id", "edge_sync_state", ["org_id"])

    # 8. sync_conflicts
    op.create_table(
        "sync_conflicts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("incident_id", sa.String, nullable=False),
        sa.Column("entity_type", sa.String, nullable=False),
        sa.Column("entity_id", sa.String, nullable=False),
        sa.Column("local", JSONB, nullable=False),
        sa.Column("remote", JSONB, nullable=False),
        sa.Column("content_hash_local", sa.String(64), nullable=False),
        sa.Column("content_hash_remote", sa.String(64), nullable=False),
        sa.Column("detected_at", sa.BigInteger, nullable=False),
    )
    op.create_index("ix_sync_conflicts_org_id", "sync_conflicts", ["org_id"])
    op.create_index("ix_sync_conflicts_incident_id", "sync_conflicts", ["incident_id"])
    op.create_index("ix_sync_conflicts_entity_id", "sync_conflicts", ["entity_id"])

    # 9. models (perception model registry)
    op.create_table(
        "models",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("version", sa.String, nullable=False),
        sa.Column("framework", sa.String, nullable=False),
        sa.Column("task", sa.String, nullable=False),
        sa.Column("r2_key", sa.String, nullable=False),
        sa.Column("input_schema", JSONB, nullable=False),
        sa.Column("output_schema", JSONB, nullable=False),
        sa.Column("calibration_metrics", JSONB, nullable=False),
        sa.Column("created_at", sa.BigInteger, nullable=False),
    )
    op.create_index("ix_models_org_id", "models", ["org_id"])
    op.create_index("ix_models_name", "models", ["name"])

    # 10. prompts
    op.create_table(
        "prompts",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("version", sa.String, nullable=False),
        sa.Column("template", sa.Text, nullable=False),
        sa.Column("created_at", sa.BigInteger, nullable=False),
    )
    op.create_index("ix_prompts_name", "prompts", ["name"])

    # 11. ai_calls
    op.create_table(
        "ai_calls",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("incident_id", sa.String, nullable=True),
        sa.Column("prompt_name", sa.String, nullable=False),
        sa.Column("prompt_version", sa.String, nullable=False),
        sa.Column("tokens_in", sa.Integer, nullable=False),
        sa.Column("tokens_out", sa.Integer, nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("cost", sa.Float, nullable=False),
        sa.Column("provider", sa.String, nullable=False),
        sa.Column("created_at", sa.BigInteger, nullable=False),
    )
    op.create_index("ix_ai_calls_org_id", "ai_calls", ["org_id"])
    op.create_index("ix_ai_calls_incident_id", "ai_calls", ["incident_id"])

    # 12. decision_provenance
    op.create_table(
        "decision_provenance",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("recommendation_id", sa.String, nullable=False),
        sa.Column("input_observation_ids", JSONB, nullable=False),
        sa.Column("data_versions", JSONB, nullable=False),
        sa.Column("model_versions", JSONB, nullable=False),
        sa.Column("optimization_parameters", JSONB, nullable=False),
        sa.Column("scenario_set", JSONB, nullable=False),
        sa.Column("constraints", JSONB, nullable=False),
        sa.Column("generated_alternatives", JSONB, nullable=False),
        sa.Column("operator_decision", JSONB, nullable=False),
        sa.Column("override_reason", sa.Text, nullable=False),
        sa.Column("execution_outcome", JSONB, nullable=False),
        sa.Column("ts", sa.BigInteger, nullable=False),
        sa.Column("prev_hash", sa.String, nullable=False),
        sa.Column("hash", sa.String, nullable=False),
    )
    op.create_index("ix_decision_provenance_org_id", "decision_provenance", ["org_id"])
    op.create_index("ix_decision_provenance_recommendation_id", "decision_provenance", ["recommendation_id"])

    # 13. h3_geo_index
    op.create_table(
        "h3_geo_index",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String, nullable=False),
        sa.Column("entity_id", sa.String(26), nullable=False),
        sa.Column("h3", sa.String, nullable=False),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("incident_id", sa.String, nullable=False),
        sa.UniqueConstraint("entity_type", "entity_id", "h3", name="uq_h3_entity_h3"),
    )
    op.create_index("ix_h3_geo_index_org_incident", "h3_geo_index", ["org_id", "incident_id"])
    op.create_index("ix_h3_geo_index_h3", "h3_geo_index", ["h3"])


def downgrade() -> None:
    for table in (
        "h3_geo_index", "decision_provenance", "ai_calls", "prompts",
        "models", "sync_conflicts", "edge_sync_state", "edge_sync_applied",
        "federation_outbox", "source_reliability", "idempotency_keys",
        "sources", "users",
    ):
        op.drop_table(table)
