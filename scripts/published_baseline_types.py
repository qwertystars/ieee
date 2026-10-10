"""Shared types and immutable pins for the published-baseline contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

ROOT: Final = Path(__file__).resolve().parents[1]
HASH_PATTERN: Final = r"^[0-9a-f]{64}$"
COMMIT_PATTERN: Final = r"^[0-9a-f]{40}$"
EXPECTED_TASKS: Final = ("sen1floods11", "floodnet", "xview2", "incident-nlp")
EXPECTED_COMMITS: Final = {
    "sen1floods11": "b9e460dabe70230111a3c3d36cd0c5ce03606ee9",
    "floodnet": "1cba183788e5661c1ec326d7ded1f2536f82e9ad",
    "xview2": "821d9f8b9201ee7952aef13b073c9fd38ce11d4b",
    "incident-nlp": "crisis-pulse-artifact",
}
EXPECTED_COMMANDS: Final = {
    "sen1floods11": "python scripts/run_baseline.py --config benchmarks/baselines/sen1floods11.yaml",
    "floodnet": "python scripts/run_baseline.py --config benchmarks/baselines/floodnet-deeplabv3plus.yaml",
    "xview2": "python scripts/run_baseline.py --config benchmarks/baselines/xview2.yaml",
    "incident-nlp": "python scripts/run_baseline.py --config benchmarks/baselines/crisis-nlp.yaml",
}
EXPECTED_DATASETS: Final = {
    "sen1floods11": "sen1floods11-flood",
    "floodnet": "floodnet-flood",
    "xview2": "xbd-damage",
    "incident-nlp": "incident-nlp-evaluation",
}
EXPECTED_PRIMARY_METRICS: Final = {
    "sen1floods11": "flood_miou",
    "floodnet": "flood_miou",
    "xview2": "damage_combined_f1",
    "incident-nlp": "nlp_macro_f1",
}
REQUIRED_VARIANT_KINDS: Final = frozenset({"modality_only", "fusion"})
SYNTHETIC_ALIASES: Final = frozenset(
    {"synthetic", "heuristic", "dummy", "fixture", "random", "placeholder", "proxy"}
)


@dataclass(frozen=True, slots=True)
class BaselineValidationReport:
    """Machine-readable result of published-baseline registry validation."""

    status: str
    exit_code: int
    findings: tuple[str, ...]
    metrics: JsonObject


class RegistryInputError(ValueError):
    """Raised when a registry cannot be read as a JSON object."""
