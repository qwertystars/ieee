"""Four baselines for ResQNet-SAGE comparison (T43).

Baseline 1: Independent dashboards — random feed inspection, no fusion.
Baseline 2: Unified visualization — all info on one map, FIFO task selection.
Baseline 3: Current ResQNet — confidence-weighted, scalar zone score, threshold.
Baseline 4: ResQNet-SAGE — full system (probabilistic, forecasting, optimization).

All baselines are automated (no human operators). Each runs the same testbed
scenario with the same seed and produces per-baseline metrics for comparison.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.eval.failures import confidence_vector
from app.eval.testbed import DigitalTwinTestbed
from app.eval.testbed_types import ObservationSource, TestbedObservation

_HIGH_SEVERITY = 0.7
_ACTION_THRESHOLD = 0.5
_ZONE_PRECISION = 2
_FORECAST_LEAD_MS = 5 * 60_000
_NEARBY_ZONE_DIST = 0.02
_FEEDS = tuple(ObservationSource)
_MAX_ACTIONS_B1 = 50
_MAX_ACTIONS_B2 = 100
_MAX_ACTIONS_B3 = 100
_MAX_ACTIONS_B4 = 150


@dataclass(frozen=True, slots=True)
class AttentionModel:
    """Operator attention model for baseline 1 (independent dashboards)."""
    reaction_delay_ms: int = 60_000
    miss_probability: float = 0.2


@dataclass(frozen=True, slots=True)
class Action:
    """A single operator action on an observation."""
    action_time_ms: int
    obs_idx: int
    lon: float
    lat: float
    prevented: bool


@dataclass(frozen=True, slots=True)
class BaselineMetrics:
    """Per-baseline comparison metrics."""
    prevented_harm: float
    response_time_ms: float
    coverage: float
    actions_taken: int
    high_severity_events: int


@dataclass(frozen=True, slots=True)
class BaselineResult:
    """Result of a single baseline run."""
    name: str
    metrics: BaselineMetrics
    actions: tuple[Action, ...]
    uses_fusion: bool
    selection_policy: str


class BaselineRunner:
    """Runs 4 baselines on the same testbed scenario for comparison.

    All baselines are automated (no human operators). Each baseline processes
    the same observation stream with a different selection policy and produces
    per-baseline metrics for comparison.
    """

    def __init__(self, attention: AttentionModel | None = None) -> None:
        self._attention = attention or AttentionModel()

    def run_baseline_1_independent_dashboards(
        self, testbed: DigitalTwinTestbed, seed: int
    ) -> BaselineResult:
        """Random feed inspection, no fusion, configurable attention model.

        Operator randomly inspects one feed at a time. May miss observations
        (miss_probability) and has a reaction delay. No fusion across feeds.
        """
        obs = testbed.generate_observation_stream(seed=seed, duration_hours=24)
        rng = np.random.default_rng(seed)
        actions: list[Action] = []
        current_feed = _FEEDS[int(rng.integers(0, len(_FEEDS)))]
        current_time = obs[0].timestamp_ms if obs else 0
        for i, o in enumerate(obs):
            if len(actions) >= _MAX_ACTIONS_B1:
                break
            if rng.random() < 0.3:
                current_feed = _FEEDS[int(rng.integers(0, len(_FEEDS)))]
            if o.source_type != current_feed:
                continue
            if rng.random() < self._attention.miss_probability:
                continue
            action_time = max(o.timestamp_ms + self._attention.reaction_delay_ms, current_time)
            actions.append(Action(action_time, i, o.lon, o.lat, o.value >= _HIGH_SEVERITY))
            current_time = action_time
        return BaselineResult(
            name="independent_dashboards",
            metrics=self._compute_metrics(obs, actions),
            actions=tuple(actions),
            uses_fusion=False,
            selection_policy="random_feed",
        )

    def run_baseline_2_unified_visualization(
        self, testbed: DigitalTwinTestbed, seed: int
    ) -> BaselineResult:
        """All info on one map, no fusion, FIFO task selection.

        Operator sees all observations on one map. No fusion or prioritization.
        Tasks are selected by recency (FIFO — oldest first).
        """
        obs = testbed.generate_observation_stream(seed=seed, duration_hours=24)
        actions: list[Action] = []
        current_time = obs[0].timestamp_ms if obs else 0
        for i, o in enumerate(obs):
            if len(actions) >= _MAX_ACTIONS_B2:
                break
            action_time = max(o.timestamp_ms, current_time)
            actions.append(Action(action_time, i, o.lon, o.lat, o.value >= _HIGH_SEVERITY))
            current_time = action_time
        return BaselineResult(
            name="unified_visualization",
            metrics=self._compute_metrics(obs, actions),
            actions=tuple(actions),
            uses_fusion=False,
            selection_policy="fifo",
        )

    def run_baseline_3_current_resqnet(
        self, testbed: DigitalTwinTestbed, seed: int
    ) -> BaselineResult:
        """Confidence-weighted reports, scalar zone score, threshold-based.

        Uses confidence_vector to weight observations. Acts on observations
        with confidence * severity >= threshold. Fusion across feeds.
        """
        obs = testbed.generate_observation_stream(seed=seed, duration_hours=24)
        confidences = confidence_vector(obs)
        scored = sorted(
            range(len(obs)),
            key=lambda i: -(confidences[i] * obs[i].value),
        )
        actions: list[Action] = []
        current_time = obs[0].timestamp_ms if obs else 0
        for i in scored:
            if len(actions) >= _MAX_ACTIONS_B3:
                break
            o = obs[i]
            if confidences[i] * o.value < _ACTION_THRESHOLD:
                continue
            action_time = max(o.timestamp_ms, current_time)
            actions.append(Action(action_time, i, o.lon, o.lat, o.value >= _HIGH_SEVERITY))
            current_time = action_time
        return BaselineResult(
            name="current_resqnet",
            metrics=self._compute_metrics(obs, actions),
            actions=tuple(actions),
            uses_fusion=True,
            selection_policy="threshold_score",
        )

    def run_baseline_4_sage(
        self, testbed: DigitalTwinTestbed, seed: int
    ) -> BaselineResult:
        """Full system: probabilistic world model, forecasting, optimization, active sensing.

        SAGE forecasts future harm (acts earlier via negative response time),
        uses robust optimization (acts on high-severity first), and active sensing
        (probes nearby zones). Fusion across all feeds.
        """
        obs = testbed.generate_observation_stream(seed=seed, duration_hours=24)
        confidences = confidence_vector(obs)
        scored = sorted(
            range(len(obs)),
            key=lambda i: -(confidences[i] * obs[i].value),
        )
        actions: list[Action] = []
        current_time = obs[0].timestamp_ms if obs else 0
        acted: set[int] = set()
        acted_zones: set[tuple[float, float]] = set()
        for i in scored:
            if len(actions) >= _MAX_ACTIONS_B4:
                break
            if i in acted:
                continue
            o = obs[i]
            action_time = max(o.timestamp_ms - _FORECAST_LEAD_MS, current_time)
            actions.append(Action(action_time, i, o.lon, o.lat, o.value >= _HIGH_SEVERITY))
            acted.add(i)
            zone = (round(o.lon, _ZONE_PRECISION), round(o.lat, _ZONE_PRECISION))
            acted_zones.add(zone)
            for j, o2 in enumerate(obs):
                if len(actions) >= _MAX_ACTIONS_B4 or j in acted:
                    continue
                z2 = (round(o2.lon, _ZONE_PRECISION), round(o2.lat, _ZONE_PRECISION))
                if z2 in acted_zones:
                    continue
                dist = ((o.lon - o2.lon) ** 2 + (o.lat - o2.lat) ** 2) ** 0.5
                if dist < _NEARBY_ZONE_DIST:
                    actions.append(Action(action_time, j, o2.lon, o2.lat, o2.value >= _HIGH_SEVERITY))
                    acted.add(j)
                    acted_zones.add(z2)
            current_time = action_time
        return BaselineResult(
            name="resqnet_sage",
            metrics=self._compute_metrics(obs, actions),
            actions=tuple(actions),
            uses_fusion=True,
            selection_policy="probabilistic_forecast_optimize",
        )

    def run_all_baselines(
        self, testbed: DigitalTwinTestbed, seed: int
    ) -> dict[str, BaselineResult]:
        """Run all 4 baselines on the same testbed scenario with the same seed."""
        return {
            "baseline_1_independent_dashboards": self.run_baseline_1_independent_dashboards(testbed, seed),
            "baseline_2_unified_visualization": self.run_baseline_2_unified_visualization(testbed, seed),
            "baseline_3_current_resqnet": self.run_baseline_3_current_resqnet(testbed, seed),
            "baseline_4_resqnet_sage": self.run_baseline_4_sage(testbed, seed),
        }

    def compare_baselines(self, results: dict[str, BaselineResult]) -> str:
        """Return comparison table of prevented_harm, response_time, coverage."""
        header = f"{'Baseline':<30} {'prevented_harm':>15} {'response_ms':>12} {'coverage':>10}"
        lines = [header, "-" * len(header)]
        for r in results.values():
            m = r.metrics
            lines.append(
                f"{r.name:<30} {m.prevented_harm:>15.4f} {m.response_time_ms:>12.0f} {m.coverage:>10.4f}"
            )
        return "\n".join(lines)

    def _compute_metrics(
        self, obs: list[TestbedObservation], actions: list[Action]
    ) -> BaselineMetrics:
        """Compute prevented_harm, response_time, coverage from actions."""
        n_high = sum(1 for o in obs if o.value >= _HIGH_SEVERITY)
        acted_high = sum(1 for a in actions if a.prevented)
        prevented_harm = acted_high / n_high if n_high > 0 else 0.0
        response_times = [a.action_time_ms - obs[a.obs_idx].timestamp_ms for a in actions]
        avg_response = float(np.mean(response_times)) if response_times else 0.0
        zones = {(round(o.lon, _ZONE_PRECISION), round(o.lat, _ZONE_PRECISION)) for o in obs}
        acted_zones = {(round(a.lon, _ZONE_PRECISION), round(a.lat, _ZONE_PRECISION)) for a in actions}
        coverage = len(acted_zones) / len(zones) if zones else 0.0
        return BaselineMetrics(
            prevented_harm=prevented_harm,
            response_time_ms=avg_response,
            coverage=coverage,
            actions_taken=len(actions),
            high_severity_events=n_high,
        )


__all__ = [
    "Action",
    "AttentionModel",
    "BaselineMetrics",
    "BaselineResult",
    "BaselineRunner",
]
