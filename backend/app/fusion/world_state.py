"""Probabilistic world state estimation via Dynamic Bayesian Network.

Uses pgmpy's DynamicBayesianNetwork + DBNInference for exact inference
(junction tree) — millisecond-scale, suitable for real-time FastAPI requests.
PyMC's MCMC is too slow (seconds vs milliseconds for pgmpy's exact inference).

Model structure (per hazard type, e.g., flood):
  - State node: {hazard}_severity in {none, minor, moderate, severe, extreme}
  - Inter-slice edge: state_t -> state_{t+1} (Markov transition)
  - Intra-slice edges: state -> {hazard}_sensor_reading,
    state -> {hazard}_citizen_report, state -> {hazard}_satellite_observation

Evidence discretization bin boundaries (documented per observation type):
  - Sensor (water level meters): [0, 0.5, 1.5, 3.0, 5.0, inf) -> 5 bins
  - Citizen report (severity keyword): direct map to severity states
  - Satellite (flood extent %): [0, 5, 15, 30, 50, inf) -> 5 bins

All evidence must be discrete — pgmpy DBN only accepts TabularCPD.
"""

from __future__ import annotations

from collections import deque

from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import DBNInference
from pgmpy.models import DynamicBayesianNetwork as DBN

# Default severity states (5-level scale per NWS/NOAA flood categories).
DEFAULT_SEVERITY_STATES: tuple[str, ...] = (
    "none", "minor", "moderate", "severe", "extreme",
)

# Observation node suffixes (intra-slice children of each state node).
# Full node name is f"{hazard_type}_{suffix}" to support multiple hazards.
OBSERVATION_NODES: tuple[str, ...] = (
    "sensor_reading", "citizen_report", "satellite_observation",
)

# Default rolling window size (number of time slices to retain evidence).
DEFAULT_WINDOW_SIZE: int = 10

# Sensor discretization bins for flood (water level in meters).
# Boundaries: [0, 0.5, 1.5, 3.0, 5.0, inf) -> 5 bins matching severity states.
FLOOD_SENSOR_BINS: tuple[float, ...] = (0.0, 0.5, 1.5, 3.0, 5.0, float("inf"))

# Satellite discretization bins for flood (flood extent %).
FLOOD_SATELLITE_BINS: tuple[float, ...] = (0.0, 5.0, 15.0, 30.0, 50.0, float("inf"))


def _default_transition(n: int) -> list[list[float]]:
    """Persistence-biased transition matrix.

    Diagonal = 0.7 (state persists), off-diagonal = 0.3/(n-1) (spread).
    """
    off = 0.3 / (n - 1) if n > 1 else 0.0
    return [[0.7 if i == j else off for j in range(n)] for i in range(n)]


def _sensor_cpd(
    state: tuple[str, int],
    obs: tuple[str, int],
    n: int,
    accuracy: float = 0.85,
) -> TabularCPD:
    """Observation CPD: P(obs | state). Diagonal=accuracy, rest=(1-acc)/(n-1)."""
    off = (1.0 - accuracy) / (n - 1) if n > 1 else 0.0
    values = [[accuracy if i == j else off for j in range(n)] for i in range(n)]
    return TabularCPD(
        variable=obs, variable_card=n,
        evidence=[state], evidence_card=[n], values=values,
    )


def discretize_sensor(
    value: float, bins: tuple[float, ...] = FLOOD_SENSOR_BINS,
) -> int:
    """Map a continuous sensor reading to a discrete state index.

    Bins are left-closed, right-open: [bins[i], bins[i+1]) -> state i.
    """
    for i in range(len(bins) - 1):
        if bins[i] <= value < bins[i + 1]:
            return i
    return len(bins) - 2  # last bin


