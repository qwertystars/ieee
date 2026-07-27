"""Dataclasses for the rolling-horizon risk-aware CVaR optimizer (T26).

All cost-bearing fields are floats in human units; the engine scales them
to integers (x1000) before feeding CP-SAT, which is integer-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Zone:
    """A geographic zone requiring coverage. ``vulnerable`` flags fairness."""

    id: str
    demand: int  # number of responders needed for full coverage
    vulnerable: bool = False  # if True, fairness floor C_min applies
    c_min: int = 0  # minimum coverage for vulnerable zones


@dataclass(frozen=True, slots=True)
class Responder:
    """A responder with skills and a vehicle class.

    ``skills`` is a set of task IDs this responder can perform.
    ``vehicle_class`` determines road compatibility (e.g. ``"boat"``).
    ``shift_end`` is the absolute deadline (epoch ms) for this responder.
    """

    id: str
    skills: frozenset[str]
    vehicle_class: str
    shift_start: int = 0
    shift_end: int = 86_400_000  # 24h default
    cost_per_task: float = 1.0  # operational cost per assigned task


@dataclass(frozen=True, slots=True)
class Task:
    """A task to be assigned. ``required_skill`` must match a responder skill.

    ``zone_id`` links the task to a zone for coverage/fairness accounting.
    ``duration`` is the task duration in seconds.
    ``precedes`` lists task IDs that must start after this task ends.
    """

    id: str
    zone_id: str
    required_skill: str
    duration: int = 3600  # seconds
    precedes: tuple[str, ...] = ()
    harm_if_unserved: float = 100.0  # loss contribution if no responder assigned


@dataclass(frozen=True, slots=True)
class RoadArc:
    """A directed road arc between two nodes.

    ``vehicle_classes`` is the set of vehicle classes that can traverse it.
    Arcs incompatible with a responder's vehicle are skipped (conditional arc).
    """

    from_node: int
    to_node: int
    vehicle_classes: frozenset[str]
    travel_time: int = 0  # seconds


@dataclass(frozen=True, slots=True)
class Shelter:
    """A shelter or hospital with capacity tracked via reservoir constraint.

    ``capacity`` is the maximum occupancy. ``initial_occupancy`` is the
    starting level. Tasks that add occupants are +1, departures are -1.
    """

    id: str
    capacity: int
    initial_occupancy: int = 0


@dataclass(frozen=True, slots=True)
class ScenarioLoss:
    """Per-scenario loss weight. ``probability`` sums to 1.0 across scenarios.

    ``harm_multiplier`` scales the harm of unserved tasks in this scenario,
    capturing scenario severity (e.g. worse flood → more harm per unmet task).
    """

    probability: float
    harm_multiplier: float = 1.0


@dataclass(frozen=True, slots=True)
class OptimizerInput:
    """Full input bundle for the EmergencyResponseOptimizer."""

    zones: tuple[Zone, ...]
    responders: tuple[Responder, ...]
    tasks: tuple[Task, ...]
    scenarios: tuple[ScenarioLoss, ...]
    road_arcs: tuple[RoadArc, ...] = ()
    shelters: tuple[Shelter, ...] = ()
    alpha: float = 0.95  # CVaR confidence level
    lambda_risk: float = 1.0  # risk aversion weight
    max_solve_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class Assignment:
    """A single responder→task assignment in the solution."""

    responder_id: str
    task_id: str
    start_time: int


@dataclass(frozen=True, slots=True)
class OptimizerResult:
    """Solution portfolio returned by the optimizer.

    ``status`` is one of ``"optimal"``, ``"feasible"``, ``"infeasible"``,
    ``"unknown"``. ``objective_value`` is the scaled integer objective.
    """

    status: str
    assignments: tuple[Assignment, ...]
    objective_value: float
    expected_harm: float
    cvar: float
    operational_cost: float
    solve_time_seconds: float
    coverage: dict[str, int] = field(default_factory=dict)


__all__ = [
    "Assignment",
    "OptimizerInput",
    "OptimizerResult",
    "Responder",
    "RoadArc",
    "ScenarioLoss",
    "Shelter",
    "Task",
    "Zone",
]
