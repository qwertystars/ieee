"""Tests for WorldStateEstimator Dynamic Bayesian Network.

Stopping conditions verified:
  - 3-state flood severity, 3 time slices, probabilities sum to 1.0
  - Prior P(severe)=0.1, with severe evidence P(severe) > 0.5
"""

from __future__ import annotations

import pytest

from app.fusion.world_state import (
    WorldStateEstimator,
    discretize_sensor,
)

# 3-state flood severity for stopping condition tests.
STATES_3 = ("none", "moderate", "severe")
PRIOR_3 = {"none": 0.7, "moderate": 0.2, "severe": 0.1}


def test_forward_inference():
    """3-state flood severity, 3 time slices, probabilities sum to 1.0."""
    est = WorldStateEstimator(
        hazard_types=("flood",),
        states=STATES_3,
        prior=PRIOR_3,
    )

    # Add evidence at 3 time slices.
    est.add_evidence({("flood_sensor_reading", 0): "severe"})
    est.add_evidence({("flood_sensor_reading", 1): "severe"})
    est.add_evidence({("flood_sensor_reading", 2): "severe"})

    # Query each time slice — probabilities must sum to 1.0.
    for t in range(3):
        dist = est.get_state_distribution("flood", t)
        assert sum(dist.values()) == pytest.approx(1.0, abs=1e-6)
        assert set(dist.keys()) == set(STATES_3)


def test_evidence_increases_severe():
    """Prior P(severe)=0.1, with severe evidence P(severe) > 0.5."""
    est = WorldStateEstimator(
        hazard_types=("flood",),
        states=STATES_3,
        prior=PRIOR_3,
    )

    # Prior: P(severe) = 0.1.
    prior = est.filter_state("flood")
    assert prior["severe"] == pytest.approx(0.1, abs=0.05)

    # Add severe evidence.
    est.add_evidence({("flood_sensor_reading", 0): "severe"})

    # Posterior: P(severe) > 0.5.
    posterior = est.filter_state("flood")
    assert posterior["severe"] > 0.5


def test_transition_matrix():
    """State propagates over time slices via transition matrix."""
    est = WorldStateEstimator(
        hazard_types=("flood",),
        states=STATES_3,
        prior=PRIOR_3,
    )

    # Strong evidence at slice 0.
    est.add_evidence({("flood_sensor_reading", 0): "severe"})
    dist_0 = est.get_state_distribution("flood", 0)
    p_severe_0 = dist_0["severe"]

    # No evidence at slice 1 — prediction via transition only.
    dist_1 = est.get_state_distribution("flood", 1)
    p_severe_1 = dist_1["severe"]

    # Transition spreads probability: P(severe) decreases over time.
    assert p_severe_1 < p_severe_0
    # But persistence keeps it above the prior.
    assert p_severe_1 > 0.1


def test_sensor_model():
    """Sensor reading updates state probability."""
    est = WorldStateEstimator(
        hazard_types=("flood",),
        states=STATES_3,
        prior=PRIOR_3,
    )

    prior = est.filter_state("flood")

    # Add sensor reading indicating moderate (index 1).
    est.add_evidence({("flood_sensor_reading", 0): 1})
    posterior = est.filter_state("flood")

    # P(moderate) should increase.
    assert posterior["moderate"] > prior["moderate"]


def test_multiple_hazard_types():
    """DBN handles multiple hazard types independently."""
    est = WorldStateEstimator(
        hazard_types=("flood", "fire"),
        states=STATES_3,
        prior=PRIOR_3,
    )

    # Add flood evidence only.
    est.add_evidence({("flood_sensor_reading", 0): "severe"})

    flood_dist = est.filter_state("flood")
    fire_dist = est.filter_state("fire")

    # Flood should be affected by evidence.
    assert flood_dist["severe"] > 0.5
    # Fire should remain at prior (no evidence).
    assert fire_dist["severe"] == pytest.approx(0.1, abs=0.05)


def test_discretize_sensor():
    """Continuous sensor values map to correct discrete bins."""
    assert discretize_sensor(0.0) == 0  # none
    assert discretize_sensor(0.3) == 0  # none
    assert discretize_sensor(0.5) == 1  # minor
    assert discretize_sensor(1.0) == 1  # minor
    assert discretize_sensor(1.5) == 2  # moderate
    assert discretize_sensor(2.0) == 2  # moderate
    assert discretize_sensor(3.0) == 3  # severe
    assert discretize_sensor(4.0) == 3  # severe
    assert discretize_sensor(5.0) == 4  # extreme
    assert discretize_sensor(10.0) == 4  # extreme
    assert discretize_sensor(100.0) == 4  # extreme
