"""Route reliability engine — P(route passable until arrival) + safety-aware cost (T28).

Cost(r) = E[T_r] + eta*Var(T_r) + gamma*P(route failure) + rho*Risk_responders

  - E[T_r]           expected travel time from segment lengths + speeds
  - Var(T_r)         travel-time variance from scenario ensemble (T23)
  - P(route failure) = 1 - P(passable), from road damage (T20) + flood (T18)
  - Risk_responders  hazard exposure along the route

The engine NEVER selects the fastest expected route as the sole criterion —
safety (passability + responder risk) always participates in the cost.
"""

from __future__ import annotations

import heapq
import itertools

from app.optimizer.routing_types import Route, RouteCost, RouteScenario, RouteSegment
from app.perception.damage import DamageAssessor

_INFINITE_TIME = 1e9


class RouteReliabilityEngine:
    """Safety-aware route reliability engine.

    ``vehicle_class`` determines per-segment passability via T20 factors.
    Defaults to ``ambulance`` (flood_factor=0.90, damage_factor=0.50).
    """

    def __init__(
        self,
        vehicle_class: str = "ambulance",
        scenarios: tuple[RouteScenario, ...] = (),
        flood_prob: float = 0.0,
        damage_prob: float = 0.0,
        hazard_intensity: float = 0.0,
    ) -> None:
        self._vehicle_class = vehicle_class
        self._assessor = DamageAssessor()
        self._scenarios = scenarios
        self._flood_prob = flood_prob
        self._damage_prob = damage_prob
        self._hazard_intensity = hazard_intensity

    # ── Passability ────────────────────────────────────────────────

    def compute_passability(
        self,
        route_segments: tuple[RouteSegment, ...] | list[RouteSegment],
        flood_prob: float = 0.0,
        damage_prob: float = 0.0,
    ) -> float:
        """P(route passable) = product of per-segment passabilities (T20)."""
        if not route_segments:
            return 1.0
        p = 1.0
        for seg in route_segments:
            sf = seg.flood_prob if seg.flood_prob is not None else flood_prob
            sd = seg.damage_prob if seg.damage_prob is not None else damage_prob
            road = {"properties": {"flood_prob": float(sf), "damage_prob": float(sd)}}
            p *= self._assessor.compute_vehicle_class_passability(road, self._vehicle_class)
        return max(0.0, min(1.0, p))

    def compute_scenario_passability(
        self,
        route: Route,
        scenarios: tuple[RouteScenario, ...] | list[RouteScenario],
    ) -> float:
        """P(passable) = sum_s p_s * P(passable | s) from scenario ensemble (T23)."""
        if not scenarios:
            return self.compute_passability(route.segments, self._flood_prob, self._damage_prob)
        total_p = sum(s.probability for s in scenarios)
        if total_p <= 0.0:
            return 0.0
        seg_ids = {seg.id for seg in route.segments}
        p = sum(
            s.probability * self.compute_passability(route.segments, s.flood_prob, s.damage_prob)
            for s in scenarios
            if not (s.failed_segments & seg_ids)
        )
        return p / total_p

    # ── Travel time ────────────────────────────────────────────────

    def compute_travel_time(
        self,
        route_segments: tuple[RouteSegment, ...] | list[RouteSegment],
    ) -> float:
        """E[T_r] = sum length_i / speed_i (seconds)."""
        if not route_segments:
            return 0.0
        return sum(seg.length_m / seg.base_speed_mps for seg in route_segments)

    def compute_travel_time_variance(
        self,
        route: Route,
        scenarios: tuple[RouteScenario, ...] | list[RouteScenario],
    ) -> float:
        """Var(T_r) = sum p_s * (T_s - E[T])^2 from scenario ensemble (T23)."""
        if not scenarios:
            return 0.0
        nominal = self.compute_travel_time(route.segments)
        seg_ids = {seg.id for seg in route.segments}
        times = [
            _INFINITE_TIME if (sc.failed_segments & seg_ids) else nominal * sc.delay_multiplier
            for sc in scenarios
        ]
        probs = [sc.probability for sc in scenarios]
        total_p = sum(probs)
        if total_p <= 0.0:
            return 0.0
        e_t = sum(p * t for p, t in zip(probs, times)) / total_p
        return sum(p * (t - e_t) ** 2 for p, t in zip(probs, times)) / total_p

    # ── Responder risk ─────────────────────────────────────────────

    def compute_responder_risk(self, route: Route, hazard_intensity: float = 0.0) -> float:
        """Risk_responders = sum hazard_intensity_i * exposure_time_i."""
        if not route.segments:
            return 0.0
        return sum(
            (seg.hazard_intensity if seg.hazard_intensity > 0 else hazard_intensity)
            * (seg.length_m / seg.base_speed_mps)
            for seg in route.segments
        )

    # ── Cost ────────────────────────────────────────────────────────

    def compute_cost(
        self, route: Route, eta: float = 0.5, gamma: float = 2.0, rho: float = 1.0
    ) -> RouteCost:
        """Cost(r) = E[T] + eta*Var(T) + gamma*P(failure) + rho*Risk_responders."""
        e_t = self.compute_travel_time(route.segments)
        var = self.compute_travel_time_variance(route, self._scenarios)
        if self._scenarios:
            passability = self.compute_scenario_passability(route, self._scenarios)
        else:
            passability = self.compute_passability(
                route.segments, self._flood_prob, self._damage_prob
            )
        failure_prob = 1.0 - passability
        risk = self.compute_responder_risk(route, self._hazard_intensity)
        total = e_t + eta * var + gamma * failure_prob + rho * risk
        return RouteCost(e_t, var, failure_prob, risk, passability, total)

    # ── k-shortest paths (Yen's algorithm) ──────────────────────────

    def k_shortest_paths(
        self,
        graph: dict[int, list[tuple[int, float]]],
        source: int,
        target: int,
        k: int = 3,
    ) -> list[list[int]]:
        """Return up to k shortest paths from source to target (Yen's algorithm).

        ``graph`` is an adjacency dict: node -> list of (neighbor, weight).
        Returns a list of paths, each a list of node IDs.
        """
        if source not in graph or k < 1:
            return []
        first = self._dijkstra(graph, source, target)
        if first is None:
            return []
        paths: list[list[int]] = [first]
        candidates: list[tuple[float, list[int]]] = []
        seen: set[tuple[int, ...]] = {tuple(first)}
        for _ in range(1, k):
            prev_path = paths[-1]
            for i in range(len(prev_path) - 1):
                root_path = prev_path[: i + 1]
                removed = {
                    (p[i], p[i + 1])
                    for p in paths
                    if len(p) > i and p[: i + 1] == root_path
                }
                sub = self._remove_edges(graph, removed)
                spur = self._dijkstra(sub, prev_path[i], target)
                if spur is None:
                    continue
                total_path = root_path[:-1] + spur
                key = tuple(total_path)
                if key not in seen:
                    heapq.heappush(
                        candidates, (self._path_weight(graph, total_path), total_path)
                    )
                    seen.add(key)
            if not candidates:
                break
            paths.append(heapq.heappop(candidates)[1])
        return paths

    @staticmethod
    def _remove_edges(
        graph: dict[int, list[tuple[int, float]]], edges: set[tuple[int, int]]
    ) -> dict[int, list[tuple[int, float]]]:
        return {
            n: [(m, w) for m, w in nbrs if (n, m) not in edges]
            for n, nbrs in graph.items()
        }

    @staticmethod
    def _dijkstra(
        graph: dict[int, list[tuple[int, float]]], source: int, target: int
    ) -> list[int] | None:
        dist: dict[int, float] = {source: 0.0}
        prev: dict[int, int] = {}
        pq: list[tuple[float, int]] = [(0.0, source)]
        visited: set[int] = set()
        while pq:
            d, u = heapq.heappop(pq)
            if u in visited:
                continue
            visited.add(u)
            if u == target:
                break
            for v, w in graph.get(u, []):
                if v not in visited and d + w < dist.get(v, float("inf")):
                    dist[v] = d + w
                    prev[v] = u
                    heapq.heappush(pq, (d + w, v))
        if target not in dist:
            return None
        path = [target]
        while path[-1] != source:
            path.append(prev[path[-1]])
        return path[::-1]

    @staticmethod
    def _path_weight(
        graph: dict[int, list[tuple[int, float]]], path: list[int]
    ) -> float:
        return sum(
            next(w for n, w in graph[u] if n == v)
            for u, v in itertools.pairwise(path)
        )

    # ── Route selection ────────────────────────────────────────────

    def select_route(
        self,
        routes: tuple[Route, ...] | list[Route],
        weights: dict[str, float] | None = None,
    ) -> Route:
        """Select the route with minimum cost.

        ``weights`` overrides the default cost weights (eta, gamma, rho).
        """
        if not routes:
            raise ValueError("select_route requires at least one route")
        w = weights or {}
        eta, gamma, rho = w.get("eta", 0.5), w.get("gamma", 2.0), w.get("rho", 1.0)
        return min(
            routes,
            key=lambda r: self.compute_cost(r, eta=eta, gamma=gamma, rho=rho).total,
        )


__all__ = ["RouteReliabilityEngine"]
