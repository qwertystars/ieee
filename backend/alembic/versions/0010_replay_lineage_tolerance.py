"""Persist the complete replay lineage and numeric tolerance."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fusion_replay_runs", sa.Column("lineage", JSONB(), nullable=True))
    op.add_column("fusion_replay_runs", sa.Column("float_tolerance", sa.Float(), nullable=True))
    op.execute(
        "UPDATE fusion_replay_runs SET lineage = jsonb_build_object("
        "'algorithm_version', algorithm_version, 'config_version', config_version, "
        "'runtime_version', runtime_version, 'library_versions', library_versions, "
        "'model_versions', model_versions, 'serialization_version', serialization_version, "
        "'float_tolerance', 0.000001) WHERE lineage IS NULL"
    )
    op.execute(
        "UPDATE fusion_replay_runs SET float_tolerance = 0.000001 "
        "WHERE float_tolerance IS NULL"
    )
    op.alter_column("fusion_replay_runs", "lineage", nullable=False)
    op.alter_column("fusion_replay_runs", "float_tolerance", nullable=False)


def downgrade() -> None:
    op.drop_column("fusion_replay_runs", "float_tolerance")
    op.drop_column("fusion_replay_runs", "lineage")
