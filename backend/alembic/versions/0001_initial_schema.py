"""initial schema: postgis extension + all tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-03

Creates the PostGIS extension first, then builds every table from the SQLAlchemy
metadata (all models imported via ``app.models``). Using ``metadata.create_all``
keeps the initial schema in lockstep with the models and lets GeoAlchemy2 emit its
geometry columns and spatial indexes correctly.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from app.db import Base
import app.models  # noqa: F401  (registers all tables on Base.metadata)

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
