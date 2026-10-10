"""Tests for fairness constraints (T50).

Test cases:
  1. test_coverage_minimum - Ward 7 gets 0 without fairness, >= C_min with fairness
  2. test_disparity_constraint - max_z delay - min_z delay <= delta
  3. test_equity_report_tradeoff - equity report shows throughput tradeoff
  4. test_low_connectivity_protection - low-connectivity zones get min service
  5. test_check_fairness - check_fairness validates plan meets all constraints

Verification command:
    docker compose run --rm -e PYTHONPATH=/app backend sh -c \
        "pip install pytest -q && python -m pytest tests/test_fairness.py -q"
"""

from __future__ import annotations

from ortools.sat.python import cp_model

from app.optimizer.fairness import FairnessEngine
from app.optimizer.fairness_types import FairnessZone, Plan

# ─── Helpers ────────────────────────────────────────────────────────────────


def _zones() -> tuple[FairnessZone, ...]:
    """3 zones: ward1 (high-benefit), ward7 (low-connectivity, vulnerable),
    ward9 (high-benefit)."""
    return (
        FairnessZone(id="ward1", vulnerable=False,
                     smartphone_ownership=0.9, network_coverage=0.9),
        FairnessZone(id="ward7", vulnerable=True, c_min=1,
                     smartphone_ownership=0.2, network_coverage=0.3,
                     social_media_usage=0.1),
        FairnessZone(id="ward9", vulnerable=False,
                     smartphone_ownership=0.9, network_coverage=0.9),
    )


def _benefits() -> dict[str, int]:
    """Ward 7 has low benefit (10) — without fairness, optimizer ignores it."""
    return {"ward1": 100, "ward7": 10, "ward9": 100}


def _solve(
    zones: tuple[FairnessZone, ...],
    benefits: dict[str, int],
    n_responders: int,
    *,
    coverage_c_min: int = 0,
    low_conn_min_service: int = 0,
) -> Plan:
    """Build and solve a coverage-maximization model.

    Without fairness constraints, the optimizer sends all responders to
    the highest-benefit zones. With coverage_c_min or low_conn_min_service,
    fairness constraints force allocation to vulnerable/low-connectivity zones.
    """
    model = cp_model.CpModel()
    coverage = {
        z.id: model.new_int_var(0, n_responders, f"cov_{z.id}") for z in zones
    }
    x: dict[tuple[int, str], cp_model.IntVar] = {}
    for r in range(n_responders):
        for z in zones:
            x[r, z.id] = model.new_bool_var(f"x_{r}_{z.id}")

    for z in zones:
        model.add(coverage[z.id] == sum(x[r, z.id] for r in range(n_responders)))
    for r in range(n_responders):
        model.add(sum(x[r, z.id] for z in zones) <= 1)

    model.maximize(
        sum(benefits[z.id] * x[r, z.id]
            for r in range(n_responders) for z in zones)
    )

    engine = FairnessEngine()
    if coverage_c_min > 0:
        vulnerable = tuple(z.id for z in zones if z.vulnerable)
        engine.add_coverage_constraint(model, coverage, vulnerable, coverage_c_min)
    if low_conn_min_service > 0:
        engine.add_low_connectivity_protection(
            model, coverage, zones, low_conn_min_service
        )

    solver = cp_model.CpSolver()
    status = solver.solve(model)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE), (
        f"solve failed: status={status}"
    )

    return Plan(
        coverage={z.id: int(solver.value(coverage[z.id])) for z in zones},
        throughput=round(solver.objective_value),
    )


# ─── Tests ──────────────────────────────────────────────────────────────────


def test_coverage_minimum() -> None:
    """Without fairness: Ward 7 gets 0; with fairness: Ward 7 gets >= C_min."""
    zones, benefits = _zones(), _benefits()

    # Without fairness: optimizer maximizes benefit, ignores low-benefit Ward 7
    plan_no_fairness = _solve(zones, benefits, n_responders=2)
    assert plan_no_fairness.coverage.get("ward7", 0) == 0, (
        f"without fairness, ward7 should get 0, got "
        f"{plan_no_fairness.coverage.get('ward7', 0)}"
    )

    # With fairness: Ward 7 gets >= C_min=1
    plan_fair = _solve(zones, benefits, n_responders=2, coverage_c_min=1)
    assert plan_fair.coverage.get("ward7", 0) >= 1, (
        f"with fairness, ward7 should get >= 1, got "
        f"{plan_fair.coverage.get('ward7', 0)}"
    )


