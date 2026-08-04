"""Conformal calibration layer — MAPIE wrapper for prediction intervals.

Wraps ML model predictions with MAPIE conformal prediction to produce
statistically guaranteed prediction intervals. Computes and stores
calibration metrics: Brier score, ECE, reliability diagram data, NLL,
conformal coverage, interval width, false-confidence rate.

MAPIE 1.4.1 API mapping (task spec used pre-1.0 names):
  - MapieRegressor        -> SplitConformalRegressor  (static calibration)
  - MapieTimeSeriesRegressor -> TimeSeriesRegressor     (EnbPI, update() for streaming)

Geographically weighted conformal: calibrate per H3 zone to handle spatial
distribution shift. Pass ``h3_zone=`` to fit/predict/partial_fit to route
to a per-zone sub-calibrator.
"""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np
from mapie.regression import SplitConformalRegressor, TimeSeriesRegressor
from sklearn.linear_model import LinearRegression

from app.fusion.calibration_metrics import (
    compute_brier_score,
    compute_coverage,
    compute_ece,
    compute_false_confidence_rate,
    compute_interval_width,
    compute_nll,
    compute_reliability_data,
)
from app.fusion.calibration_policy import (
    CALIBRATION_POLICIES,
    AbstentionDecision,
    AbstentionInput,
    CalibrationPolicy,
    OutputType,
    ReleaseGateDecision,
    decide_abstention,
    policy_for_output_type,
    release_gate,
)

# Default miscoverage rate alpha = 0.1 -> 90% confidence level.
_DEFAULT_ALPHA = 0.1
# Train/calibration split ratio for the internal conformalization.
_CALIB_FRACTION = 0.3


class _EstimatorLike(Protocol):
    """Structural type for sklearn-compatible estimators."""

    def fit(self, X: np.ndarray, y: np.ndarray) -> object: ...

    def predict(self, X: np.ndarray) -> np.ndarray: ...


