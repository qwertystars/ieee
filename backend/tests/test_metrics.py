"""Tests for metrics collection (T44).

Verifies: all 6 metric categories collected with >0 metrics each,
Brier score in [0,1], prevented_harm > 0 for SAGE, equity metrics
show disparity, resilience metrics include latency.

No DB needed — operates on the in-memory testbed.
Run: docker compose run --rm -e PYTHONPATH=/app backend sh -c \
    "pip install pytest -q && python -m pytest tests/test_metrics.py -q"
"""

from __future__ import annotations

import pytest

from app.eval.baselines import BaselineRunner
from app.eval.metrics import MetricsCollector
from app.eval.testbed import DigitalTwinTestbed
from app.eval.testbed_types import TestbedParams

DEFAULT_PARAMS = TestbedParams()


@pytest.fixture
def testbed() -> DigitalTwinTestbed:
    tb = DigitalTwinTestbed()
    tb.generate(seed=42, params=DEFAULT_PARAMS)
    return tb


@pytest.fixture
def runner() -> BaselineRunner:
    return BaselineRunner()


@pytest.fixture
def baseline_results(testbed, runner):
    return runner.run_all_baselines(testbed, seed=42)


@pytest.fixture
def collector() -> MetricsCollector:
    return MetricsCollector()


def test_all_categories(testbed, baseline_results, collector):
    """All 6 categories collected with >0 metrics each."""
    metrics = collector.collect_all(testbed, baseline_results)
    assert len(metrics) == 6
    expected = {"perception", "uncertainty", "operational",
                "resilience", "human_factors", "equity"}
    assert set(metrics.keys()) == expected
    for cat, vals in metrics.items():
        assert len(vals) > 0, f"category {cat} has 0 metrics"


def test_brier_score_in_range(testbed, baseline_results, collector):
    """Brier score is in [0, 1]."""
    metrics = collector.collect_uncertainty_metrics(testbed, baseline_results)
    brier = metrics["brier_score"]
    assert 0.0 <= brier <= 1.0, f"brier_score {brier} not in [0,1]"


def test_prevented_harm_sage(testbed, baseline_results, collector):
    """prevented_harm > 0 for SAGE baseline."""
    sage = baseline_results["baseline_4_resqnet_sage"]
    assert sage.metrics.prevented_harm > 0.0, "SAGE prevented_harm should be > 0"
    op = collector.collect_operational_metrics(testbed, baseline_results)
    assert op["urgent_demand_served"] > 0.0
    assert op["expected_casualties_avoided"] > 0.0


def test_equity_disparity(testbed, baseline_results, collector):
    """Equity metrics show disparity (resource_allocation_disparity > 0)."""
    eq = collector.collect_equity_metrics(testbed, baseline_results)
    assert eq["resource_allocation_disparity"] > 0.0, "expected non-zero disparity"
    assert "response_delay_by_vulnerability" in eq
    assert len(eq["response_delay_by_vulnerability"]) == 3
    assert "low" in eq["response_delay_by_vulnerability"]
    assert "high" in eq["response_delay_by_vulnerability"]


def test_resilience_latency(testbed, baseline_results, collector):
    """Resilience metrics include latency."""
    res = collector.collect_resilience_metrics(testbed, baseline_results)
    assert "p50_sensor_to_map_latency_ms" in res
    assert "p95_sensor_to_map_latency_ms" in res
    assert "p50_report_to_recommendation_latency_ms" in res
    assert "p95_report_to_recommendation_latency_ms" in res
    assert "data_loss_window_pct" in res
    assert "pct_capability_under_connectivity_loss" in res


def test_perception_metrics_complete(testbed, baseline_results, collector):
    """Perception metrics include precision, recall, F1, mIoU."""
    p = collector.collect_perception_metrics(testbed, baseline_results)
    assert 0.0 <= p["precision"] <= 1.0
    assert 0.0 <= p["recall"] <= 1.0
    assert 0.0 <= p["f1"] <= 1.0
    assert 0.0 <= p["miou_flood_extent"] <= 1.0
    assert p["median_geolocation_error_m"] >= 0.0


def test_human_factors_automated(testbed, baseline_results, collector):
    """Human-factors metrics are all automated proxies."""
    hf = collector.collect_human_factors_metrics(testbed, baseline_results)
    assert 0.0 <= hf["correct_override_rate"] <= 1.0
    assert 0.0 <= hf["harmful_override_rate"] <= 1.0
    assert 0.0 <= hf["nasa_tlx_proxy"] <= 1.0
    assert hf["simulated_operator_decision_time_ms"] >= 0.0
