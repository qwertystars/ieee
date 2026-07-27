"""Tests for the telecom silence residual model (T25).

Verifies:
1. High-population zone with tower failure flagged as meaningful silence.
2. Low-population zone NOT flagged (residual below threshold).
3. Bias correction reduces expected rate for low-connectivity zones.
4. Residual computation is correct (expected - observed).
5. Meaningful silence requires supporting evidence (not just low reports).
6. Meaningful silence requires high vulnerability.
7. Observed rate counts reports in window correctly.
"""

from __future__ import annotations

from app.twin.silence import TelecomSilenceModel
from app.twin.silence_types import SilenceContext, TimeWindow, Zone

# 1-hour time window starting at epoch.
WINDOW = TimeWindow(start_ms=0, end_ms=3_600_000)

# High-population, full-connectivity zone (stopping condition 1).
# Expected rate = 1000 * 0.005 * 1.0 * 1.0 * 1.0 = 5.0 reports/hour.
ZONE_HIGH_POP = Zone(
    zone_id="zone_high",
    population=1000,
    normal_activity_rate=1.0,
    smartphone_ownership=1.0,
    network_coverage=1.0,
    social_media_usage=1.0,
    vulnerability_score=0.8,
    historical_reporting_rate=0.005,
    hazard_intensity=0.0,
)

# Low-population, low-connectivity zone (stopping condition 2).
# Expected rate = 100 * 0.01 * 1.0 * 1.0 * 0.5 = 0.5 reports/hour.
# bias_correction = (0.5 + 0.5 + 0.5) / 3 = 0.5.
ZONE_LOW_POP = Zone(
    zone_id="zone_low",
    population=100,
    normal_activity_rate=1.0,
    smartphone_ownership=0.5,
    network_coverage=0.5,
    social_media_usage=0.5,
    vulnerability_score=0.3,
    historical_reporting_rate=0.01,
    hazard_intensity=0.0,
)

# Context with tower failure (supporting evidence).
CONTEXT_TOWER_FAILED = SilenceContext(
    tower_failed=True,
    power_outage=False,
    failed_calls=0,
    devices_unreachable=0,
    hazard_intensity=0.0,
)

# Context with no supporting evidence.
CONTEXT_NO_EVIDENCE = SilenceContext(
    tower_failed=False,
    power_outage=False,
    failed_calls=0,
    devices_unreachable=0,
    hazard_intensity=0.0,
)


def test_meaningful_silence() -> None:
    """High-pop zone, expected 5/hr, observed 0, tower failed -> meaningful.

    Stopping condition 1: zone with population 1000, expected 5 reports/hr,
    observed 0, tower failed -> residual = 5, flagged as meaningful.
    """
    model = TelecomSilenceModel()
    r_hat = model.estimate_expected_rate(ZONE_HIGH_POP, WINDOW)
    r_obs = model.compute_observed_rate(
        ZONE_HIGH_POP, WINDOW, observations=[]
    )
    residual = model.compute_residual(r_hat, r_obs)

    assert r_hat == 5.0
    assert r_obs == 0.0
    assert residual == 5.0
    assert model.is_meaningful_silence(
        ZONE_HIGH_POP, residual, CONTEXT_TOWER_FAILED
    )


def test_low_connectivity_not_flagged() -> None:
    """Low-pop zone, expected 0.5/hr, observed 0 -> NOT meaningful.

    Stopping condition 2: zone with population 100, expected 0.5 reports/hr,
    observed 0 -> residual = 0.5, NOT flagged (low-connectivity area).
    The bias correction reduces the expected rate, preventing false
    positives for less-connected communities.
    """
    model = TelecomSilenceModel()
    r_hat = model.estimate_expected_rate(ZONE_LOW_POP, WINDOW)
    r_obs = model.compute_observed_rate(
        ZONE_LOW_POP, WINDOW, observations=[]
    )
    residual = model.compute_residual(r_hat, r_obs)

    assert r_hat == 0.5
    assert r_obs == 0.0
    assert residual == 0.5
    assert not model.is_meaningful_silence(
        ZONE_LOW_POP, residual, CONTEXT_TOWER_FAILED
    )


