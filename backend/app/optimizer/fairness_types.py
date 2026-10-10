"""Dataclasses for fairness constraints (T50).

FairnessZone extends the optimizer's Zone concept with connectivity
indicators (smartphone_ownership, network_coverage, social_media_usage)
used by the low-connectivity protection constraint. Plan and EquityReport
capture the inputs and outputs of fairness evaluation.

The connectivity indicators mirror T25's TelecomSilenceModel bias
correction: zones with low smartphone ownership, weak network coverage,
or limited social-media use are systematically under-reported and must
not be ignored by the optimizer.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class FairnessZone:
    """Zone with connectivity attributes for fairness constraints.

    Attributes:
        id: Unique zone identifier.
        vulnerable: If True, coverage floor C_min applies.
        c_min: Minimum coverage for vulnerable zones.
        smartphone_ownership: Fraction of population with smartphones (0-1).
        network_coverage: Cellular network coverage quality (0-1).
        social_media_usage: Social media adoption rate (0-1).
    """

    id: str
    vulnerable: bool = False
    c_min: int = 0
    smartphone_ownership: float = 1.0
    network_coverage: float = 1.0
    social_media_usage: float = 1.0

    @property
    def is_low_connectivity(self) -> bool:
        """True if any connectivity indicator is below 0.5.

        Zones below this threshold are systematically under-reported
        (per T25's bias correction) and require minimum service guarantee.
        """
        return (
            self.smartphone_ownership < 0.5
            or self.network_coverage < 0.5
            or self.social_media_usage < 0.5
        )


@dataclass(frozen=True, slots=True)
class Plan:
    """A coverage plan for fairness evaluation.

    Attributes:
        coverage: zone_id -> responder coverage count.
        response_delays: zone_id -> response delay in seconds.
        throughput: Total benefit (sum of served task harm values).
    """

    coverage: dict[str, int] = field(default_factory=dict)
    response_delays: dict[str, int] = field(default_factory=dict)
    throughput: int = 0


@dataclass(frozen=True, slots=True)
class EquityReport:
    """Report on equity constraints' impact on the plan.

    Attributes:
        equity_applied: True if fairness constraints altered the plan.
        throughput_tradeoff_pct: % reduction in throughput (0.0 if none).
        vulnerable_zones_protected: Zone IDs that got C_min coverage.
        low_connectivity_zones_protected: Zone IDs with min service guarantee.
        disparity_seconds: max - min response delay across zones.
        message: Human-readable summary for the operator.
    """

    equity_applied: bool
    throughput_tradeoff_pct: float
    vulnerable_zones_protected: tuple[str, ...]
    low_connectivity_zones_protected: tuple[str, ...]
    disparity_seconds: int
    message: str


__all__ = ["EquityReport", "FairnessZone", "Plan"]
