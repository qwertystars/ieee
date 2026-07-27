"""Dataclasses for the route reliability engine (T28).

Route reliability combines road passability (T20), flood probability (T18),
and scenario ensemble variance (T23) into a safety-aware route cost.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RouteSegment:
    """A single road segment in a route.

    ``flood_prob`` and ``damage_prob`` are per-segment hazard probabilities
    in [0, 1]. When None, the route-level defaults from compute_passability
    are used. ``hazard_intensity`` in [0, 1] quantifies responder exposure.
    """

    id: str
    length_m: float
    base_speed_mps: float
    flood_prob: float | None = None
    damage_prob: float | None = None
    hazard_intensity: float = 0.0


@dataclass(frozen=True, slots=True)
class RouteScenario:
    """A single scenario for travel-time variance + passability (T23).

    ``failed_segments`` are segment IDs that become impassable in this
    scenario. ``delay_multiplier`` scales the nominal travel time.
    ``flood_prob`` and ``damage_prob`` override the route-level defaults
    for scenario-weighted passability computation.
    """

    scenario_id: str
    probability: float
    flood_prob: float = 0.0
    damage_prob: float = 0.0
    failed_segments: frozenset[str] = frozenset()
    delay_multiplier: float = 1.0


@dataclass(frozen=True, slots=True)
class Route:
    """A route: ordered sequence of segments from source to target."""

    id: str
    segments: tuple[RouteSegment, ...]
    source_node: int = 0
    target_node: int = 0


@dataclass(frozen=True, slots=True)
class RouteCost:
    """Decomposed route cost: E[T] + eta*Var(T) + gamma*P(failure) + rho*Risk.

    ``total`` is the scalar cost used for route comparison. ``passability``
    is P(route remains passable until arrival).
    """

    expected_time: float
    variance: float
    failure_prob: float
    responder_risk: float
    passability: float
    total: float


__all__ = ["Route", "RouteCost", "RouteScenario", "RouteSegment"]