def test_bias_correction_reduces_expected_rate() -> None:
    """Low-connectivity zone gets reduced expected rate via bias correction.

    A zone with smartphone_ownership=0.3, network_coverage=0.3,
    social_media_usage=0.3 gets bias_correction=0.3, reducing the expected
    rate to 30% of the full-connectivity baseline.
    """
    model = TelecomSilenceModel()

    full_connectivity = Zone(
        zone_id="full",
        population=1000,
        normal_activity_rate=1.0,
        smartphone_ownership=1.0,
        network_coverage=1.0,
        social_media_usage=1.0,
        vulnerability_score=0.5,
        historical_reporting_rate=0.005,
    )
    low_connectivity = Zone(
        zone_id="low",
        population=1000,
        normal_activity_rate=1.0,
        smartphone_ownership=0.3,
        network_coverage=0.3,
        social_media_usage=0.3,
        vulnerability_score=0.5,
        historical_reporting_rate=0.005,
    )

    assert model.bias_correction(full_connectivity) == 1.0
    assert model.bias_correction(low_connectivity) == 0.3
    assert model.estimate_expected_rate(
        low_connectivity, WINDOW
    ) < model.estimate_expected_rate(full_connectivity, WINDOW)


def test_residual_computation() -> None:
    """Residual = expected - observed."""
    model = TelecomSilenceModel()
    assert model.compute_residual(5.0, 2.0) == 3.0
    assert model.compute_residual(0.0, 0.0) == 0.0
    assert model.compute_residual(1.0, 3.0) == -2.0


def test_requires_supporting_evidence() -> None:
    """High residual without supporting evidence -> NOT meaningful.

    Silence must NOT be flagged as "no reports = high danger" — it must
    be corroborated by infrastructure evidence (tower failure, power
    outage, failed calls, or unreachable devices).
    """
    model = TelecomSilenceModel()
    r_hat = model.estimate_expected_rate(ZONE_HIGH_POP, WINDOW)
    residual = model.compute_residual(r_hat, 0.0)

    assert residual > 1.0  # residual exceeds threshold
    assert not model.is_meaningful_silence(
        ZONE_HIGH_POP, residual, CONTEXT_NO_EVIDENCE
    )


def test_requires_high_vulnerability() -> None:
    """High residual with supporting evidence but low vulnerability -> NOT meaningful.

    A wealthy, low-vulnerability zone with a tower failure is less
    concerning than a high-vulnerability zone with the same silence.
    """
    model = TelecomSilenceModel()

    low_vuln_zone = Zone(
        zone_id="low_vuln",
        population=1000,
        normal_activity_rate=1.0,
        smartphone_ownership=1.0,
        network_coverage=1.0,
        social_media_usage=1.0,
        vulnerability_score=0.2,  # below threshold
        historical_reporting_rate=0.005,
    )

    r_hat = model.estimate_expected_rate(low_vuln_zone, WINDOW)
    residual = model.compute_residual(r_hat, 0.0)

    assert residual > 1.0
    assert not model.is_meaningful_silence(
        low_vuln_zone, residual, CONTEXT_TOWER_FAILED
    )


def test_compute_observed_rate() -> None:
    """Observed rate = count of reports in window / window hours."""
    model = TelecomSilenceModel()

    # 3 observations in a 1-hour window -> 3.0 reports/hour.
    observations = [0, 1_000_000, 2_000_000]  # all within [0, 3_600_000)
    r_obs = model.compute_observed_rate(ZONE_HIGH_POP, WINDOW, observations)
    assert r_obs == 3.0

    # Observations at or after end_ms are not counted.
    outside = [3_600_000, 7_200_000]
    r_obs = model.compute_observed_rate(ZONE_HIGH_POP, WINDOW, outside)
    assert r_obs == 0.0
