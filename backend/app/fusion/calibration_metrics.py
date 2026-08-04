"""Model-output calibration metrics shared by the calibration facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

import numpy as np


class ReliabilityData(TypedDict):
    """JSON-compatible reliability diagram data."""

    bin_lower: list[float]
    bin_upper: list[float]
    bin_count: list[int]
    bin_accuracy: list[float]
    bin_confidence: list[float]
    n_bins: int


@dataclass(frozen=True, slots=True)
class RiskCoveragePoint:
    """Selective prediction risk at one retained coverage level."""

    coverage: float
    risk: float


@dataclass(frozen=True, slots=True)
class SubgroupMetric:
    """Calibration summary for one named subgroup or hazard."""

    name: str
    sample_count: int
    ece: float
    brier_score: float
    nll: float


def compute_brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Return the binary Brier score."""
    labels = np.asarray(y_true, dtype=float)
    probabilities = np.asarray(y_prob, dtype=float)
    return float(np.mean((probabilities - labels) ** 2))


def compute_ece(
    y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10
) -> float:
    """Return expected calibration error using fixed-width probability bins."""
    labels = np.asarray(y_true, dtype=float)
    probabilities = np.asarray(y_prob, dtype=float)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for index in range(n_bins):
        mask = (probabilities >= bins[index]) & (probabilities < bins[index + 1])
        if index == n_bins - 1:
            mask = (probabilities >= bins[index]) & (probabilities <= bins[index + 1])
        count = int(np.sum(mask))
        if count:
            ece += (count / len(labels)) * abs(
                float(np.mean(labels[mask])) - float(np.mean(probabilities[mask]))
            )
    return ece


def compute_reliability_data(
    y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10
) -> ReliabilityData:
    """Return counts, confidence, and empirical accuracy for each bin."""
    labels = np.asarray(y_true, dtype=float)
    probabilities = np.asarray(y_prob, dtype=float)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    counts: list[int] = []
    accuracies: list[float] = []
    confidences: list[float] = []
    for index in range(n_bins):
        mask = (probabilities >= bins[index]) & (probabilities < bins[index + 1])
        if index == n_bins - 1:
            mask = (probabilities >= bins[index]) & (probabilities <= bins[index + 1])
        count = int(np.sum(mask))
        counts.append(count)
        if count:
            accuracies.append(float(np.mean(labels[mask])))
            confidences.append(float(np.mean(probabilities[mask])))
        else:
            accuracies.append(0.0)
            confidences.append(float(bins[index]))
    return {
        "bin_lower": [float(value) for value in bins[:-1]],
        "bin_upper": [float(value) for value in bins[1:]],
        "bin_count": counts,
        "bin_accuracy": accuracies,
        "bin_confidence": confidences,
        "n_bins": n_bins,
    }


def compute_nll(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Return clipped binary negative log likelihood."""
    labels = np.asarray(y_true, dtype=float)
    probabilities = np.clip(np.asarray(y_prob, dtype=float), 1e-15, 1.0 - 1e-15)
    return float(
        -np.mean(
            labels * np.log(probabilities)
            + (1.0 - labels) * np.log(1.0 - probabilities)
        )
    )


def compute_coverage(
    y_true: np.ndarray, y_pred_lower: np.ndarray, y_pred_upper: np.ndarray
) -> float:
    """Return the fraction of labels contained by an interval."""
    labels = np.asarray(y_true, dtype=float)
    lower = np.asarray(y_pred_lower, dtype=float)
    upper = np.asarray(y_pred_upper, dtype=float)
    return float(np.mean((labels >= lower) & (labels <= upper)))


def compute_interval_width(
    y_pred_lower: np.ndarray, y_pred_upper: np.ndarray
) -> float:
    """Return mean conformal interval width."""
    return float(
        np.mean(np.asarray(y_pred_upper, dtype=float) - np.asarray(y_pred_lower, dtype=float))
    )


def compute_false_confidence_rate(
    y_true: np.ndarray, y_prob: np.ndarray, threshold: float = 0.9
) -> float:
    """Return the error rate among predictions above a confidence threshold."""
    labels = np.asarray(y_true, dtype=float)
    probabilities = np.asarray(y_prob, dtype=float)
    selected = probabilities >= threshold
    if not np.any(selected):
        return 0.0
    return float(np.mean(labels[selected] != 1.0))


def compute_segmentation_confidence(probabilities: np.ndarray) -> float:
    """Return mean per-pixel maximum class probability for segmentation."""
    values = np.asarray(probabilities, dtype=float)
    if values.ndim < 3:
        raise ValueError("segmentation probabilities require class and spatial axes")
    return float(np.mean(np.max(values, axis=1)))


def compute_ensemble_disagreement(member_probabilities: np.ndarray) -> float:
    """Return mean member variance, the named ensemble disagreement measure."""
    values = np.asarray(member_probabilities, dtype=float)
    if values.ndim < 2 or values.shape[0] < 2:
        raise ValueError("ensemble disagreement requires at least two members")
    return float(np.mean(np.var(values, axis=0)))


def compute_risk_coverage(
    y_true: np.ndarray, y_prob: np.ndarray, coverages: tuple[float, ...] = (1.0, 0.9, 0.8)
) -> tuple[RiskCoveragePoint, ...]:
    """Return selective risk after retaining the most confident predictions."""
    labels = np.asarray(y_true, dtype=float)
    probabilities = np.asarray(y_prob, dtype=float)
    confidence = np.maximum(probabilities, 1.0 - probabilities)
    predicted = (probabilities >= 0.5).astype(float)
    order = np.argsort(-confidence, kind="stable")
    points: list[RiskCoveragePoint] = []
    for requested_coverage in coverages:
        count = max(1, min(len(labels), int(np.ceil(len(labels) * requested_coverage))))
        selected = order[:count]
        points.append(
            RiskCoveragePoint(
                coverage=float(count / len(labels)),
                risk=float(np.mean(predicted[selected] != labels[selected])),
            )
        )
    return tuple(points)


def compute_subgroup_metric(
    name: str, y_true: np.ndarray, y_prob: np.ndarray
) -> SubgroupMetric:
    """Compute the required reliability metrics for one subgroup."""
    labels = np.asarray(y_true, dtype=float)
    probabilities = np.asarray(y_prob, dtype=float)
    return SubgroupMetric(
        name=name,
        sample_count=len(labels),
        ece=compute_ece(labels, probabilities),
        brier_score=compute_brier_score(labels, probabilities),
        nll=compute_nll(labels, probabilities),
    )


__all__ = [
    "ReliabilityData",
    "RiskCoveragePoint",
    "SubgroupMetric",
    "compute_brier_score",
    "compute_coverage",
    "compute_ece",
    "compute_ensemble_disagreement",
    "compute_false_confidence_rate",
    "compute_interval_width",
    "compute_nll",
    "compute_reliability_data",
    "compute_risk_coverage",
    "compute_segmentation_confidence",
    "compute_subgroup_metric",
]
