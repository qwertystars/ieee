"""Chaos test conftest — overrides parent _setup_db so the live Docker backend
is not disturbed. Chaos tests hit the running Docker backend at localhost:8000
via HTTP and toggle Docker services via `docker compose stop/start`.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest


@pytest.fixture(scope="session", autouse=True)
def _setup_db() -> Generator[None, None, None]:
    """No-op override — chaos tests run against the live Docker backend."""
    yield
