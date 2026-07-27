"""expand operational_tasks with assignment fields.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-26

Adds 3 columns to the operational_tasks table to support team assignment
and capability-based routing:
- assigned_team_id (String, nullable) — currently assigned team.
- required_capability (String, nullable) — capability required to perform
  the task (used by the assignment engine for matching).
- assignment_history (JSONB, nullable) — append-only log of assignment
  transitions (team, timestamp, reason).

The ORM model in app.models.entities.OperationalTask is updated to match.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operational_tasks",
        sa.Column("assigned_team_id", sa.String(), nullable=True),
    )
    op.add_column(
        "operational_tasks",
        sa.Column("required_capability", sa.String(), nullable=True),
    )
    op.add_column(
        "operational_tasks",
        sa.Column("assignment_history", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("operational_tasks", "assignment_history")
    op.drop_column("operational_tasks", "required_capability")
    op.drop_column("operational_tasks", "assigned_team_id")
