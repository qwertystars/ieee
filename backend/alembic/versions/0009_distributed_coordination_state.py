import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emergency_overrides",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("target_user_id", sa.String(26), nullable=False),
        sa.Column("granted_by", sa.String(26), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("granted_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("expires_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("revoked_at_ms", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_emergency_overrides_org_target",
        "emergency_overrides",
        ["org_id", "target_user_id"],
    )
    op.create_index(
        "ix_emergency_overrides_expiry", "emergency_overrides", ["expires_at_ms"]
    )

    op.create_table(
        "credential_states",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String(), nullable=True),
        sa.Column("credential_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("expires_at_ms", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("credential_hash", name="uq_credential_states_hash"),
    )
    op.create_index(
        "ix_credential_states_org_expiry",
        "credential_states",
        ["org_id", "expires_at_ms"],
    )

    op.create_table(
        "coordination_quarantine",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("subject_type", sa.String(), nullable=False),
        sa.Column("subject_id", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("expires_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("released_at_ms", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_coordination_quarantine_org_subject",
        "coordination_quarantine",
        ["org_id", "subject_id"],
    )
    op.create_index(
        "ix_coordination_quarantine_expiry",
        "coordination_quarantine",
        ["expires_at_ms"],
    )

    op.create_table(
        "evaluation_jobs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(26), nullable=False),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("request_payload", JSONB(), nullable=False),
        sa.Column("result_payload", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("expires_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("claimed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_evaluation_jobs_org_status", "evaluation_jobs", ["org_id", "status"]
    )
    op.create_index("ix_evaluation_jobs_expiry", "evaluation_jobs", ["expires_at_ms"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_jobs_expiry", table_name="evaluation_jobs")
    op.drop_index("ix_evaluation_jobs_org_status", table_name="evaluation_jobs")
    op.drop_table("evaluation_jobs")
    op.drop_index(
        "ix_coordination_quarantine_expiry", table_name="coordination_quarantine"
    )
    op.drop_index(
        "ix_coordination_quarantine_org_subject", table_name="coordination_quarantine"
    )
    op.drop_table("coordination_quarantine")
    op.drop_index("ix_credential_states_org_expiry", table_name="credential_states")
    op.drop_table("credential_states")
    op.drop_index("ix_emergency_overrides_expiry", table_name="emergency_overrides")
    op.drop_index(
        "ix_emergency_overrides_org_target", table_name="emergency_overrides"
    )
    op.drop_table("emergency_overrides")
