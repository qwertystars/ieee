"""Deterministic paired statistics for incident-level benchmark reports."""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import mean, median
from typing import Final

DEFAULT_BOOTSTRAP_RESAMPLES: Final = 10_000
DEFAULT_CONFIDENCE_LEVEL: Final = 0.95
DEFAULT_SUPERIORITY_MARGIN: Final = 0.02


@dataclass(frozen=True, slots=True)
class SeedMetric:
    """One metric observation for one incident and execution seed."""

    incident_id: str
    seed: int
    value: float


@dataclass(frozen=True, slots=True)
class PairedMetric:
    """Candidate and baseline values for one incident after seed aggregation."""

    incident_id: str
    candidate: float
    baseline: float


@dataclass(frozen=True, slots=True)
class BootstrapInterval:
    """A paired incident bootstrap interval for candidate minus baseline."""

    point_estimate: float
    lower_bound: float
    upper_bound: float
    resamples: int
    confidence_level: float
    incident_count: int
    p_value: float


class StatisticsInputError(ValueError):
    """Raised when a paired statistical input violates the benchmark contract."""


def median_seed_metrics(values: Sequence[SeedMetric]) -> dict[str, float]:
    """Return the median metric per incident after requiring five unique seeds."""
    by_incident: dict[str, list[float]] = {}
    seen: set[tuple[str, int]] = set()
    for value in values:
        key = (value.incident_id, value.seed)
        if key in seen:
            raise StatisticsInputError(f"duplicate incident/seed: {value.incident_id}/{value.seed}")
        seen.add(key)
        by_incident.setdefault(value.incident_id, []).append(value.value)
    if not by_incident:
        raise StatisticsInputError("at least one incident is required")
    if any(len(scores) != 5 for scores in by_incident.values()):
        raise StatisticsInputError("each incident requires exactly five seed scores")
    return {incident_id: float(median(scores)) for incident_id, scores in by_incident.items()}


def pair_incident_metrics(
    candidate: Sequence[SeedMetric], baseline: Sequence[SeedMetric]
) -> tuple[PairedMetric, ...]:
    """Median five seeds and pair candidate/baseline by immutable incident ID."""
    candidate_medians = median_seed_metrics(candidate)
    baseline_medians = median_seed_metrics(baseline)
    if set(candidate_medians) != set(baseline_medians):
        raise StatisticsInputError("candidate and baseline incident IDs must match")
    return tuple(
        PairedMetric(incident_id, candidate_medians[incident_id], baseline_medians[incident_id])
        for incident_id in sorted(candidate_medians)
    )


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _sign_test_p_value(differences: Sequence[float]) -> float:
    nonzero = [difference for difference in differences if difference != 0.0]
    if not nonzero:
        return 1.0
    positives = sum(difference > 0.0 for difference in nonzero)
    trials = len(nonzero)
    tail = sum(math.comb(trials, index) for index in range(positives + 1)) / 2**trials
    return min(1.0, 2.0 * min(tail, 1.0 - tail + math.comb(trials, positives) / 2**trials))


def paired_incident_bootstrap(
    values: Sequence[PairedMetric],
    *,
    resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    random_seed: int = 2025,
) -> BootstrapInterval:
    """Compute a deterministic paired incident bootstrap confidence interval."""
    if not values:
        raise StatisticsInputError("at least one paired incident is required")
    if resamples < 1:
        raise StatisticsInputError("bootstrap resamples must be positive")
    if not 0.0 < confidence_level < 1.0:
        raise StatisticsInputError("confidence level must be between zero and one")
    differences = [value.candidate - value.baseline for value in values]
    rng = random.Random(random_seed)
    distributions = [
        mean(rng.choice(differences) for _ in differences) for _ in range(resamples)
    ]
    tail = (1.0 - confidence_level) / 2.0
    return BootstrapInterval(
        point_estimate=mean(differences),
        lower_bound=_percentile(distributions, tail),
        upper_bound=_percentile(distributions, 1.0 - tail),
        resamples=resamples,
        confidence_level=confidence_level,
        incident_count=len(values),
        p_value=_sign_test_p_value(differences),
    )


def holm_correction(p_values: Mapping[str, float]) -> dict[str, float]:
    """Return Holm step-down adjusted p-values for one comparison family."""
    if any(not 0.0 <= value <= 1.0 for value in p_values.values()):
        raise StatisticsInputError("p-values must be in the closed unit interval")
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for rank, (name, p_value) in enumerate(ordered):
        running = max(running, min(1.0, p_value * (total - rank)))
        adjusted[name] = running
    return adjusted


def superiority_gate(
    candidate_lower_bound: float,
    baseline_value: float,
    *,
    margin: float = DEFAULT_SUPERIORITY_MARGIN,
) -> bool:
    """Apply the preregistered absolute candidate-minus-baseline margin gate."""
    return candidate_lower_bound >= baseline_value + margin


__all__ = [
    "DEFAULT_BOOTSTRAP_RESAMPLES",
    "DEFAULT_CONFIDENCE_LEVEL",
    "DEFAULT_SUPERIORITY_MARGIN",
    "BootstrapInterval",
    "PairedMetric",
    "SeedMetric",
    "StatisticsInputError",
    "holm_correction",
    "median_seed_metrics",
    "pair_incident_metrics",
    "paired_incident_bootstrap",
    "superiority_gate",
]