class WorldStateEstimator:
    """Stateful DBN estimator with rolling evidence window.

    Supports multiple hazard types as independent sub-networks within
    a single DBN. Each hazard has its own state node and observation nodes.
    Inference results are cached and invalidated on new evidence or step().
    """

    def __init__(
        self,
        hazard_types: tuple[str, ...] = ("flood",),
        states: tuple[str, ...] = DEFAULT_SEVERITY_STATES,
        prior: dict[str, float] | None = None,
        window_size: int = DEFAULT_WINDOW_SIZE,
    ) -> None:
        self._states = states
        self._hazard_types = hazard_types
        self._window_size = window_size
        self._current_slice = 0
        self._evidence_window: deque[dict[tuple[str, int], int]] = deque(
            maxlen=window_size,
        )
        self._cache: dict[tuple[str, int], dict[str, float]] = {}

        n = len(states)
        if prior:
            prior_list = [prior.get(s, 0.0) for s in states]
        else:
            # Default: P(severe)=0.1 for stopping condition test.
            prior_list = (
                [0.4, 0.25, 0.15, 0.1, 0.1] if n == 5 else [0.7, 0.2, 0.1]
            )

        self._dbn = self._build_dbn(hazard_types, states, prior_list)
        self._infer = DBNInference(self._dbn)

    def _build_dbn(
        self,
        hazard_types: tuple[str, ...],
        states: tuple[str, ...],
        prior: list[float],
    ) -> DBN:
        """Construct the DBN with edges and CPDs."""
        n = len(states)
        dbn = DBN()

        edges: list[tuple[tuple[str, int], tuple[str, int]]] = []
        cpds: list[TabularCPD] = []

        for hz in hazard_types:
            state_node = f"{hz}_severity"

            # Inter-slice: state_t -> state_{t+1}
            edges.append(((state_node, 0), (state_node, 1)))

            # Intra-slice: state -> observations (hazard-specific names)
            for obs in OBSERVATION_NODES:
                obs_node = f"{hz}_{obs}"
                edges.append(((state_node, 0), (obs_node, 0)))

            # Prior CPD: P(state_0)
            cpds.append(TabularCPD(
                variable=(state_node, 0), variable_card=n,
                values=[[p] for p in prior],
            ))

            # Transition CPD: P(state_1 | state_0)
            cpds.append(TabularCPD(
                variable=(state_node, 1), variable_card=n,
                evidence=[(state_node, 0)], evidence_card=[n],
                values=_default_transition(n),
            ))

            # Observation CPDs: P(obs_0 | state_0)
            # pgmpy auto-creates slice 1 versions via initialize_initial_state().
            for obs in OBSERVATION_NODES:
                obs_node = f"{hz}_{obs}"
                cpds.append(_sensor_cpd(
                    state=(state_node, 0), obs=(obs_node, 0), n=n,
                ))

        dbn.add_edges_from(edges)
        dbn.add_cpds(*cpds)
        dbn.initialize_initial_state()
        return dbn

    def add_evidence(
        self, evidence: dict[tuple[str, int] | str, str | int],
    ) -> None:
        """Add observations for the current time slice.

        Evidence keys are (node, time_slice) tuples or plain node names
        (which default to the current slice). Values are state names or indices.
        """
        normalized: dict[tuple[str, int], int] = {}
        for key, val in evidence.items():
            if isinstance(key, tuple):
                node, t = key
            else:
                node, t = key, self._current_slice
            normalized[(node, t)] = self._state_index(val)
        self._evidence_window.append(normalized)
        self._cache.clear()

    def _state_index(self, val: str | int) -> int:
        """Convert state name or index to integer index."""
        if isinstance(val, int):
            return val
        if val in self._states:
            return self._states.index(val)
        raise ValueError(f"Unknown state: {val}. Expected one of {self._states}")

    def _collect_evidence(self) -> dict[tuple[str, int], int]:
        """Flatten the evidence window into a single dict."""
        result: dict[tuple[str, int], int] = {}
        for slice_evidence in self._evidence_window:
            result.update(slice_evidence)
        return result

    def filter_state(self, hazard_type: str) -> dict[str, float]:
        """Return P(state_t | evidence) for the given hazard at current slice."""
        return self.get_state_distribution(hazard_type, self._current_slice)

    def get_state_distribution(
        self, hazard_type: str, time_slice: int,
    ) -> dict[str, float]:
        """Return P(state | evidence) for a hazard at a specific time slice."""
        cache_key = (hazard_type, time_slice)
        if cache_key in self._cache:
            return self._cache[cache_key]

        state_node = f"{hazard_type}_severity"
        evidence = self._collect_evidence()

        result = self._infer.forward_inference(
            variables=[(state_node, time_slice)],
            evidence=evidence,
        )

        # forward_inference returns a dict mapping variable tuples to
        # DiscreteFactor objects (or a list in older pgmpy versions).
        if isinstance(result, dict):
            factor = next(iter(result.values()))
        elif isinstance(result, list):
            factor = result[0]
        else:
            factor = result
        values = factor.values

        total = sum(values)
        probs = (
            [float(v / total) for v in values]
            if total > 0
            else [0.0] * len(values)
        )

        dist = dict(zip(self._states, probs, strict=True))
        self._cache[cache_key] = dist
        return dist

    def step(self) -> None:
        """Advance the time slice (shift evidence window)."""
        self._current_slice += 1
        self._cache.clear()

    @property
    def current_slice(self) -> int:
        return self._current_slice


__all__ = [
    "DEFAULT_SEVERITY_STATES",
    "FLOOD_SATELLITE_BINS",
    "FLOOD_SENSOR_BINS",
    "OBSERVATION_NODES",
    "WorldStateEstimator",
    "discretize_sensor",
]
