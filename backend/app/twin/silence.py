"""Telecom silence residual model — expected vs observed report rate.

Estimates the expected report rate per zone per time window based on
population, normal activity, hazard intensity, historical reporting, and
network availability. Computes the residual between expected and observed
rates. Large residuals, combined with supporting evidence (tower failure,
power outage, failed calls, unreachable devices, high vulnerability),
indicate meaningful silence — populations that may be affected but cannot
communicate.

Bias correction adjusts the expected rate for zones with historically low
smartphone ownership, weak network coverage, or limited social-media use.
Without this correction, the model would systematically over-flag
low-connectivity communities as "silent" when they are simply less connected.

This is NOT a "no reports = high danger" model. The residual must exceed a
threshold AND be corroborated by infrastructure evidence to be meaningful.
"""

from __future__ import annotations

from app.twin.silence_types import SilenceContext, TimeWindow, Zone

# Hazard increases reporting by up to 50% (people report emergencies).
_HAZARD_REPORT_BOOST: float = 0.5

# Residual (reports/hour) must exceed this to be considered meaningful.
_MEANINGFUL_SILENCE_THRESHOLD: float = 1.0

# Vulnerability must exceed this for silence to be meaningful.
_VULNERABILITY_THRESHOLD: float = 0.4


class TelecomSilenceModel:
    """Estimate expected report rate and detect meaningful silence.

    The model computes:
    1. Expected rate r_hat from population, historical reporting, activity,
       hazard intensity, and network availability (bias-corrected).
    2. Observed rate r_observed from actual reports in the time window.
    3. Residual = r_hat - r_observed.
    4. Meaningful silence: residual > threshold AND supporting evidence
       (tower failure, power outage, failed calls, unreachable devices)
       AND high vulnerability.
    """

    def estimate_expected_rate(
        self, zone: Zone, time_window: TimeWindow
    ) -> float:
        """Estimate expected report rate (reports/hour) for a zone.

        r_hat = population * historical_reporting_rate * normal_activity
                * hazard_factor * bias_correction

        The bias_correction factor reduces the expected rate for zones
        with low smartphone ownership, weak network coverage, or limited
        social-media use — preventing false positives for less-connected
        communities.
        """
        base = (
            zone.population
            * zone.historical_reporting_rate
            * zone.normal_activity_rate
        )
        hazard_factor = 1.0 + zone.hazard_intensity * _HAZARD_REPORT_BOOST
        network_factor = self.bias_correction(zone)
        return base * hazard_factor * network_factor

    def compute_observed_rate(
        self,
        zone: Zone,
        time_window: TimeWindow,
        observations: list[int],
    ) -> float:
        """Compute observed report rate (reports/hour) from observation timestamps.

        Counts observations whose timestamps fall within [start_ms, end_ms)
        and divides by the window duration in hours.
        """
        count = sum(
            1
            for ts in observations
            if time_window.start_ms <= ts < time_window.end_ms
        )
        return count / time_window.hours

    def compute_residual(
        self, r_hat: float, r_observed: float
    ) -> float:
        """Compute residual = expected - observed (reports/hour).

        Positive residual indicates silence (fewer reports than expected).
        Negative residual indicates more reports than expected.
        """
        return r_hat - r_observed

    def is_meaningful_silence(
        self,
        zone: Zone,
        residual: float,
        context: SilenceContext,
    ) -> bool:
        """Determine if a silence residual is meaningful.

        A residual is meaningful when ALL of the following hold:
        1. residual > threshold (expected significantly exceeds observed)
        2. Supporting evidence exists: tower failure, power outage, failed
           calls, or previously active devices becoming unreachable.
        3. Zone has high vulnerability (vulnerability_score > threshold).

        This prevents the model from flagging "no reports = high danger"
        in low-connectivity areas where silence is the baseline state.
        """
        if residual <= _MEANINGFUL_SILENCE_THRESHOLD:
            return False
        supporting_evidence = (
            context.tower_failed
            or context.power_outage
            or context.failed_calls > 0
            or context.devices_unreachable > 0
        )
        if not supporting_evidence:
            return False
        return zone.vulnerability_score > _VULNERABILITY_THRESHOLD

    def bias_correction(self, zone: Zone) -> float:
        """Compute bias correction multiplier for low-connectivity zones.

        Returns the arithmetic mean of smartphone ownership, network
        coverage, and social media usage. Zones with low connectivity
        get a reduced expected rate, preventing false positives where
        less-connected communities are systematically misflagged as silent.

        Without this correction, poorer communities with historically low
        smartphone ownership, weak network coverage, or limited social-media
        use would be over-flagged as "in danger" simply because they report
        less — a systematic misrepresentation.
        """
        return (
            zone.smartphone_ownership
            + zone.network_coverage
            + zone.social_media_usage
        ) / 3.0


__all__ = ["TelecomSilenceModel"]
