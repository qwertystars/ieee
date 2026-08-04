"""Pure subgroup-gap metrics used by safety and robustness gates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubgroupGap:
    """Maximum eligible-group metric difference and its eligible groups."""

    value: float
    eligible_groups: tuple[str, ...]
    excluded_groups: tuple[str, ...]
    minimum_samples: int


def compute_subgroup_gap(
    metric_by_group: Mapping[str, float],
    sample_counts: Mapping[str, int],
    minimum_samples: int = 200,
) -> SubgroupGap:
    """Compute the maximum absolute difference over adequately sized groups."""
    eligible = tuple(
        sorted(
            group
            for group, metric in metric_by_group.items()
            if group in sample_counts
            and sample_counts[group] >= minimum_samples
            and 0.0 <= metric <= 1.0
        )
    )
    excluded = tuple(sorted(group for group in metric_by_group if group not in eligible))
    values = [metric_by_group[group] for group in eligible]
    gap = max(values) - min(values) if values else 0.0
    return SubgroupGap(
        value=float(gap),
        eligible_groups=eligible,
        excluded_groups=excluded,
        minimum_samples=minimum_samples,
    )


def subgroup_gap_passes(gap: SubgroupGap, maximum: float) -> bool:
    """Return whether an eligible subgroup gap is within its release bound."""
    return bool(gap.eligible_groups) and gap.value <= maximum


__all__ = ["SubgroupGap", "compute_subgroup_gap", "subgroup_gap_passes"]
