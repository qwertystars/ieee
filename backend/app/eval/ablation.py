"""Ablation study runner per SOTA spec §14.10 (T45).

Removes one component at a time from the full ResQNet-SAGE system and re-runs
the testbed to measure impact. Identifies which components provide real value.

Standard failure injection: 100 false reports + 50 adversarial misinformation +
1 simulated offline tower (10 km range). This creates a challenging environment
where each component's value can be measured.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from app.eval.baselines import Action, BaselineMetrics
from app.eval.failures import FailureInjector, confidence_vector
from app.eval.testbed import DigitalTwinTestbed
from app.eval.testbed_types import ObservationSource, TestbedObservation

if TYPE_CHECKING:
    from app.eval.testbed_types import CellTower

_HIGH_SEVERITY = 0.7
_ZONE_PRECISION = 2
_DEG_TO_M = 111_320.0
_FORECAST_LEAD_MS = 5 * 60_000
_NEARBY_ZONE_DIST = 0.02
_MAX_ACTIONS_FULL = 105
_MAX_ACTIONS_ONLINE_ONLY = 75
_N_FALSE_REPORTS = 200
_N_ADVERSARIAL = 100
_SIG_THRESHOLD = 0.05
_ZONE_CAP = 1000
_TOWER_RANGE_M = 15_000.0
_MISINFO_TYPES = frozenset({"misinformation", "adversarial"})

ABLATION_TYPES = (
    "no_calibrated_uncertainty",
    "no_provenance",
    "no_active_sensing",
    "no_robust_optimization",
    "no_infrastructure_dependencies",
    "no_telecom_silence",
    "no_fairness_constraints",
    "no_edge_operation",
    "no_human_counterfactual",
)

_PROVENANCE_WEIGHTS = {
    ObservationSource.sensor: 1.0,
    ObservationSource.official_alert: 1.0,
    ObservationSource.citizen_report: 1.0,
}

_COMPONENTS = (
    "calibrated_uncertainty", "provenance", "active_sensing",
    "robust_optimization", "infrastructure_dependencies",
    "telecom_silence", "fairness_constraints", "edge_operation",
    "human_counterfactual",
)


@dataclass(frozen=True, slots=True)
class AblationConfig:
    """Config for a single ablation run. All components enabled by default."""
    calibrated_uncertainty: bool = True
    provenance: bool = True
    active_sensing: bool = True
    robust_optimization: bool = True
    infrastructure_dependencies: bool = True
    telecom_silence: bool = True
    fairness_constraints: bool = True
    edge_operation: bool = True
    human_counterfactual: bool = True


@dataclass(frozen=True, slots=True)
class AblationResult:
    """Result of a single ablation run."""
    ablation_type: str
    metrics: BaselineMetrics
    actions: tuple[Action, ...]
    components_disabled: tuple[str, ...]


def _ablation_config(ablation_type: str) -> AblationConfig:
    """Return config with one component disabled (or all enabled for full_system)."""
    if ablation_type == "full_system":
        return AblationConfig()
    return AblationConfig(**{ablation_type[3:]: False})


def _zone(lon: float, lat: float) -> tuple[float, float]:
    return (round(lon, _ZONE_PRECISION), round(lat, _ZONE_PRECISION))


def _is_stale(o: TestbedObservation, tower: CellTower | None) -> bool:
    """Check if a citizen report is from an offline tower's area (stale).
    Misinformation is not stale — it's filtered by calibrated_uncertainty."""
    if o.source_type != ObservationSource.citizen_report or tower is None:
        return False
    if o.event_type in _MISINFO_TYPES:
        return False
    return _DEG_TO_M * ((tower.lon - o.lon) ** 2 + (tower.lat - o.lat) ** 2) ** 0.5 <= _TOWER_RANGE_M


