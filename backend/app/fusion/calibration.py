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

    # ------------------------------------------------------------------
    # Metric utilities (static — accept raw arrays)
    # ------------------------------------------------------------------

    @staticmethod
    def compute_brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
        """Brier score = mean((y_prob - y_true)^2) for binary labels."""
        y_true = np.asarray(y_true, dtype=float)
        y_prob = np.asarray(y_prob, dtype=float)
        return float(np.mean((y_prob - y_true) ** 2))

    @staticmethod
    def compute_ece(
        y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10
    ) -> float:
        """Expected Calibration Error.

        Bins predictions by confidence, computes |accuracy - confidence|
        per bin weighted by bin proportion.
        """
        y_true = np.asarray(y_true, dtype=float)
        y_prob = np.asarray(y_prob, dtype=float)
        bins = np.linspace(0.0, 1.0, n_bins + 1)
        ece = 0.0
        n = len(y_true)
        for i in range(n_bins):
            mask = (y_prob >= bins[i]) & (y_prob < bins[i + 1])
            if i == n_bins - 1:
                mask = (y_prob >= bins[i]) & (y_prob <= bins[i + 1])
            count = int(np.sum(mask))
            if count == 0:
                continue
            acc = float(np.mean(y_true[mask]))
            conf = float(np.mean(y_prob[mask]))
            ece += (count / n) * abs(acc - conf)
        return ece

    @staticmethod
    def compute_reliability_data(
        y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10
    ) -> dict[str, Any]:
        """Reliability diagram data: per-bin accuracy, confidence, count."""
        y_true = np.asarray(y_true, dtype=float)
        y_prob = np.asarray(y_prob, dtype=float)
        bins = np.linspace(0.0, 1.0, n_bins + 1)
        bin_lower: list[float] = []
        bin_upper: list[float] = []
        bin_count: list[int] = []
        bin_accuracy: list[float] = []
        bin_confidence: list[float] = []
        for i in range(n_bins):
            mask = (y_prob >= bins[i]) & (y_prob < bins[i + 1])
            if i == n_bins - 1:
                mask = (y_prob >= bins[i]) & (y_prob <= bins[i + 1])
            count = int(np.sum(mask))
            bin_lower.append(float(bins[i]))
            bin_upper.append(float(bins[i + 1]))
            bin_count.append(count)
            if count == 0:
                bin_accuracy.append(0.0)
                bin_confidence.append(float(bins[i]))
                continue
            bin_accuracy.append(float(np.mean(y_true[mask])))
            bin_confidence.append(float(np.mean(y_prob[mask])))
        return {
            "bin_lower": bin_lower,
            "bin_upper": bin_upper,
            "bin_count": bin_count,
            "bin_accuracy": bin_accuracy,
            "bin_confidence": bin_confidence,
            "n_bins": n_bins,
        }

    @staticmethod
    def compute_coverage(
        y_true: np.ndarray, y_pred_lower: np.ndarray, y_pred_upper: np.ndarray
    ) -> float:
        """Fraction of true values within [lower, upper] interval."""
        y_true = np.asarray(y_true, dtype=float)
        lo = np.asarray(y_pred_lower, dtype=float)
        hi = np.asarray(y_pred_upper, dtype=float)
        return float(np.mean((y_true >= lo) & (y_true <= hi)))

    @staticmethod
    def compute_nll(y_true: np.ndarray, y_prob: np.ndarray) -> float:
        """Negative log-likelihood for binary labels (clipped to avoid log 0)."""
        y_true = np.asarray(y_true, dtype=float)
        y_prob = np.clip(np.asarray(y_prob, dtype=float), 1e-15, 1.0 - 1e-15)
        return float(-np.mean(y_true * np.log(y_prob) + (1 - y_true) * np.log(1 - y_prob)))

    @staticmethod
    def compute_false_confidence_rate(
        y_true: np.ndarray, y_prob: np.ndarray, threshold: float = 0.9
    ) -> float:
        """Fraction of high-confidence predictions (>= threshold) that are wrong."""
        y_true = np.asarray(y_true, dtype=float)
        y_prob = np.asarray(y_prob, dtype=float)
        high_conf = y_prob >= threshold
        if not np.any(high_conf):
            return 0.0
        wrong = y_true[high_conf] != 1.0
        return float(np.mean(wrong))

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
            metrics["interval_width"] = float(
                np.mean(np.asarray(y_pred_upper) - np.asarray(y_pred_lower))
            )
        self._metrics = metrics
        return metrics

    def _zone(self, h3_zone: str) -> ConformalCalibrator:
        """Get or create a per-H3-zone sub-calibrator."""
        if h3_zone not in self._zones:
            self._zones[h3_zone] = ConformalCalibrator(
                estimator=self._estimator, alpha=self._alpha, mode=self._mode
            )
        return self._zones[h3_zone]


__all__ = ["ConformalCalibrator"]
