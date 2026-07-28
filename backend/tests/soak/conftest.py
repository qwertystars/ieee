"""Soak test conftest — overrides parent _setup_db so the live Docker backend
is not disturbed. Soak tests hit the running Docker backend at localhost:8000
via HTTP; they do not touch the local test database.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest


@pytest.fixture(scope="session", autouse=True)
def _setup_db() -> Generator[None, None, None]:
    """No-op override — soak tests run against the live Docker backend."""
    yield
