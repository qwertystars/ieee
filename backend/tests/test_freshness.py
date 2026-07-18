"""Tests for phenomenon-specific freshness decay (T15)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.fusion.freshness import (
    DEFAULT_TAU,
    TAU_BY_PHENOMENON,
    FreshnessCalculator,
)
from app.lib.time import now_ms

# Fixed reference time for deterministic tests (arbitrary epoch ms).
BASE_TIME_MS = 1_700_000_000_000


@dataclass
class _FakeObs:
    """Minimal observation-like object for freshness tests."""

    observed_at: int
    phenomenon: str


def test_per_type_decay() -> None:
    """Stopping conditions: road 60s F>0.9, road 2h F<0.01, building 1h F>0.9."""
    calc = FreshnessCalculator()

    # Road 60s old: F = exp(-60/600) = 0.9048
    road_60s = calc.compute_freshness(
        observed_at=BASE_TIME_MS - 60_000,
        current_time=BASE_TIME_MS,
        phenomenon="road_passability",
    )
    assert road_60s > 0.9, f"road 60s old F={road_60s} should be > 0.9"

    # Road 2h old: F = exp(-7200/600) = exp(-12) = 6.14e-6
    road_2h = calc.compute_freshness(
        observed_at=BASE_TIME_MS - 2 * 3600_000,
        current_time=BASE_TIME_MS,
        phenomenon="road_passability",
    )
    assert road_2h < 0.01, f"road 2h old F={road_2h} should be < 0.01"

    # Building 1h old: F = exp(-3600/86400) = 0.9592
    building_1h = calc.compute_freshness(
        observed_at=BASE_TIME_MS - 3600_000,
        current_time=BASE_TIME_MS,
        phenomenon="building_footprint",
    )
    assert building_1h > 0.9, f"building 1h old F={building_1h} should be > 0.9"


def test_default_tau() -> None:
    """Unknown phenomenon uses default tau=600."""
    calc = FreshnessCalculator()
    assert calc.get_tau("unknown_phenomenon") == DEFAULT_TAU == 600

    # 60s old with default tau=600: F = exp(-60/600) = 0.9048
    f = calc.compute_freshness(
        observed_at=BASE_TIME_MS - 60_000,
        current_time=BASE_TIME_MS,
        phenomenon="totally_unknown",
    )
    assert abs(f - 0.9048) < 0.001


def test_freshness_zero_age() -> None:
    """Just observed -> F = 1.0."""
    calc = FreshnessCalculator()
    f = calc.compute_freshness(
        observed_at=BASE_TIME_MS,
        current_time=BASE_TIME_MS,
        phenomenon="road_passability",
    )
    assert f == 1.0


def test_freshness_old() -> None:
    """Very old observation -> F approaches 0."""
    calc = FreshnessCalculator()
    # 1 year old road observation
    year_ms = 365 * 24 * 3600_000
    f = calc.compute_freshness(
        observed_at=BASE_TIME_MS - year_ms,
        current_time=BASE_TIME_MS,
        phenomenon="road_passability",
    )
    assert f < 1e-50, f"very old F={f} should approach 0"
    assert f >= 0.0


def test_custom_tau() -> None:
    """update_tau overrides the value for a phenomenon."""
    calc = FreshnessCalculator()

    # Before: road_passability uses default tau=600
    assert calc.get_tau("road_passability") == 600
    f_before = calc.compute_freshness(
        observed_at=BASE_TIME_MS - 60_000,
        current_time=BASE_TIME_MS,
        phenomenon="road_passability",
    )
    # F = exp(-60/600) = 0.9048
    assert abs(f_before - 0.9048) < 0.001

    # Override tau to 10s — same 60s age now decays much faster
    calc.update_tau("road_passability", 10)
    assert calc.get_tau("road_passability") == 10
    f_after = calc.compute_freshness(
        observed_at=BASE_TIME_MS - 60_000,
        current_time=BASE_TIME_MS,
        phenomenon="road_passability",
    )
    # F = exp(-60/10) = exp(-6) = 0.00248
    assert abs(f_after - 0.00248) < 0.001
    assert f_after < f_before


def test_compute_for_observation() -> None:
    """compute_for_observation uses observation fields and current time."""
    calc = FreshnessCalculator()
    # Use real now_ms() so observed_at is current relative to the wall clock
    # that compute_for_observation reads internally.
    obs = _FakeObs(now_ms(), "road_passability")
    # Just-observed -> F very close to 1.0 (within a few ms of now)
    f = calc.compute_for_observation(obs)
    assert f > 0.99


def test_update_tau_rejects_nonpositive() -> None:
    """update_tau rejects zero or negative tau."""
    calc = FreshnessCalculator()
    with pytest.raises(ValueError):
        calc.update_tau("road_passability", 0)
    with pytest.raises(ValueError):
        calc.update_tau("road_passability", -1)


def test_future_observation_clamped() -> None:
    """observed_at in the future (clock skew) -> F clamped to 1.0."""
    calc = FreshnessCalculator()
    f = calc.compute_freshness(
        observed_at=BASE_TIME_MS + 5000,  # 5s in the future
        current_time=BASE_TIME_MS,
        phenomenon="road_passability",
    )
    assert f == 1.0


def test_instance_override_isolated() -> None:
    """Instance overrides don't mutate module-level dict or other instances."""
    calc1 = FreshnessCalculator()
    calc2 = FreshnessCalculator()
    calc1.update_tau("road_passability", 10)
    assert calc1.get_tau("road_passability") == 10
    assert calc2.get_tau("road_passability") == 600
    # Module-level dict unchanged
    assert TAU_BY_PHENOMENON["road_passability"] == 600


def test_all_phenomenon_taus_present() -> None:
    """All required phenomenon types have explicit tau values."""
    required = {
        "responder_position": 60,
        "road_passability": 600,
        "shelter_capacity": 1800,
        "building_footprint": 86400,
        "demographic_vulnerability": 2592000,
        "water_level": 300,
        "flood_depth": 600,
        "rainfall": 300,
        "wind_speed": 300,
    }
    for phenomenon, expected_tau in required.items():
        assert TAU_BY_PHENOMENON[phenomenon] == expected_tau, (
            f"{phenomenon} tau mismatch"
        )
