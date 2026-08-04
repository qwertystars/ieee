import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("operational_tasks", sa.Column("source_alert_id", sa.String(26), nullable=True))
    op.add_column("operational_tasks", sa.Column("decision_id", sa.String(26), nullable=True))
    op.create_unique_constraint(
        "uq_operational_task_alert",
        "operational_tasks",
        ["org_id", "incident_id", "source_alert_id"],
    )
    op.create_index(
        "ix_operational_tasks_decision",
        "operational_tasks",
        ["org_id", "decision_id"],
    )

    op.create_table(
        "command_signing_keys",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key_id", sa.String(26), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("revoked_at", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("org_id", "key_id", name="uq_command_key_org_key"),
    )
    op.create_index("ix_command_key_org_user", "command_signing_keys", ["org_id", "user_id"])

    op.create_table(
        "alert_decisions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("incident_id", sa.String(26), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("alert_id", sa.String(26), sa.ForeignKey("alerts.id"), nullable=False),
        sa.Column("command_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("task_id", sa.String(26), nullable=True),
        sa.Column("created_by", sa.String(26), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint(
            "org_id", "incident_id", "alert_id", "command_type",
            name="uq_alert_decision_command",
        ),
    )
    op.create_index("ix_alert_decisions_org_incident", "alert_decisions", ["org_id", "incident_id"])

    op.create_table(
        "command_approvals",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("incident_id", sa.String(26), nullable=False),
        sa.Column("alert_id", sa.String(26), nullable=False),
        sa.Column("decision_id", sa.String(26), sa.ForeignKey("alert_decisions.id"), nullable=False),
        sa.Column("approver_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approver_role", sa.String(), nullable=False),
        sa.Column("key_id", sa.String(26), nullable=False),
        sa.Column("nonce", sa.String(26), nullable=False),
        sa.Column("signed_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("expires_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint(
            "org_id", "decision_id", "approver_id",
            name="uq_command_approval_approver",
        ),
        sa.UniqueConstraint("org_id", "nonce", name="uq_command_approval_nonce"),
    )
    op.create_index("ix_command_approvals_decision", "command_approvals", ["org_id", "decision_id"])


def downgrade() -> None:
    op.drop_table("command_approvals")
    op.drop_index("ix_alert_decisions_org_incident", table_name="alert_decisions")
    op.drop_table("alert_decisions")
    op.drop_index("ix_command_key_org_user", table_name="command_signing_keys")
    op.drop_table("command_signing_keys")
    op.drop_index("ix_operational_tasks_decision", table_name="operational_tasks")
    op.drop_constraint("uq_operational_task_alert", "operational_tasks", type_="unique")
    op.drop_column("operational_tasks", "decision_id")
    op.drop_column("operational_tasks", "source_alert_id")
