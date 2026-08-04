"""Pure robustness, selective-prediction, harm, and equity metrics."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TypeVar

from app.eval.robustness_types import (
    RiskCoverageResult,
    RobustnessEvaluation,
    RobustnessSample,
)
from app.optimizer.fairness_metrics import compute_subgroup_gap

_LeftValue = TypeVar("_LeftValue")
_RightValue = TypeVar("_RightValue")


def _require_same_length(
    left: Sequence[_LeftValue], right: Sequence[_RightValue]
) -> None:
    if len(left) != len(right):
        raise ValueError("metric inputs must have equal length")


def compute_false_alert_burden(
    predictions: Sequence[bool | None], actionable: Sequence[bool]
) -> float:
    """Return non-actionable alerts divided by all emitted alerts."""
    _require_same_length(predictions, actionable)
    alerts = [index for index, prediction in enumerate(predictions) if prediction is True]
    if not alerts:
        return 0.0
    return sum(not actionable[index] for index in alerts) / len(alerts)


def compute_severe_error_rate(
    predictions: Sequence[bool | None], actual: Sequence[bool], severe: Sequence[bool]
) -> float:
    """Return explicit severe false negatives divided by severe labels.

    Abstentions are excluded from false negatives because they are safe
    non-decisions; an affected route must still expose its uncertainty state.
    """
    _require_same_length(predictions, actual)
    _require_same_length(predictions, severe)
    severe_labels = [index for index, label in enumerate(severe) if label and actual[index]]
    if not severe_labels:
        return 0.0
    false_negatives = sum(predictions[index] is False for index in severe_labels)
    return false_negatives / len(severe_labels)


def compute_harm_weighted_error(
    predictions: Sequence[bool | None],
    actual: Sequence[bool],
    false_positive_cost: float = 1.0,
    false_negative_cost: float = 5.0,
) -> float:
    """Apply a fixed safety cost matrix, excluding explicitly abstained cases."""
    _require_same_length(predictions, actual)
    denominator = sum(
        false_negative_cost if label else false_positive_cost for label in actual
    )
    if denominator == 0.0:
        return 0.0
    weighted = sum(
        false_negative_cost if label else false_positive_cost
        for prediction, label in zip(predictions, actual)
        if prediction is not None and prediction != label
    )
    return weighted / denominator


def compute_risk_coverage(
    predictions: Sequence[bool | None],
    actual: Sequence[bool],
    confidence: Sequence[float],
    requested_coverage: float = 0.8,
) -> RiskCoverageResult:
    """Compute error risk after retaining the most confident non-abstentions."""
    _require_same_length(predictions, actual)
    _require_same_length(predictions, confidence)
    selected_candidates = [
        index for index, prediction in enumerate(predictions) if prediction is not None
    ]
    if not selected_candidates:
        return RiskCoverageResult(requested_coverage, 0.0, 0.0, 0)
    selected_candidates.sort(key=lambda index: (-confidence[index], index))
    requested_count = max(1, int(len(predictions) * requested_coverage + 0.999999))
    count = min(requested_count, len(selected_candidates))
    selected = selected_candidates[:count]
    errors = sum(predictions[index] != actual[index] for index in selected)
    return RiskCoverageResult(
        requested_coverage=requested_coverage,
        observed_coverage=count / len(predictions),
        risk=errors / count,
        selected_count=count,
    )


def _recall(samples: Iterable[RobustnessSample]) -> float:
    rows = tuple(samples)
    positives = sum(sample.actual for sample in rows)
    if positives == 0:
        return 0.0
    true_positives = sum(sample.actual and sample.prediction is True for sample in rows)
    return true_positives / positives


def evaluate_samples(
    samples: Sequence[RobustnessSample],
    baseline_recall: float,
    subgroup_minimum_samples: int = 200,
    attack_count: int = 0,
) -> RobustnessEvaluation:
    """Compute every release-gate metric from typed validation-only samples."""
    predictions = tuple(sample.prediction for sample in samples)
    actual = tuple(sample.actual for sample in samples)
    confidence = tuple(sample.confidence for sample in samples)
    severe = tuple(sample.severe for sample in samples)
    actionable = tuple(sample.actionable for sample in samples)
    recall = _recall(samples)
    degradation = max(0.0, (baseline_recall - recall) / baseline_recall) if baseline_recall else 0.0
    groups = sorted({sample.group for sample in samples})
    subgroup_metrics = {
        group: _recall(sample for sample in samples if sample.group == group)
        for group in groups
    }
    subgroup_gap = compute_subgroup_gap(
        subgroup_metrics,
        {group: sum(sample.group == group for sample in samples) for group in groups},
        subgroup_minimum_samples,
    ).value
    affected = [sample for sample in samples if sample.affected]
    fallback_rate = (
        sum(sample.fallback is not None for sample in affected) / len(affected)
        if affected
        else 1.0
    )
    return RobustnessEvaluation(
        sample_count=len(samples),
        affected_count=len(affected),
        recall=recall,
        degradation=degradation,
        false_alert_burden=compute_false_alert_burden(predictions, actionable),
        severe_error_rate=compute_severe_error_rate(predictions, actual, severe),
        harm_weighted_error=compute_harm_weighted_error(predictions, actual),
        risk_coverage=compute_risk_coverage(predictions, actual, confidence),
        subgroup_metrics=subgroup_metrics,
        subgroup_gap=subgroup_gap,
        fallback_rate=fallback_rate,
        attack_count=attack_count,
    )


__all__ = [
    "compute_false_alert_burden",
    "compute_harm_weighted_error",
    "compute_risk_coverage",
    "compute_severe_error_rate",
    "evaluate_samples",
]
