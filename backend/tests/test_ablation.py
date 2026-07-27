"""Tests for the ablation study runner (T45).

Verifies: runs 9 ablations + 1 full system = 10 results, produces comparison
table, at least 3 ablations show prevented_harm decrease, full system has
highest prevented_harm, ablation types are distinct.

No DB needed — operates on the in-memory testbed.
Run: docker compose run --rm -e PYTHONPATH=/app backend sh -c \
    "pip install pytest -q && python -m pytest tests/test_ablation.py -q"
"""

from __future__ import annotations

import pytest

from app.eval.ablation import ABLATION_TYPES, AblationRunner
from app.eval.testbed import DigitalTwinTestbed
from app.eval.testbed_types import TestbedParams

DEFAULT_PARAMS = TestbedParams()


@pytest.fixture
def testbed() -> DigitalTwinTestbed:
    tb = DigitalTwinTestbed()
    tb.generate(seed=42, params=DEFAULT_PARAMS)
    return tb


@pytest.fixture
def runner() -> AblationRunner:
    return AblationRunner()


@pytest.fixture
def results(testbed, runner):
    return runner.run_all_ablations(testbed, seed=42)


def test_runs_all_ablations(results):
    """Runs 9 ablations + 1 full system = 10 results."""
    assert len(results) == 10
    assert "full_system" in results
    for ablation_type in ABLATION_TYPES:
        assert ablation_type in results
    for r in results.values():
        assert 0.0 <= r.metrics.prevented_harm <= 1.0
        assert r.metrics.actions_taken > 0
        assert r.metrics.high_severity_events > 0


def test_comparison_table(results, runner):
    """Produces comparison table showing prevented_harm for each ablation vs full system."""
    table = runner.compare_ablations(results)
    assert "full_system" in table
    assert "prevented_harm" in table
    assert "delta" in table
    for ablation_type in ABLATION_TYPES:
        assert ablation_type in table


def test_component_impact(results, runner):
    """At least 3 ablations show statistically significant degradation."""
    significant = runner.get_significant_ablations(results, threshold=0.05)
    assert len(significant) >= 3, (
        f"Expected at least 3 significant ablations, got {len(significant)}: {significant}"
    )


def test_full_system_highest(results):
    """Full system has highest prevented_harm."""
    full = results["full_system"].metrics.prevented_harm
    for key, r in results.items():
        if key == "full_system":
            continue
        assert full >= r.metrics.prevented_harm, (
            f"full_system prevented_harm {full} should be >= "
            f"{key} {r.metrics.prevented_harm}"
        )


def test_ablation_types_distinct(results):
    """Ablation types are distinct (each disables a different component)."""
    ablation_results = {k: v for k, v in results.items() if k != "full_system"}
    assert len(ablation_results) == 9
    disabled_sets = [set(r.components_disabled) for r in ablation_results.values()]
    # Each ablation disables exactly one component
    for disabled in disabled_sets:
        assert len(disabled) == 1, f"Expected 1 disabled component, got {disabled}"
    # All disabled components are distinct
    all_disabled = [next(iter(s)) for s in disabled_sets]
    assert len(set(all_disabled)) == 9, (
        f"Expected 9 distinct disabled components, got {len(set(all_disabled))}"
    )
