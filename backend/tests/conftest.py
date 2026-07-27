"""pytest fixtures for the ResQNet-SAGE backend.

All tests run against a real PostgreSQL/PostGIS database. The schema is
dropped and rebuilt via ``alembic upgrade head`` once per test session so
every test starts from a clean, migration-defined schema — no ad-hoc
table creation or column workarounds in test code.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from alembic import command
from app.db import SessionLocal, engine
from app.deps import get_db
from app.main import app

TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://resqnet:resqnet123@localhost:5432/resqnet",
)


def _drop_all_schema() -> None:
    """Drop and recreate the public schema for a fresh test session."""
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS age;"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS h3;"))


def _run_migrations() -> None:
    """Run ``alembic upgrade head`` to build the full schema."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _setup_db() -> Generator[None, None, None]:
    """Drop and rebuild the schema via Alembic once per test session."""
    _drop_all_schema()
    _run_migrations()
    yield


def override_get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Create a test client backed by the PostgreSQL test DB."""
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
