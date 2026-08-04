"""Immutable replay configuration, lineage, and canonical event ordering."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from app.lib.audit import JSONValue, canonical_json_bytes, sha256_hex
from app.models.events import RawEvent

REPLAY_SERIALIZATION_VERSION: Final[str] = "rfc8785-v2"
DEFAULT_ALGORITHM_VERSION: Final[str] = "fusion-replay-v1"
DEFAULT_CONFIG_VERSION: Final[str] = "fusion-config-v1"
DEFAULT_RUNTIME_VERSION: Final[str] = "python-3.11"
DEFAULT_LIBRARY_VERSIONS: Final[tuple[tuple[str, str], ...]] = (
    ("canonical-json", REPLAY_SERIALIZATION_VERSION),
    ("fusion-kernel", "stdlib-v1"),
)
DEFAULT_MODEL_VERSIONS: Final[tuple[tuple[str, str], ...]] = (
    ("confidence", "confidence-v1"),
    ("hypothesis", "hypothesis-v1"),
    ("world-state", "world-state-v1"),
)


@dataclass(frozen=True, slots=True)
class ReplayLineage:
    """Pinned implementation identity included in every replay hash."""

    algorithm_version: str
    config_version: str
    runtime_version: str
    library_versions: tuple[tuple[str, str], ...]
    model_versions: tuple[tuple[str, str], ...]
    serialization_version: str = REPLAY_SERIALIZATION_VERSION
    float_tolerance: float = 1e-6

    def as_dict(self) -> dict[str, JSONValue]:
        """Return a canonical JSON-compatible lineage mapping."""
        return {
            "algorithm_version": self.algorithm_version,
            "config_version": self.config_version,
            "runtime_version": self.runtime_version,
            "library_versions": [
                {"name": name, "version": version}
                for name, version in self.library_versions
            ],
            "model_versions": [
                {"name": name, "version": version}
                for name, version in self.model_versions
            ],
            "serialization_version": self.serialization_version,
            "float_tolerance": self.float_tolerance,
        }

    @property
    def lineage_hash(self) -> str:
        """Return the SHA-256 identity of this exact lineage."""
        return f"sha256:{sha256_hex(canonical_json_bytes(self.as_dict()))}"


@dataclass(frozen=True, slots=True)
class ReplayConfigError(ValueError):
    """A replay configuration cannot be used as a deterministic contract."""

    field: str
    reason: str

    def __str__(self) -> str:
        return f"{self.field}: {self.reason}"


@dataclass(frozen=True, slots=True)
class ReplayConfig:
    """Explicit replay configuration; no wall-clock or process state is used."""

    algorithm_version: str = DEFAULT_ALGORITHM_VERSION
    config_version: str = DEFAULT_CONFIG_VERSION
    runtime_version: str = DEFAULT_RUNTIME_VERSION
    library_versions: tuple[tuple[str, str], ...] = DEFAULT_LIBRARY_VERSIONS
    model_versions: tuple[tuple[str, str], ...] = DEFAULT_MODEL_VERSIONS
    as_of_ms: int | None = None
    float_tolerance: float = 1e-6

    def __post_init__(self) -> None:
        """Reject configuration values that would make replay ambiguous."""
        for field_name in (
            "algorithm_version",
            "config_version",
            "runtime_version",
        ):
            value = getattr(self, field_name)
            if not value.strip():
                raise ReplayConfigError(field_name, "must not be empty")
        for field_name, versions in (
            ("library_versions", self.library_versions),
            ("model_versions", self.model_versions),
        ):
            for name, version in versions:
                if not name.strip() or not version.strip():
                    raise ReplayConfigError(field_name, "names and versions must not be empty")
        if self.as_of_ms is not None and self.as_of_ms < 0:
            raise ReplayConfigError("as_of_ms", "must be non-negative")
        if not math.isfinite(self.float_tolerance) or self.float_tolerance <= 0:
            raise ReplayConfigError("float_tolerance", "must be finite and positive")

    def lineage(self) -> ReplayLineage:
        """Build the immutable lineage record for this configuration."""
        return ReplayLineage(
            algorithm_version=self.algorithm_version,
            config_version=self.config_version,
            runtime_version=self.runtime_version,
            library_versions=tuple(sorted(self.library_versions)),
            model_versions=tuple(sorted(self.model_versions)),
            float_tolerance=self.float_tolerance,
        )


def canonical_event_bytes(event: RawEvent) -> bytes:
    """Serialize one raw event using the established canonical serializer."""
    return canonical_json_bytes(event.model_dump(mode="json"))


def canonical_event_hash(event: RawEvent) -> str:
    """Hash one canonical raw event."""
    return f"sha256:{sha256_hex(canonical_event_bytes(event))}"


def event_sort_key(event: RawEvent) -> tuple[int, int, str, int, str, str, str]:
    """Return the database-order-independent event ordering key."""
    return (
        event.source_time_ms,
        event.receipt_time_ms,
        event.source_id,
        event.sequence,
        event.external_id,
        event.event_id,
        canonical_event_hash(event),
    )


def order_events(events: tuple[RawEvent, ...] | list[RawEvent]) -> tuple[RawEvent, ...]:
    """Return canonical event order without mutating the caller's collection."""
    return tuple(sorted(events, key=event_sort_key))


__all__ = [
    "DEFAULT_ALGORITHM_VERSION",
    "DEFAULT_CONFIG_VERSION",
    "DEFAULT_LIBRARY_VERSIONS",
    "DEFAULT_MODEL_VERSIONS",
    "DEFAULT_RUNTIME_VERSION",
    "REPLAY_SERIALIZATION_VERSION",
    "ReplayConfig",
    "ReplayConfigError",
    "ReplayLineage",
    "canonical_event_bytes",
    "canonical_event_hash",
    "event_sort_key",
    "order_events",
]
