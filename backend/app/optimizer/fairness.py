"""Fairness constraints for the emergency response optimizer (T50).

Three constraint families ensure the optimizer does NOT maximize total
benefit in a way that systematically ignores vulnerable communities:

1. Coverage constraint: Coverage_z >= C_min for designated vulnerable zones.
2. Response delay disparity: max_z delay_z - min_z delay_z <= delta,
   subject to emergency severity (no zone waits significantly longer).
3. Low-connectivity protection: zones with low smartphone_ownership,
   network_coverage, or social_media_usage get a minimum service guarantee.

An equity report surfaces throughput tradeoffs when equity constraints
alter the mathematically highest-throughput plan, so the operator is
never silently trading away equity for throughput.
"""

from __future__ import annotations

from ortools.sat.python import cp_model

from app.optimizer.fairness_metrics import (
    SubgroupGap,
    compute_subgroup_gap,
    subgroup_gap_passes,
)
from app.optimizer.fairness_types import EquityReport, FairnessZone, Plan

# Upper bound for delay variables (seconds). 10^6 = ~11.5 days.
_DELAY_UB = 10**6


class FairnessEngine:
    """Fairness constraints for CP-SAT optimizer models.

    Each add_* method adds a constraint family to a cp_model.CpModel.
    check_fairness validates a solved plan against all constraints.
    compute_equity_report compares the unconstrained (highest-throughput)
    plan against the fair plan and surfaces the tradeoff.
    """

    def add_coverage_constraint(
        self,
        model: cp_model.CpModel,
        coverage_vars: dict[str, cp_model.IntVar],
        vulnerable_zones: tuple[str, ...],
        c_min: int,
    ) -> None:
        """Coverage_z >= C_min for designated vulnerable zones.

        Ensures vulnerable zones receive at least c_min responders, even
        if the optimizer would otherwise divert them to higher-benefit zones.
        """
        for zone_id in vulnerable_zones:
            if zone_id in coverage_vars:
                model.add(coverage_vars[zone_id] >= c_min)

    def add_disparity_constraint(
        self,
        model: cp_model.CpModel,
        response_delays: dict[str, cp_model.IntVar],
        delta: int,
    ) -> None:
        """max_z ResponseDelay_z - min_z ResponseDelay_z <= delta.

        Ensures no zone waits significantly longer than another for
        emergency response, subject to severity. The delta is in seconds.
        """
        if not response_delays:
            return
        delays = list(response_delays.values())
        max_delay = model.new_int_var(0, _DELAY_UB, "fairness_max_delay")
        min_delay = model.new_int_var(0, _DELAY_UB, "fairness_min_delay")
        model.add_max_equality(max_delay, delays)
        model.add_min_equality(min_delay, delays)
        model.add(max_delay - min_delay <= delta)

    def add_low_connectivity_protection(
        self,
        model: cp_model.CpModel,
        coverage_vars: dict[str, cp_model.IntVar],
        zones: tuple[FairnessZone, ...],
        min_service: int,
    ) -> None:
        """Minimum service guarantee for low-connectivity areas.

        Zones with low smartphone_ownership, network_coverage, or
        social_media_usage (below 0.5) receive at least min_service
        responders. Without this, the optimizer would systematically
        ignore communities that report less — the same bias T25 corrects
        in the telecom silence model.
        """
        for zone in zones:
            if zone.is_low_connectivity and zone.id in coverage_vars:
                model.add(coverage_vars[zone.id] >= min_service)

    def compute_equity_report(
        self,
        original_plan: Plan,
        fair_plan: Plan,
        zones: tuple[FairnessZone, ...],
    ) -> EquityReport:
        """Report showing throughput tradeoff when equity constraints alter the plan.

        Compares the mathematically highest-throughput plan (original)
        against the fairness-constrained plan (fair). If equity constraints
        reduced throughput, surfaces the tradeoff so the operator knows
        equity was prioritized over raw benefit.
        """
        original_tp = original_plan.throughput
        fair_tp = fair_plan.throughput

        if original_tp > 0:
            tradeoff_pct = round(
                ((original_tp - fair_tp) / original_tp) * 100.0, 1
            )
        else:
            tradeoff_pct = 0.0

        equity_applied = original_tp > fair_tp

        vulnerable_protected = tuple(
            z.id for z in zones
            if z.vulnerable and z.c_min > 0
            and fair_plan.coverage.get(z.id, 0) >= z.c_min
        )
        low_conn_protected = tuple(
            z.id for z in zones
            if z.is_low_connectivity
            and fair_plan.coverage.get(z.id, 0) > 0
        )

        delays = list(fair_plan.response_delays.values())
        disparity = max(delays) - min(delays) if delays else 0

        if equity_applied:
            # Pick a representative zone that received priority allocation
            priority_zone = (
                low_conn_protected[0] if low_conn_protected
                else vulnerable_protected[0] if vulnerable_protected
                else "vulnerable"
            )
            message = (
                f"Equity constraint applied: {priority_zone} (low-connectivity) "
                f"received priority allocation, reducing total throughput by "
                f"{tradeoff_pct}%"
            )
        else:
            message = (
                "No equity tradeoff - fair plan matches highest-throughput plan."
            )

        return EquityReport(
            equity_applied=equity_applied,
            throughput_tradeoff_pct=tradeoff_pct,
            vulnerable_zones_protected=vulnerable_protected,
            low_connectivity_zones_protected=low_conn_protected,
            disparity_seconds=disparity,
            message=message,
        )

    def check_fairness(
        self,
        plan: Plan,
        zones: tuple[FairnessZone, ...],
        c_min: int,
        delta: int,
    ) -> bool:
        """Verify plan meets all fairness constraints.

        Checks:
        1. Coverage_z >= c_min for vulnerable zones.
        2. max_z delay_z - min_z delay_z <= delta.
        3. Low-connectivity zones get at least 1 responder (minimum service).

        Returns True only if all three constraint families are satisfied.
        """
        # 1. Coverage minimum for vulnerable zones
        for zone in zones:
            if zone.vulnerable and plan.coverage.get(zone.id, 0) < c_min:
                return False

        # 2. Response delay disparity
        delays = list(plan.response_delays.values())
        if delays and max(delays) - min(delays) > delta:
            return False

        # 3. Low-connectivity protection (minimum service = 1)
        for zone in zones:
            if zone.is_low_connectivity and plan.coverage.get(zone.id, 0) < 1:
                return False

        return True


__all__ = [
    "FairnessEngine",
    "SubgroupGap",
    "compute_subgroup_gap",
    "subgroup_gap_passes",
]
