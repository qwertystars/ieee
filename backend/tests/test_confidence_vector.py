"""Tests for confidence vector computation (T13).

Uses in-memory SQLite for the source_reliability table (via ensure_table)
and dataclass observation doubles for the observation data. The candidates
list is passed directly to compute_corroboration/compute_conflict, avoiding
the need for a PostGIS-backed observations table in tests.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.fusion.confidence import ConfidenceVector, ConfidenceVectorCalculator
from app.fusion.freshness import FreshnessCalculator
from app.fusion.reliability import SourceReliabilityTracker, ensure_table
from app.models.enums import SourceType

BASE_TIME_MS = 1_700_000_000_000


@dataclass
class _TestObs:
    """Minimal observation-like object satisfying _ObsLike Protocol."""

    observation_id: str
    source_id: str
    source_type: SourceType
    phenomenon: str
    observed_at: int
    geometry_uncertainty: float
    model_uncertainty: float | None
    quality_flags: dict
    geometry: str
    org_id: str
    event_type: str
    value: float | None


def _make_obs(
    obs_id: str = "obs_1",
    value: float | None = 1.0,
    phenomenon: str = "road_passability",
    source_type: SourceType = SourceType.sensor,
    source_id: str = "src_1",
    observed_at: int = BASE_TIME_MS,
    geometry: str = "POINT(-73.9 40.7)",
    geometry_uncertainty: float = 50.0,
    model_uncertainty: float | None = None,
) -> _TestObs:
    return _TestObs(
        observation_id=obs_id,
        source_id=source_id,
        source_type=source_type,
        phenomenon=phenomenon,
        observed_at=observed_at,
        geometry_uncertainty=geometry_uncertainty,
        model_uncertainty=model_uncertainty,
        quality_flags={},
        geometry=geometry,
        org_id="org_test",
        event_type="road_status",
        value=value,
    )


def test_six_dimensions() -> None:
    """Vector has S, C, F, G, M, K for 5 observations."""
    calc = ConfidenceVectorCalculator()
    for i in range(5):
        obs = _make_obs(obs_id=f"obs_{i}")
        v = calc.compute_vector(obs, current_time_ms=BASE_TIME_MS)
        assert isinstance(v.s, float)
        assert isinstance(v.c, float)
        assert isinstance(v.f, float)
        assert isinstance(v.g, float)
        assert v.m is None
        assert isinstance(v.k, float)
        assert 0.0 <= v.s <= 1.0
        assert 0.0 <= v.c <= 1.0
        assert 0.0 <= v.f <= 1.0
        assert 0.0 <= v.g <= 1.0
        assert 0.0 <= v.k <= 1.0


def test_corroboration_increases() -> None:
    """C increases when 2 observations support same claim."""
    calc = ConfidenceVectorCalculator()
    obs = _make_obs("obs_1", value=1.0)
    v0 = calc.compute_vector(obs, current_time_ms=BASE_TIME_MS, candidates=[])
    assert v0.c == 0.0
    corrob1 = _make_obs("obs_2", value=1.0)
    v1 = calc.compute_vector(
        obs, current_time_ms=BASE_TIME_MS, candidates=[corrob1]
    )
    assert v1.c > v0.c
    corrob2 = _make_obs("obs_3", value=1.0)
    v2 = calc.compute_vector(
        obs, current_time_ms=BASE_TIME_MS, candidates=[corrob1, corrob2]
    )
    assert v2.c > v1.c


def test_conflict_increases() -> None:
    """K increases when contradicting observation added."""
    calc = ConfidenceVectorCalculator()
    obs = _make_obs("obs_1", value=1.0)
    v0 = calc.compute_vector(obs, current_time_ms=BASE_TIME_MS, candidates=[])
    assert v0.k == 0.0
    contradicting = _make_obs("obs_2", value=0.0)
    v1 = calc.compute_vector(
        obs, current_time_ms=BASE_TIME_MS, candidates=[contradicting]
    )
    assert v1.k > v0.k


def test_geo_precision_by_source_type() -> None:
    """GPS/sensor=1.0, citizen_report=0.3."""
    calc = ConfidenceVectorCalculator()
    assert calc.compute_geo_precision(SourceType.sensor) == 1.0
    assert calc.compute_geo_precision(SourceType.citizen_report) == 0.3
    assert calc.compute_geo_precision(SourceType.satellite) == 0.9
    assert calc.compute_geo_precision(SourceType.other) == 0.1


def test_freshness_from_calculator() -> None:
    """F matches FreshnessCalculator output."""
    fc = FreshnessCalculator()
    calc = ConfidenceVectorCalculator(freshness_calc=fc)
    obs = _make_obs(observed_at=BASE_TIME_MS - 60_000)
    v = calc.compute_vector(obs, current_time_ms=BASE_TIME_MS)
    expected = fc.compute_freshness(
        observed_at=BASE_TIME_MS - 60_000,
        current_time=BASE_TIME_MS,
        phenomenon="road_passability",
    )
    assert abs(v.f - expected) < 1e-9


def test_source_reliability_from_beta() -> None:
    """S matches SourceReliabilityTracker output."""
    engine = create_engine("sqlite://")
    ensure_table(engine)
    with Session(engine) as session:
        tracker = SourceReliabilityTracker(session)
        tracker.update("src_1", True, "road_passability")
        tracker.update("src_1", True, "road_passability")
        expected, _, _ = tracker.get_reliability("src_1", "road_passability")
        obs = _make_obs(source_id="src_1")
        calc = ConfidenceVectorCalculator()
        # Pass candidates=[] so corroboration/conflict skip the DB query
        # (the observations table doesn't exist on in-memory SQLite).
        v = calc.compute_vector(
            obs,
            current_time_ms=BASE_TIME_MS,
            db_session=session,
            candidates=[],
        )
        assert abs(v.s - expected) < 1e-9


def test_model_uncertainty_none_for_direct() -> None:
    """M is None for direct observations (sensor, citizen_report)."""
    calc = ConfidenceVectorCalculator()
    obs = _make_obs(source_type=SourceType.sensor, model_uncertainty=None)
    v = calc.compute_vector(obs, current_time_ms=BASE_TIME_MS)
    assert v.m is None
    ml_obs = _make_obs(source_type=SourceType.model, model_uncertainty=0.15)
    v2 = calc.compute_vector(ml_obs, current_time_ms=BASE_TIME_MS)
    assert v2.m == 0.15


def test_display_confidence_weighted_sum() -> None:
    """Display = w1*S + w2*C + w3*F + w4*G + w5*M + w6*K."""
    calc = ConfidenceVectorCalculator()
    v = ConfidenceVector(s=0.8, c=0.5, f=0.9, g=1.0, m=0.2, k=0.1)
    expected = (
        0.25 * 0.8
        + 0.20 * 0.5
        + 0.20 * 0.9
        + 0.10 * 1.0
        + (-0.10) * 0.2
        + (-0.15) * 0.1
    )
    assert abs(calc.compute_display_confidence(v) - expected) < 1e-9
    v_none = ConfidenceVector(s=0.8, c=0.5, f=0.9, g=1.0, m=None, k=0.0)
    expected_none = 0.25 * 0.8 + 0.20 * 0.5 + 0.20 * 0.9 + 0.10 * 1.0
    assert abs(calc.compute_display_confidence(v_none) - expected_none) < 1e-9