def test_disparity_constraint() -> None:
    """max_z ResponseDelay_z - min_z ResponseDelay_z <= delta."""
    engine = FairnessEngine()

    # Forced delays [10, 90, 50] → disparity = 80 > delta=30 → INFEASIBLE
    model = cp_model.CpModel()
    delays = {
        "ward1": model.new_int_var(0, 100, "d_ward1"),
        "ward7": model.new_int_var(0, 100, "d_ward7"),
        "ward9": model.new_int_var(0, 100, "d_ward9"),
    }
    model.add(delays["ward1"] == 10)
    model.add(delays["ward7"] == 90)
    model.add(delays["ward9"] == 50)
    engine.add_disparity_constraint(model, delays, delta=30)
    solver = cp_model.CpSolver()
    status = solver.solve(model)
    assert status == cp_model.INFEASIBLE, (
        f"expected infeasible (disparity 80 > delta 30), got {status}"
    )

    # With delta=100: disparity 80 <= 100 → FEASIBLE
    model2 = cp_model.CpModel()
    delays2 = {
        "ward1": model2.new_int_var(0, 100, "d_ward1"),
        "ward7": model2.new_int_var(0, 100, "d_ward7"),
        "ward9": model2.new_int_var(0, 100, "d_ward9"),
    }
    model2.add(delays2["ward1"] == 10)
    model2.add(delays2["ward7"] == 90)
    model2.add(delays2["ward9"] == 50)
    engine.add_disparity_constraint(model2, delays2, delta=100)
    status2 = solver.solve(model2)
    assert status2 in (cp_model.OPTIMAL, cp_model.FEASIBLE), (
        f"expected feasible with delta=100, got {status2}"
    )


def test_equity_report_tradeoff() -> None:
    """Equity report shows throughput tradeoff when fairness alters the plan."""
    zones, benefits = _zones(), _benefits()

    original = _solve(zones, benefits, n_responders=2)
    fair = _solve(zones, benefits, n_responders=2, coverage_c_min=1)

    # Original plan: Ward 7 gets 0, throughput = 200
    assert original.coverage.get("ward7", 0) == 0
    assert original.throughput == 200

    # Fair plan: Ward 7 gets >= 1, throughput = 110 (tradeoff)
    assert fair.coverage.get("ward7", 0) >= 1
    assert fair.throughput < original.throughput

    engine = FairnessEngine()
    report = engine.compute_equity_report(original, fair, zones)

    assert report.equity_applied is True
    assert report.throughput_tradeoff_pct > 0.0, (
        f"expected tradeoff > 0, got {report.throughput_tradeoff_pct}"
    )
    assert "ward7" in report.low_connectivity_zones_protected
    assert "equity" in report.message.lower()
    assert "throughput" in report.message.lower()


def test_low_connectivity_protection() -> None:
    """Low-connectivity zones get minimum service guarantee."""
    # Ward 7 is low-connectivity but NOT vulnerable — tests protection in isolation
    zones = (
        FairnessZone(id="ward1", vulnerable=False,
                     smartphone_ownership=0.9, network_coverage=0.9),
        FairnessZone(id="ward7", vulnerable=False,
                     smartphone_ownership=0.2, network_coverage=0.3,
                     social_media_usage=0.1),
    )
    benefits = {"ward1": 100, "ward7": 10}

    # Without protection: 1 responder goes to ward1, ward7 gets 0
    plan_no = _solve(zones, benefits, n_responders=1)
    assert plan_no.coverage.get("ward7", 0) == 0, (
        f"without protection, ward7 should get 0, got "
        f"{plan_no.coverage.get('ward7', 0)}"
    )

    # With low-connectivity protection (min_service=1): ward7 gets >= 1
    plan_protected = _solve(zones, benefits, n_responders=1, low_conn_min_service=1)
    assert plan_protected.coverage.get("ward7", 0) >= 1, (
        f"with protection, ward7 should get >= 1, got "
        f"{plan_protected.coverage.get('ward7', 0)}"
    )


def test_check_fairness() -> None:
    """check_fairness validates plan meets all fairness constraints."""
    zones = _zones()
    engine = FairnessEngine()

    # Plan that violates coverage: Ward 7 (vulnerable) gets 0
    bad_coverage = Plan(coverage={"ward1": 1, "ward7": 0, "ward9": 1})
    assert engine.check_fairness(bad_coverage, zones, c_min=1, delta=100) is False

    # Plan that violates low-connectivity: Ward 7 gets 0
    bad_low_conn = Plan(coverage={"ward1": 2, "ward7": 0, "ward9": 0})
    assert engine.check_fairness(bad_low_conn, zones, c_min=0, delta=100) is False

    # Plan that violates disparity: delays [0, 100, 0], delta=30
    bad_disparity = Plan(
        coverage={"ward1": 1, "ward7": 1, "ward9": 1},
        response_delays={"ward1": 0, "ward7": 100, "ward9": 0},
    )
    assert engine.check_fairness(bad_disparity, zones, c_min=1, delta=30) is False

    # Plan that meets all constraints
    good_plan = Plan(
        coverage={"ward1": 1, "ward7": 1, "ward9": 1},
        response_delays={"ward1": 40, "ward7": 50, "ward9": 60},
    )
    assert engine.check_fairness(good_plan, zones, c_min=1, delta=30) is True
