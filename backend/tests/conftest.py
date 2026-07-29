"""pytest fixtures for the ResQNet-SAGE backend.

All tests run against a real PostgreSQL/PostGIS database. The schema is
dropped and rebuilt via ``alembic upgrade head`` once per test session so
every test starts from a clean, migration-defined schema — no ad-hoc
table creation or column workarounds in test code.
"""

from __future__ import annotations

import asyncio
import os
import time
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


# ── SOTA degradation test support ───────────────────────────────────────────

# Placeholder ONNX weights that, if present, cause routes to attempt real
# inference instead of returning the model_unavailable degradation response.
_MODEL_WEIGHTS = [
    "models/sar-flood-mapping-v1.0.0.onnx",
    "models/building-damage-v1.0.0.onnx",
    "models/incident-nlp-v1.0.0.onnx",
]


def _wait_for_redis(timeout: float = 5.0) -> None:
    """Retry Redis ping until it succeeds or ``timeout`` seconds elapse."""
    import redis

    from app.config import settings

    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
            r.ping()
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(0.5)
    raise RuntimeError(f"Redis not reachable after {timeout}s: {last_exc}")


def _wait_for_kafka(timeout: float = 5.0) -> None:
    """Retry Kafka/Redpanda producer start until it succeeds or timeout."""
    from aiokafka import AIOKafkaProducer

    from app.config import settings

    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:

            async def _check() -> None:
                producer = AIOKafkaProducer(
                    bootstrap_servers=settings.REDPANDA_BOOTSTRAP_SERVERS,
                )
                await asyncio.wait_for(producer.start(), timeout=2)
                await producer.stop()

            asyncio.run(_check())
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(0.5)
    raise RuntimeError(f"Kafka not reachable after {timeout}s: {last_exc}")


@pytest.fixture
def degrade_env() -> Generator[None, None, None]:
    """Ensure services are healthy and model weights are unavailable.

    Used by SOTA degradation tests so that routes return ``model_unavailable``:
      1. Waits for Redis ping + Kafka producer start (5s timeout each).
      2. Resets the ``_redis_client`` singleton to avoid stale connections.
      3. Moves placeholder ONNX files aside so ``_weights_available()`` returns
         False — the routes then return the degradation response at request
         time (not startup).
      4. After the test: restores ONNX files and resets ``_redis_client``.
    """
    import app.deps

    _wait_for_redis(timeout=5)
    _wait_for_kafka(timeout=5)

    # Clear any stale Redis client from previous tests.
    app.deps._redis_client = None

    # Restore .bak files from a previous failed run before moving again.
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    for rel in _MODEL_WEIGHTS:
        src = os.path.join(data_dir, rel)
        bak = src + ".bak"
        if os.path.exists(bak) and not os.path.exists(src):
            os.rename(bak, src)

    # Move placeholder ONNX files aside so routes see weights as unavailable.
    moved: list[tuple[str, str]] = []
    for rel in _MODEL_WEIGHTS:
        src = os.path.join(data_dir, rel)
        if os.path.exists(src):
            dst = src + ".bak"
            os.rename(src, dst)
            moved.append((src, dst))

    try:
        yield
    finally:
        for src, dst in moved:
            if os.path.exists(dst):
                os.rename(dst, src)
        # Reset Redis client to avoid stale connections leaking across tests.
        app.deps._redis_client = None
