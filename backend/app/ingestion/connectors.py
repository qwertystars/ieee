"""Source connectors (DESIGN §6). Stubs; Task #4 implements real fetching."""
from __future__ import annotations

from typing import Any

from app.ingestion.base import BaseConnector


class NullConnector(BaseConnector):
    source_type = "manual"

    def fetch(self, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return []


def get_connector(source_type: str) -> BaseConnector:
    """Return a connector for the given source type. Stub returns NullConnector."""
    return NullConnector()
