"""Bind edge receipts to tenant-scoped idempotency and conflict identities."""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("edge_sync_applied", sa.Column("idempotency_key", sa.String(26), nullable=True))
    op.execute("UPDATE edge_sync_applied SET idempotency_key = item_id WHERE idempotency_key IS NULL")
    op.alter_column("edge_sync_applied", "idempotency_key", nullable=False)
    op.drop_index("ix_edge_sync_applied_content_hash", table_name="edge_sync_applied")
    op.create_index(
        "uq_edge_sync_applied_org_incident_hash",
        "edge_sync_applied",
        ["org_id", "incident_id", "content_hash"],
        unique=True,
    )
    op.create_index(
        "uq_edge_sync_applied_org_idempotency",
        "edge_sync_applied",
        ["org_id", "idempotency_key"],
        unique=True,
    )
    op.drop_constraint("edge_sync_state_pkey", "edge_sync_state", type_="primary")
    op.create_primary_key("edge_sync_state_pkey", "edge_sync_state", ["org_id", "incident_id"])
    op.add_column("sync_conflicts", sa.Column("item_id", sa.String(26), nullable=True))
    op.create_index("ix_sync_conflicts_item_id", "sync_conflicts", ["item_id"])


def downgrade() -> None:
    op.drop_index("ix_sync_conflicts_item_id", table_name="sync_conflicts")
    op.drop_column("sync_conflicts", "item_id")
    op.drop_constraint("edge_sync_state_pkey", "edge_sync_state", type_="primary")
    op.create_primary_key("edge_sync_state_pkey", "edge_sync_state", ["incident_id"])
    op.drop_index("uq_edge_sync_applied_org_idempotency", table_name="edge_sync_applied")
    op.drop_index("uq_edge_sync_applied_org_incident_hash", table_name="edge_sync_applied")
    op.create_index("ix_edge_sync_applied_content_hash", "edge_sync_applied", ["content_hash"], unique=True)
    op.drop_column("edge_sync_applied", "idempotency_key")
