"""Tests for the four baselines (T43).

Verifies: all 4 baselines run on the same seed, produce different metrics,
ResQNet-SAGE outperforms others on prevented_harm, baseline 1 has no fusion,
and baseline 2 uses FIFO task selection.

No DB needed — operates on the in-memory testbed.
Run: docker compose run --rm -e PYTHONPATH=/app backend sh -c \
    "pip install pytest -q && python -m pytest tests/test_baselines.py -q"
"""

from __future__ import annotations

import pytest

from app.eval.baselines import BaselineRunner
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


def test_all_baselines_run_on_same_seed(testbed, runner):
    """All 4 baselines run on the same testbed seed and produce results."""
    results = runner.run_all_baselines(testbed, seed=42)
    assert len(results) == 4
    for r in results.values():
        assert r.metrics.actions_taken > 0
        assert r.metrics.high_severity_events > 0
        assert 0.0 <= r.metrics.prevented_harm <= 1.0
        assert 0.0 <= r.metrics.coverage <= 1.0


def test_baselines_produce_different_metrics(testbed, runner):
    """Different baselines produce different metrics on the same seed."""
    results = runner.run_all_baselines(testbed, seed=42)
    prevented = [r.metrics.prevented_harm for r in results.values()]
    assert len(set(prevented)) > 1, "baselines should produce different prevented_harm"
    response = [r.metrics.response_time_ms for r in results.values()]
    assert len(set(response)) > 1, "baselines should produce different response_time"


def test_sage_outperforms_on_prevented_harm(testbed, runner):
    """ResQNet-SAGE outperforms other baselines on prevented_harm."""
    results = runner.run_all_baselines(testbed, seed=42)
    sage = results["baseline_4_resqnet_sage"]
    for key, r in results.items():
        if key == "baseline_4_resqnet_sage":
            continue
        assert sage.metrics.prevented_harm >= r.metrics.prevented_harm, (
            f"SAGE prevented_harm {sage.metrics.prevented_harm} should be >= "
            f"{r.name} {r.metrics.prevented_harm}"
        )


def test_baseline_1_has_no_fusion(testbed, runner):
    """Baseline 1 (independent dashboards) has no fusion."""
    result = runner.run_baseline_1_independent_dashboards(testbed, seed=42)
    assert result.uses_fusion is False
    assert result.selection_policy == "random_feed"


def test_baseline_2_uses_fifo(testbed, runner):
    """Baseline 2 (unified visualization) uses FIFO task selection."""
    result = runner.run_baseline_2_unified_visualization(testbed, seed=42)
    assert result.selection_policy == "fifo"
    assert result.uses_fusion is False
    obs_indices = [a.obs_idx for a in result.actions]
    assert obs_indices == sorted(obs_indices), "FIFO should process in timestamp order"


def test_comparison(testbed, runner):
    """Comparison: all 4 baselines run on same seed, SAGE outperforms on prevented_harm."""
    results = runner.run_all_baselines(testbed, seed=42)
    table = runner.compare_baselines(results)
    assert "independent_dashboards" in table
    assert "unified_visualization" in table
    assert "current_resqnet" in table
    assert "resqnet_sage" in table
    sage = results["baseline_4_resqnet_sage"]
    others = [r for k, r in results.items() if k != "baseline_4_resqnet_sage"]
    assert all(sage.metrics.prevented_harm >= o.metrics.prevented_harm for o in others)
