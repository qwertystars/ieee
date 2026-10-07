"""Create tenancy indexes declared on models but never migrated."""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_INDEXES = (
    ("ix_canonical_decisions_incident_id", "canonical_decisions", "incident_id"),
    ("ix_canonical_decisions_org_id", "canonical_decisions", "org_id"),
    ("ix_predictions_incident_id", "predictions", "incident_id"),
    ("ix_predictions_org_id", "predictions", "org_id"),
    ("ix_raw_events_incident_id", "raw_events", "incident_id"),
    ("ix_raw_events_org_id", "raw_events", "org_id"),
)


def upgrade() -> None:
    for name, table, column in _INDEXES:
        op.create_index(name, table, [column], if_not_exists=True)


def downgrade() -> None:
    for name, table, _column in reversed(_INDEXES):
        op.drop_index(name, table_name=table, if_exists=True)