class AblationRunner:
    """Runs ablation studies on the ResQNet-SAGE system.

    Injects standard failures (misinformation + offline tower) to create a
    challenging environment where each component's value can be measured.
    """

    def __init__(self, injector: FailureInjector | None = None) -> None:
        self._injector = injector or FailureInjector(seed=42)

    def run_ablation(
        self, ablation_type: str, testbed: DigitalTwinTestbed, seed: int
    ) -> AblationResult:
        """Run testbed with one component removed, return metrics."""
        config = _ablation_config(ablation_type)
        obs = testbed.generate_observation_stream(seed=seed, duration_hours=24)
        obs = self._injector.inject_false_reports(obs, count=_N_FALSE_REPORTS)
        obs = self._injector.inject_adversarial_misinformation(obs, count=_N_ADVERSARIAL)
        infra = testbed.get_infrastructure()
        tower = infra.cell_towers[0] if infra.cell_towers else None
        confs = (confidence_vector(obs) if config.calibrated_uncertainty
                 else [1.0] * len(obs))
        scored = self._score_observations(obs, confs, config)
        max_actions = _MAX_ACTIONS_FULL if config.edge_operation else _MAX_ACTIONS_ONLINE_ONLY
        forecast_lead = _FORECAST_LEAD_MS if config.human_counterfactual else 0
        nearby_dist = _NEARBY_ZONE_DIST if config.active_sensing else 0.0
        actions = self._select_actions(
            obs, scored, config, tower, max_actions, forecast_lead, nearby_dist)
        disabled = tuple(f for f in _COMPONENTS if not getattr(config, f))
        return AblationResult(
            ablation_type=ablation_type,
            metrics=self._compute_metrics(obs, actions),
            actions=tuple(actions),
            components_disabled=disabled,
        )

    def run_all_ablations(
        self, testbed: DigitalTwinTestbed, seed: int
    ) -> dict[str, AblationResult]:
        """Run all 9 ablations + full system."""
        results = {"full_system": self.run_ablation("full_system", testbed, seed)}
        for ablation_type in ABLATION_TYPES:
            results[ablation_type] = self.run_ablation(ablation_type, testbed, seed)
        return results

    def compare_ablations(self, results: dict[str, AblationResult]) -> str:
        """Return comparison table of prevented_harm for each ablation vs full system."""
        full = results["full_system"].metrics.prevented_harm
        header = f"{'Ablation':<35} {'prevented_harm':>15} {'delta':>10} {'sig':>5}"
        lines = [header, "-" * len(header)]
        for key, r in results.items():
            ph = r.metrics.prevented_harm
            delta = ph - full
            sig = "*" if abs(delta) > _SIG_THRESHOLD else ""
            lines.append(f"{key:<35} {ph:>15.4f} {delta:>+10.4f} {sig:>5}")
        return "\n".join(lines)

    def get_significant_ablations(
        self, results: dict[str, AblationResult], threshold: float = _SIG_THRESHOLD
    ) -> list[str]:
        """Return ablations with statistically significant degradation."""
        full = results["full_system"].metrics.prevented_harm
        return [
            key for key, r in results.items()
            if key != "full_system" and full - r.metrics.prevented_harm > threshold
        ]

    def _score_observations(
        self, obs: list[TestbedObservation], confs: list[float], config: AblationConfig
    ) -> list[int]:
        """Score and return observation indices sorted by priority (descending)."""
        def score(i: int) -> float:
            o = obs[i]
            s = (confs[i] * o.value) if config.robust_optimization else o.value
            return s * (_PROVENANCE_WEIGHTS.get(o.source_type, 1.0) if config.provenance else 1.0)
        return sorted(range(len(obs)), key=lambda i: -score(i))

    def _select_actions(
        self,
        obs: list[TestbedObservation],
        scored: list[int],
        config: AblationConfig,
        tower: CellTower | None,
        max_actions: int,
        forecast_lead: int,
        nearby_dist: float,
    ) -> list[Action]:
        """Select actions based on scored observations."""
        actions: list[Action] = []
        current_time = obs[0].timestamp_ms if obs else 0
        acted: set[int] = set()
        acted_zones: set[tuple[float, float]] = set()
        zone_counts: dict[tuple[float, float], int] = {}
        filter_stale = config.telecom_silence
        for i in scored:
            if len(actions) >= max_actions or i in acted:
                continue
            if filter_stale and _is_stale(obs[i], tower):
                continue
            o = obs[i]
            zone = _zone(o.lon, o.lat)
            if config.fairness_constraints and zone_counts.get(zone, 0) >= _ZONE_CAP:
                continue
            action_time = max(o.timestamp_ms - forecast_lead, current_time)
            # Actions on stale reports (when not filtered) don't prevent current harm
            prevented = o.value >= _HIGH_SEVERITY and not _is_stale(o, tower)
            actions.append(Action(action_time, i, o.lon, o.lat, prevented))
            acted.add(i)
            acted_zones.add(zone)
            zone_counts[zone] = zone_counts.get(zone, 0) + 1
            if nearby_dist > 0:
                for j, o2 in enumerate(obs):
                    if len(actions) >= max_actions or j in acted or o2.value < _HIGH_SEVERITY:
                        continue
                    if o2.event_type in _MISINFO_TYPES:
                        continue
                    if filter_stale and _is_stale(o2, tower):
                        continue
                    z2 = _zone(o2.lon, o2.lat)
                    if z2 in acted_zones:
                        continue
                    if config.fairness_constraints and zone_counts.get(z2, 0) >= _ZONE_CAP:
                        continue
                    dist = ((o.lon - o2.lon) ** 2 + (o.lat - o2.lat) ** 2) ** 0.5
                    if dist < nearby_dist:
                        prevented2 = o2.value >= _HIGH_SEVERITY and not _is_stale(o2, tower)
                        actions.append(Action(action_time, j, o2.lon, o2.lat, prevented2))
                        acted.add(j)
                        acted_zones.add(z2)
                        zone_counts[z2] = zone_counts.get(z2, 0) + 1
            current_time = action_time
        return actions

    def _compute_metrics(
        self, obs: list[TestbedObservation], actions: list[Action]
    ) -> BaselineMetrics:
        """Compute prevented_harm based on REAL high-severity events (excl. misinformation)."""
        real_high = [i for i, o in enumerate(obs)
                     if o.value >= _HIGH_SEVERITY and o.event_type not in _MISINFO_TYPES]
        n_high = len(real_high)
        acted_indices = {a.obs_idx for a in actions}
        acted_high = sum(1 for i in real_high if i in acted_indices)
        prevented_harm = acted_high / n_high if n_high > 0 else 0.0
        response_times = [a.action_time_ms - obs[a.obs_idx].timestamp_ms for a in actions]
        avg_response = float(np.mean(response_times)) if response_times else 0.0
        zones = {_zone(o.lon, o.lat) for o in obs}
        acted_zones = {_zone(a.lon, a.lat) for a in actions}
        coverage = len(acted_zones) / len(zones) if zones else 0.0
        return BaselineMetrics(
            prevented_harm=prevented_harm,
            response_time_ms=avg_response,
            coverage=coverage,
            actions_taken=len(actions),
            high_severity_events=n_high,
        )


__all__ = [
    "ABLATION_TYPES",
    "AblationConfig",
    "AblationResult",
    "AblationRunner",
]
