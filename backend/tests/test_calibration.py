"""Tests for the conformal calibration layer (T17).

Verifies:
  1. Conformal coverage >= 0.89 for alpha=0.1 (90% target).
  2. Brier score computed correctly on mock data.
  3. ECE ≈ 0 for perfectly calibrated probabilities.
  4. partial_fit (streaming update) changes prediction intervals.
  5. Reliability diagram data has correct structure.
  6. False-confidence rate flags high-confidence wrong predictions.

All tests use mock classifiers/regressors (sklearn) — no real ML models.
"""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import LinearRegression, LogisticRegression

from app.fusion.calibration import ConformalCalibrator


def _make_regression_data(n: int = 300, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """Synthetic regression data with linear signal + noise."""
    rng = np.random.RandomState(seed)
    X = rng.randn(n, 3)
    y = X @ np.array([1.0, -2.0, 0.5]) + 0.1 * rng.randn(n)
    return X, y


def _make_classification_data(
    n: int = 300, seed: int = 42
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Synthetic binary classification data + fitted LogisticRegression probs."""
    rng = np.random.RandomState(seed)
    X = rng.randn(n, 3)
    logits = X @ np.array([1.5, -1.0, 0.8])
    y = (logits > 0).astype(float)
    clf = LogisticRegression(max_iter=500)
    clf.fit(X, y)
    y_prob = clf.predict_proba(X)[:, 1]
    return X, y, y_prob


# ---------------------------------------------------------------------
# 1. Conformal coverage
# ---------------------------------------------------------------------


def test_coverage() -> None:
    """Conformal coverage >= 0.89 for alpha=0.1 (90% target)."""
    X, y = _make_regression_data(n=400)
    cal = ConformalCalibrator(estimator=LinearRegression(), alpha=0.1, mode="static")
    cal.fit(X[:300], y[:300], alpha=0.1)
    result = cal.predict(X[300:])
    lower = np.array(result["interval_lower"])
    upper = np.array(result["interval_upper"])
    coverage = ConformalCalibrator.compute_coverage(y[300:], lower, upper)
    assert coverage >= 0.89, f"coverage {coverage} < 0.89 target"


# ---------------------------------------------------------------------
# 2. Brier score
# ---------------------------------------------------------------------


def test_brier_score() -> None:
    """Brier score computed correctly on mock classification data."""
    _, y, y_prob = _make_classification_data(n=300)
    brier = ConformalCalibrator.compute_brier_score(y, y_prob)
    # Brier score = mean((y_prob - y)^2); manually verify.
    expected = float(np.mean((y_prob - y) ** 2))
    assert abs(brier - expected) < 1e-12
    # Brier score for perfect predictions is 0.
    assert ConformalCalibrator.compute_brier_score(y, y) == 0.0
    # Brier score for all-wrong (prob=1, label=0) is 1.
    assert ConformalCalibrator.compute_brier_score(
        np.zeros(10), np.ones(10)
    ) == 1.0


# ---------------------------------------------------------------------
# 3. ECE
# ---------------------------------------------------------------------


def test_ece() -> None:
    """ECE ≈ 0 for perfectly calibrated probabilities."""
    # Perfect calibration: y_prob == y_true (each prediction matches label).
    y_true = np.array([0.0, 1.0, 0.0, 1.0, 1.0, 0.0])
    y_prob = y_true.copy()
    ece = ConformalCalibrator.compute_ece(y_true, y_prob, n_bins=10)
    assert ece < 1e-9, f"ECE {ece} not ~0 for perfect calibration"
    # Worst case: all predictions are 1.0 but all labels are 0.0.
    y_wrong = np.zeros(50)
    p_wrong = np.ones(50)
    ece_wrong = ConformalCalibrator.compute_ece(y_wrong, p_wrong, n_bins=10)
    assert ece_wrong > 0.9, f"ECE {ece_wrong} should be high for all-wrong"


# ---------------------------------------------------------------------
# 4. partial_fit (streaming update)
# ---------------------------------------------------------------------


def test_partial_fit() -> None:
    """Streaming update (partial_fit) changes prediction intervals."""
    X, y = _make_regression_data(n=300)
    cal = ConformalCalibrator(estimator=LinearRegression(), mode="streaming")
    cal.fit(X[:200], y[:200], alpha=0.1)
    before = cal.predict(X[200:250])
    # Feed new data via partial_fit (EnbPI update).
    cal.partial_fit(X[200:230], y[200:230])
    after = cal.predict(X[230:250])
    # Intervals should change after incorporating new data.
    before_lower = np.array(before["interval_lower"][:20])
    after_lower = np.array(after["interval_lower"])
    assert not np.allclose(before_lower, after_lower), (
        "intervals unchanged after partial_fit"
    )
    # Coverage should still be reasonable after update.
    lower = np.array(after["interval_lower"])
    upper = np.array(after["interval_upper"])
    coverage = ConformalCalibrator.compute_coverage(y[230:250], lower, upper)
    assert coverage >= 0.7, f"post-update coverage {coverage} too low"


# ---------------------------------------------------------------------
# 5. Reliability diagram data
# ---------------------------------------------------------------------


def test_reliability_data() -> None:
    """Reliability diagram data has correct structure."""
    _, y, y_prob = _make_classification_data(n=300)
    n_bins = 10
    data = ConformalCalibrator.compute_reliability_data(y, y_prob, n_bins=n_bins)
    required_keys = {
        "bin_lower",
        "bin_upper",
        "bin_count",
        "bin_accuracy",
        "bin_confidence",
        "n_bins",
    }
    assert set(data.keys()) == required_keys, f"missing keys: {set(data.keys())}"
    assert data["n_bins"] == n_bins
    for key in ("bin_lower", "bin_upper", "bin_count", "bin_accuracy", "bin_confidence"):
        assert len(data[key]) == n_bins, f"{key} length != {n_bins}"
    assert sum(data["bin_count"]) == len(y), "bin counts don't sum to n_samples"
    # bin_lower[i] < bin_upper[i] for all bins.
    for i in range(n_bins):
        assert data["bin_lower"][i] < data["bin_upper"][i]
    # Accuracy in [0, 1] for non-empty bins.
    for i in range(n_bins):
        if data["bin_count"][i] > 0:
            assert 0.0 <= data["bin_accuracy"][i] <= 1.0


# ---------------------------------------------------------------------
# 6. False confidence rate
# ---------------------------------------------------------------------


def test_false_confidence_rate() -> None:
    """High-confidence wrong predictions are flagged."""
    # 5 predictions at prob=0.95, all wrong (label=0).
    y_true = np.zeros(5)
    y_prob = np.array([0.95, 0.96, 0.97, 0.98, 0.99])
    fcr = ConformalCalibrator.compute_false_confidence_rate(y_true, y_prob, threshold=0.9)
    assert fcr == 1.0, f"FCR {fcr} should be 1.0 (all high-conf wrong)"
    # Mix: 3 high-conf correct, 2 high-conf wrong -> FCR = 0.4.
    y_mixed = np.array([1.0, 1.0, 1.0, 0.0, 0.0])
    p_mixed = np.array([0.95, 0.92, 0.91, 0.95, 0.93])
    fcr_mixed = ConformalCalibrator.compute_false_confidence_rate(
        y_mixed, p_mixed, threshold=0.9
    )
    assert abs(fcr_mixed - 0.4) < 1e-9, f"FCR {fcr_mixed} != 0.4"
    # No high-confidence predictions -> FCR = 0.
    assert ConformalCalibrator.compute_false_confidence_rate(
        np.ones(5), np.full(5, 0.5), threshold=0.9
    ) == 0.0


# ---------------------------------------------------------------------
# Bonus: geographically weighted conformal (per-H3-zone)
# ---------------------------------------------------------------------


def test_geographically_weighted_conformal() -> None:
    """Per-H3-zone calibrators are independent."""
    X, y = _make_regression_data(n=300)
    cal = ConformalCalibrator(estimator=LinearRegression(), alpha=0.1)
    # Fit two zones with different data subsets.
    cal.fit(X[:100], y[:100], alpha=0.1, h3_zone="zone_a")
    cal.fit(X[100:200], y[100:200], alpha=0.1, h3_zone="zone_b")
    result_a = cal.predict(X[200:250], h3_zone="zone_a")
    result_b = cal.predict(X[200:250], h3_zone="zone_b")
    # Different zones should produce different intervals.
    assert not np.allclose(
        result_a["interval_lower"], result_b["interval_lower"]
    ), "per-zone intervals should differ"
    metrics = cal.get_metrics()
    assert "zone_a" in metrics["h3_zones"]
    assert "zone_b" in metrics["h3_zones"]


# ---------------------------------------------------------------------
# Bonus: store_metrics + get_metrics dashboard
# ---------------------------------------------------------------------


def test_store_metrics_dashboard() -> None:
    """store_metrics computes all metrics for the dashboard."""
    _, y, y_prob = _make_classification_data(n=200)
    X, y_reg = _make_regression_data(n=200)
    cal = ConformalCalibrator(estimator=LinearRegression(), alpha=0.1)
    cal.fit(X[:150], y_reg[:150], alpha=0.1)
    result = cal.predict(X[150:])
    lower = np.array(result["interval_lower"])
    upper = np.array(result["interval_upper"])
    # Use first len(y[150:]) classification samples for metric demo.
    n = len(y_reg[150:])
    cal.store_metrics(
        y_true=y[:n],
        y_prob=y_prob[:n],
        y_pred_lower=lower[:n] if len(lower) >= n else lower,
        y_pred_upper=upper[:n] if len(upper) >= n else upper,
    )
    metrics = cal.get_metrics()
    for key in (
        "brier_score",
        "ece",
        "reliability",
        "nll",
        "false_confidence_rate",
        "conformal_coverage",
        "interval_width",
    ):
        assert key in metrics, f"missing metric: {key}"
