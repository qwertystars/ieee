"""Telecom silence residual model — dataclasses for zones, contexts, time windows.

Models the expected report rate per zone per time window and computes the
residual between expected and observed rates. Large residuals, combined with
supporting evidence (tower failure, power outage, etc.), indicate meaningful
silence — potentially affected populations that cannot communicate.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Zone:
    """A geographic zone with population and connectivity attributes.

    Attributes:
        zone_id: Unique zone identifier.
        population: Number of people in the zone.
        normal_activity_rate: Multiplier for normal reporting activity (1.0 = normal).
        smartphone_ownership: Fraction of population with smartphones (0-1).
        network_coverage: Cellular network coverage quality (0-1).
        social_media_usage: Social media adoption rate (0-1).
        vulnerability_score: Pre-existing vulnerability index (0-1).
        historical_reporting_rate: Baseline reports per person per hour
            (theoretical rate under full connectivity).
        hazard_intensity: Current hazard intensity at the zone (0-1).
    """

    zone_id: str
    population: int
    normal_activity_rate: float
    smartphone_ownership: float
    network_coverage: float
    social_media_usage: float
    vulnerability_score: float
    historical_reporting_rate: float
    hazard_intensity: float = 0.0


@dataclass(frozen=True, slots=True)
class SilenceContext:
    """Operational context for silence detection.

    Attributes:
        tower_failed: Whether a cell tower serving the zone has failed.
        power_outage: Whether there is a power outage in the zone.
        failed_calls: Number of failed call attempts in the time window.
        devices_unreachable: Number of previously active devices now unreachable.
        hazard_intensity: Current hazard intensity (0-1).
    """

    tower_failed: bool
    power_outage: bool
    failed_calls: int
    devices_unreachable: int
    hazard_intensity: float


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """A time window in UTC epoch milliseconds.

    Attributes:
        start_ms: Start time in UTC epoch milliseconds (inclusive).
        end_ms: End time in UTC epoch milliseconds (exclusive).
    """

    start_ms: int
    end_ms: int

    @property
    def hours(self) -> float:
        """Window duration in hours."""
        return (self.end_ms - self.start_ms) / 3_600_000.0


__all__ = ["SilenceContext", "TimeWindow", "Zone"]
