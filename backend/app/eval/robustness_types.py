"""Typed records for deterministic robustness and equity evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FallbackStatus(StrEnum):
    """Safe output states accepted by an affected route."""

    ABSTAIN = "abstain"
    UNAVAILABLE = "unavailable"
    UNCERTAINTY = "uncertainty"


@dataclass(frozen=True, slots=True)
class RobustnessSample:
    """One deterministic, validation-only prediction outcome."""

    actual: bool
    prediction: bool | None
    confidence: float
    actionable: bool
    severe: bool
    group: str
    affected: bool = False
    fallback: FallbackStatus | None = None


@dataclass(frozen=True, slots=True)
class RiskCoverageResult:
    """Selective prediction risk at one requested coverage."""

    requested_coverage: float
    observed_coverage: float
    risk: float
    selected_count: int


@dataclass(frozen=True, slots=True)
class RobustnessEvaluation:
    """Computed metrics for one deterministic failure family."""

    sample_count: int
    affected_count: int
    recall: float
    degradation: float
    false_alert_burden: float
    severe_error_rate: float
    harm_weighted_error: float
    risk_coverage: RiskCoverageResult
    subgroup_metrics: dict[str, float]
    subgroup_gap: float
    fallback_rate: float
    attack_count: int


__all__ = [
    "FallbackStatus",
    "RiskCoverageResult",
    "RobustnessEvaluation",
    "RobustnessSample",
]
