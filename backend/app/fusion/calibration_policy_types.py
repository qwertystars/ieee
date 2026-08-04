from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OutputType(StrEnum):
    SAR_SEGMENTATION = "sar_segmentation_confidence"
    DAMAGE_PROBABILITY = "damage_probability"
    NLP_PROBABILITY = "nlp_probability"
    ENSEMBLE_DISAGREEMENT = "ensemble_disagreement"
    CONFORMAL_INTERVAL = "conformal_interval"
    RISK_COVERAGE = "risk_coverage"


@dataclass(frozen=True, slots=True)
class CalibrationThresholds:
    confidence_min: float
    disagreement_max: float
    ece_max: float
    brier_max: float
    nll_max: float
    coverage_min: float
    coverage_max: float
    risk_max: float
    shift_ece_delta: float
    shift_coverage_delta: float


@dataclass(frozen=True, slots=True)
class CalibrationPolicy:
    output_type: OutputType
    method: str
    confidence_level: float
    minimum_samples: int
    subgroup_minimum_samples: int
    hazard_minimum_samples: int
    required_metrics: tuple[str, ...]
    thresholds: CalibrationThresholds
    shift_trigger: str
    recalibration_cadence_days: int
    test_tuning_forbidden: bool


@dataclass(frozen=True, slots=True)
class AbstentionInput:
    output_type: OutputType
    calibration_available: bool
    confidence: float | None = None
    disagreement: float | None = None
    shift_detected: bool = False


@dataclass(frozen=True, slots=True)
class AbstentionDecision:
    abstain: bool
    reason: str
    output_type: OutputType


@dataclass(frozen=True, slots=True)
class ReleaseGateDecision:
    allowed: bool
    status: str
    reason: str