class ConformalCalibrator:
    """Conformal calibration wrapper around a scikit-learn estimator.

    Supports two modes:
      - ``static`` (default): SplitConformalRegressor for one-shot calibration.
      - ``streaming``: TimeSeriesRegressor with EnbPI and ``partial_fit``
        (calls MAPIE's ``update``) for streaming interval updates.

    Geographically weighted conformal is supported via the ``h3_zone``
    parameter on fit/predict/partial_fit — each zone gets an independent
    sub-calibrator.
    """

    def __init__(
        self,
        estimator: _EstimatorLike | None = None,
        alpha: float = _DEFAULT_ALPHA,
        mode: str = "static",
    ) -> None:
        self._estimator = estimator or LinearRegression()
        self._alpha = alpha
        self._mode = mode
        self._calibrator: SplitConformalRegressor | TimeSeriesRegressor | None = None
        self._zones: dict[str, ConformalCalibrator] = {}
        self._metrics: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Fit / predict / partial_fit
    # ------------------------------------------------------------------

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        alpha: float = _DEFAULT_ALPHA,
        h3_zone: str | None = None,
    ) -> ConformalCalibrator:
        """Fit calibrator with an internal train/calibration split.

        ``alpha`` is the miscoverage rate (1 - confidence_level).
        """
        if h3_zone is not None:
            return self._zone(h3_zone).fit(X, y, alpha)
        self._alpha = alpha
        confidence_level = 1.0 - alpha
        xa = np.asarray(X, dtype=float)
        ya = np.asarray(y, dtype=float)
        n = len(ya)
        split = max(1, int(n * (1.0 - _CALIB_FRACTION)))
        cal: SplitConformalRegressor | TimeSeriesRegressor
        if self._mode == "streaming":
            cal = TimeSeriesRegressor(estimator=self._estimator, method="enbpi")
        else:
            cal = SplitConformalRegressor(
                estimator=self._estimator,
                confidence_level=confidence_level,
                prefit=False,
            )
        cal.fit(xa[:split], ya[:split])
        cal.conformalize(xa[split:], ya[split:])
        self._calibrator = cal
        return self

    def predict(self, X: np.ndarray, h3_zone: str | None = None) -> dict[str, Any]:
        """Return point prediction, interval, and interval width."""
        if h3_zone is not None:
            return self._zone(h3_zone).predict(X)
        if self._calibrator is None:
            raise RuntimeError("Calibrator not fitted — call fit() first")
        cal = self._calibrator
        xa = np.asarray(X, dtype=float)
        if isinstance(cal, TimeSeriesRegressor):
            y_pred, y_int = cal.predict(xa, confidence_level=1.0 - self._alpha)
        else:
            y_pred, y_int = cal.predict_interval(xa)
        lower = y_int[:, 0, 0]
        upper = y_int[:, 1, 0]
        return {
            "prediction": y_pred.tolist(),
            "interval_lower": lower.tolist(),
            "interval_upper": upper.tolist(),
            "interval_width": (upper - lower).tolist(),
            "alpha": self._alpha,
        }

    def partial_fit(
        self, X: np.ndarray, y: np.ndarray, h3_zone: str | None = None
    ) -> ConformalCalibrator:
        """Streaming update via EnbPI (TimeSeriesRegressor.update)."""
        if h3_zone is not None:
            return self._zone(h3_zone).partial_fit(X, y)
        cal = self._calibrator
        if cal is None:
            raise RuntimeError("Calibrator not fitted — call fit() first")
        if not isinstance(cal, TimeSeriesRegressor):
            raise TypeError("partial_fit requires mode='streaming'")
        cal.update(np.asarray(X, dtype=float), np.asarray(y, dtype=float))
        return self

    compute_brier_score = staticmethod(compute_brier_score)
    compute_ece = staticmethod(compute_ece)
    compute_reliability_data = staticmethod(compute_reliability_data)
    compute_coverage = staticmethod(compute_coverage)
    compute_nll = staticmethod(compute_nll)
    compute_false_confidence_rate = staticmethod(compute_false_confidence_rate)

    # ------------------------------------------------------------------
    # Dashboard / zone management
    # ------------------------------------------------------------------

    def get_metrics(self) -> dict[str, Any]:
        """Return all stored metrics for the calibration dashboard."""
        return {
            "alpha": self._alpha,
            "mode": self._mode,
            "fitted": self._calibrator is not None,
            "h3_zones": list(self._zones.keys()),
            **self._metrics,
        }

    def store_metrics(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray | None = None,
        y_pred_lower: np.ndarray | None = None,
        y_pred_upper: np.ndarray | None = None,
    ) -> dict[str, Any]:
        """Compute and store all metrics from a calibration evaluation."""
        metrics: dict[str, Any] = {}
        if y_prob is not None:
            metrics["brier_score"] = self.compute_brier_score(y_true, y_prob)
            metrics["ece"] = self.compute_ece(y_true, y_prob)
            metrics["reliability"] = self.compute_reliability_data(y_true, y_prob)
            metrics["nll"] = self.compute_nll(y_true, y_prob)
            metrics["false_confidence_rate"] = self.compute_false_confidence_rate(
                y_true, y_prob
            )
        if y_pred_lower is not None and y_pred_upper is not None:
            metrics["conformal_coverage"] = self.compute_coverage(
                y_true, y_pred_lower, y_pred_upper
            )
            metrics["interval_width"] = compute_interval_width(y_pred_lower, y_pred_upper)
        self._metrics = metrics
        return metrics

    def _zone(self, h3_zone: str) -> ConformalCalibrator:
        """Get or create a per-H3-zone sub-calibrator."""
        if h3_zone not in self._zones:
            self._zones[h3_zone] = ConformalCalibrator(
                estimator=self._estimator, alpha=self._alpha, mode=self._mode
            )
        return self._zones[h3_zone]


__all__ = [
    "CALIBRATION_POLICIES",
    "AbstentionDecision",
    "AbstentionInput",
    "CalibrationPolicy",
    "ConformalCalibrator",
    "OutputType",
    "ReleaseGateDecision",
    "decide_abstention",
    "policy_for_output_type",
    "release_gate",
]
