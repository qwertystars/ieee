"""Shared types and constants for benchmark validation modules."""

from __future__ import annotations

from typing import TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
SPLITS = ("train", "calibration", "test")
HASH_PATTERN = r"^[0-9a-f]{64}$"
COMMIT_PATTERN = r"^[0-9a-f]{40}$"
PHASH_PATTERN = r"^[0-9a-f]{16}$"
PINNED_DATASETS = {
    "sen1floods11-flood": "github:cloudtostreet/Sen1Floods11@b9e460dabe70230111a3c3d36cd0c5ce03606ee9",
    "floodnet-flood": "github:BinaLab/FloodNet-Supervised_v1.0@1cba183788e5661c1ec326d7ded1f2536f82e9ad",
    "xbd-damage": "github:DIUx-xView/xView2_baseline@821d9f8b9201ee7952aef13b073c9fd38ce11d4b",
}
