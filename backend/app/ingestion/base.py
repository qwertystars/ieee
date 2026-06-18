"""Connector base interface (DESIGN §6). Feature worker (Task #4) implements connectors."""
from __future__ import annotations

import abc
from typing import Any


class BaseConnector(abc.ABC):
    """Pulls raw payloads from an external source for a DataSource."""

    source_type: str = "manual"

    @abc.abstractmethod
    def fetch(self, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Return a list of raw payload dicts. Stub returns empty list."""
        raise NotImplementedError
