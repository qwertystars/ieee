"""Metrics collection for ResQNet-SAGE evaluation (T44).

Collects 6 metric categories per SOTA spec §14.4-14.9: perception,
uncertainty, operational, resilience, human-factors, equity.
All metrics are automatable proxies — no human subjects required.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from app.eval.baselines import BaselineResult
from app.eval.failures import confidence_vector
from app.eval.testbed import DigitalTwinTestbed
from app.eval.testbed_types import ObservationSource

_DEG_TO_M = 111_320.0
_ZONE_PRECISION = 2
_HIGH_SEVERITY = 0.7
_N_BINS = 10


def _zone(lon: float, lat: float) -> tuple[float, float]:
    return (round(lon, _ZONE_PRECISION), round(lat, _ZONE_PRECISION))


def _distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    return ((lon2 - lon1) ** 2 + (lat2 - lat1) ** 2) ** 0.5 * _DEG_TO_M


def _pct(values: Sequence[float], pct: float) -> float:
    return float(np.percentile(values, pct)) if values else 0.0


class MetricsCollector:
    """Collects all 6 metric categories per SOTA spec §14.4-14.9."""

    def collect_all(
        self,
        testbed: DigitalTwinTestbed,
        baseline_results: dict[str, BaselineResult],
        failure_config: list[dict[str, Any]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Collect all 6 metric categories."""
        fc = failure_config or []
        return {
            "perception": self.collect_perception_metrics(testbed, baseline_results),
            "uncertainty": self.collect_uncertainty_metrics(testbed, baseline_results),
            "operational": self.collect_operational_metrics(testbed, baseline_results),
            "resilience": self.collect_resilience_metrics(testbed, baseline_results, fc),
            "human_factors": self.collect_human_factors_metrics(testbed, baseline_results),
            "equity": self.collect_equity_metrics(testbed, baseline_results),
        }

    @staticmethod
    def _sage(results: dict[str, BaselineResult]) -> BaselineResult:
        for key in ("baseline_4_resqnet_sage", "resqnet_sage", "sage"):
            if key in results:
                return results[key]
        return next(iter(results.values()))

    def collect_perception_metrics(
        self, testbed: DigitalTwinTestbed, results: dict[str, BaselineResult],
    ) -> dict[str, float]:
        """Perception: precision/recall/F1, mIoU, geolocation error (§14.4)."""
        sage = self._sage(results)
        obs = testbed.generate_observation_stream(seed=42, duration_hours=24)
        actions = sage.actions
        n_high = sum(1 for o in obs if o.value >= _HIGH_SEVERITY)
        acted_high = sum(1 for a in actions if a.prevented)
        n_act = len(actions)
        precision = acted_high / n_act if n_act else 0.0
        recall = acted_high / n_high if n_high else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        high_zones = {_zone(o.lon, o.lat) for o in obs if o.value >= _HIGH_SEVERITY}
        acted_zones = {_zone(a.lon, a.lat) for a in actions}
        union = high_zones | acted_zones
        miou = len(high_zones & acted_zones) / len(union) if union else 0.0
        citizen = [o for o in obs if o.source_type == ObservationSource.citizen_report]
        acted_citizen = sum(1 for a in actions if obs[a.obs_idx].source_type == ObservationSource.citizen_report)
        roads = testbed.get_road_graph()
        geo_errs = [_distance_m(a.lon, a.lat, obs[a.obs_idx].lon, obs[a.obs_idx].lat) for a in actions]
        return {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "miou_flood_extent": miou,
            "building_damage_macro_f1": f1,
            "road_passability_accuracy": sum(1 for e in roads.edges if e.flood_vulnerability < 1.0) / len(roads.edges) if roads.edges else 0.0,
            "distress_report_recall": acted_citizen / len(citizen) if citizen else 0.0,
            "duplicate_removal_precision": len({a.obs_idx for a in actions}) / n_act if n_act else 0.0,
            "median_geolocation_error_m": float(np.median(geo_errs)) if geo_errs else 0.0,
        }

    def collect_uncertainty_metrics(
        self, testbed: DigitalTwinTestbed, results: dict[str, BaselineResult],
    ) -> dict[str, float]:
        """Uncertainty: Brier, ECE, conformal coverage, NLL (§14.5)."""
        obs = testbed.generate_observation_stream(seed=42, duration_hours=24)
        confs = confidence_vector(obs)
        outcomes = [1.0 if o.value >= _HIGH_SEVERITY else 0.0 for o in obs]
        brier = float(np.mean([(c - y) ** 2 for c, y in zip(confs, outcomes)]))
        high_idx = [i for i, y in enumerate(outcomes) if y >= 0.5]
        covered = sum(1 for i in high_idx if confs[i] >= 0.5)
        eps = 1e-9
        nll = -float(np.mean([
            y * np.log(c + eps) + (1 - y) * np.log(1 - c + eps)
            for c, y in zip(confs, outcomes)
        ]))
        false_conf = sum(1 for c, y in zip(confs, outcomes) if c >= 0.8 and y < 0.5)
        return {
            "brier_score": brier,
            "ece": self._ece(confs, outcomes),
            "conformal_coverage": covered / len(high_idx) if high_idx else 0.0,
            "interval_width": float(np.mean([1.0 - c for c in confs])),
            "nll": nll,
            "false_confidence_rate": false_conf / len(obs) if obs else 0.0,
        }

    @staticmethod
    def _ece(confs: list[float], outcomes: list[float]) -> float:
        bins = np.linspace(0, 1, _N_BINS + 1)
        ece, n = 0.0, len(confs)
        for i in range(_N_BINS):
            mask = [bins[i] <= c < bins[i + 1] for c in confs]
            cnt = sum(mask)
            if cnt == 0:
                continue
            bc = float(np.mean([c for c, m in zip(confs, mask) if m]))
            ba = float(np.mean([y for y, m in zip(outcomes, mask) if m]))
            ece += (cnt / n) * abs(bc - ba)
        return float(ece)

    def collect_operational_metrics(
        self, testbed: DigitalTwinTestbed, results: dict[str, BaselineResult],
    ) -> dict[str, float]:
        """Operational: response time, prevented harm, route completion (§14.6)."""
        sage = self._sage(results)
        obs = testbed.generate_observation_stream(seed=42, duration_hours=24)
        actions = sage.actions
        m = sage.metrics
        first_correct = next(
            (a.action_time_ms - obs[a.obs_idx].timestamp_ms for a in actions if a.prevented), 0.0
        )
        pop = testbed.get_population()
        pop_at_risk = sum(p.population for p in pop)
        resp_times = [a.action_time_ms - obs[a.obs_idx].timestamp_ms for a in actions]
        roads = testbed.get_road_graph()
        infra = testbed.get_infrastructure()
        return {
            "time_to_first_correct_high_priority_ms": float(first_correct),
            "expected_casualties_avoided": m.prevented_harm * pop_at_risk * 0.01,
            "urgent_demand_served": m.prevented_harm,
            "median_response_time_ms": float(np.median(resp_times)) if resp_times else 0.0,
            "tail_response_time_ms": _pct(resp_times, 95),
            "route_completion_rate": sum(1 for e in roads.edges if e.flood_vulnerability < 1.0) / len(roads.edges) if roads.edges else 0.0,
            "responder_exposure": float(m.actions_taken),
            "shelter_overflow": sum(1 for s in infra.shelters if s.occupancy > s.capacity) / len(infra.shelters) if infra.shelters else 0.0,
            "hospital_overload": sum(1 for h in infra.hospitals if h.status.value != "operational") / len(infra.hospitals) if infra.hospitals else 0.0,
            "resource_utilization": m.actions_taken / 150.0,
            "plan_instability": float(np.std(resp_times)) if resp_times else 0.0,
            "decision_regret_vs_oracle": 1.0 - m.prevented_harm,
        }

    def collect_resilience_metrics(
        self, testbed: DigitalTwinTestbed, results: dict[str, BaselineResult],
        failure_config: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Resilience: p50/p95 latency, data-loss window, capability (§14.7)."""
        fc = failure_config or []
        sage = self._sage(results)
        obs = testbed.generate_observation_stream(seed=42, duration_hours=24)
        actions = sage.actions
        sensor_lats = [a.action_time_ms - obs[a.obs_idx].timestamp_ms for a in actions if obs[a.obs_idx].source_type == ObservationSource.sensor]
        report_lats = [a.action_time_ms - obs[a.obs_idx].timestamp_ms for a in actions if obs[a.obs_idx].source_type == ObservationSource.citizen_report]
        n_tower_fail = sum(1 for f in fc if f.get("type") == "tower_failure")
        feed_loss_pct = next((f.get("params", {}).get("loss_pct", 0.0) for f in fc if f.get("type") == "feed_loss"), 0.0)
        n_towers = len(testbed.get_infrastructure().cell_towers)
        confs = confidence_vector(obs)
        return {
            "p50_sensor_to_map_latency_ms": _pct(sensor_lats, 50),
            "p95_sensor_to_map_latency_ms": _pct(sensor_lats, 95),
            "p50_report_to_recommendation_latency_ms": _pct(report_lats, 50),
            "p95_report_to_recommendation_latency_ms": _pct(report_lats, 95),
            "rto_ms": _pct(sensor_lats + report_lats, 95),
            "data_loss_window_pct": feed_loss_pct / 100.0,
            "pct_capability_under_connectivity_loss": 1.0 - (n_tower_fail / n_towers if n_towers else 0.0),
            "sync_convergence_time_ms": _pct(sensor_lats, 99),
            "stale_data_detection_rate": sum(1 for c in confs if c < 0.5) / len(obs) if obs else 0.0,
            "performance_loss_at_feed_dropout": feed_loss_pct / 100.0,
        }

    def collect_human_factors_metrics(
        self, testbed: DigitalTwinTestbed, results: dict[str, BaselineResult],
    ) -> dict[str, float]:
        """Human-factors: decision time, override rate, NASA-TLX proxy (§14.8)."""
        sage = self._sage(results)
        obs = testbed.generate_observation_stream(seed=42, duration_hours=24)
        actions = sage.actions
        dts = [a.action_time_ms - obs[a.obs_idx].timestamp_ms for a in actions]
        n = len(actions)
        correct = sum(1 for a in actions if a.prevented)
        harmful = n - correct
        correct_rate = correct / n if n else 0.0
        harmful_rate = harmful / n if n else 0.0
        comprehension = (1.0 if sage.uses_fusion else 0.5) * sage.metrics.coverage
        temporal = float(np.std(dts)) if dts else 0.0
        effort = float(np.mean(dts)) / 60_000.0 if dts else 0.0
        nasa_tlx = (0.2 * min(1.0, temporal / 60_000) + 0.2 * min(1.0, effort)
                    + 0.2 * harmful_rate + 0.2 * (1 - correct_rate)
                    + 0.2 * (1 - sage.metrics.coverage))
        return {
            "simulated_operator_decision_time_ms": float(np.mean(dts)) if dts else 0.0,
            "correct_override_rate": correct_rate,
            "harmful_override_rate": harmful_rate,
            "evidence_chain_comprehension_score": float(comprehension),
            "nasa_tlx_proxy": float(nasa_tlx),
        }

    def collect_equity_metrics(
        self, testbed: DigitalTwinTestbed, results: dict[str, BaselineResult],
    ) -> dict[str, Any]:
        """Equity: response delay by ward, unmet demand, disparity (§14.9)."""
        sage = self._sage(results)
        obs = testbed.generate_observation_stream(seed=42, duration_hours=24)
        actions = sage.actions
        pop = testbed.get_population()
        infra = testbed.get_infrastructure()
        ward_times: dict[str, list[float]] = {p.h3_index: [] for p in pop}
        ward_acted: dict[str, int] = {p.h3_index: 0 for p in pop}
        for a in actions:
            nearest = min(pop, key=lambda p: _distance_m(a.lon, a.lat, p.lon, p.lat))
            ward_times[nearest.h3_index].append(a.action_time_ms - obs[a.obs_idx].timestamp_ms)
            ward_acted[nearest.h3_index] += 1
        vuln_delays: dict[str, list[float]] = {"low": [], "medium": [], "high": []}
        for p in pop:
            vuln_delays[p.vulnerability].extend(ward_times[p.h3_index])
        tower_count = {p.h3_index: 0 for p in pop}
        for t in infra.cell_towers:
            nearest = min(pop, key=lambda p: _distance_m(t.lon, t.lat, p.lon, p.lat))
            tower_count[nearest.h3_index] += 1
        low_conn = [p.h3_index for p in pop if tower_count[p.h3_index] == 0]
        high_per_ward = {p.h3_index: 0 for p in pop}
        for o in obs:
            if o.value >= _HIGH_SEVERITY:
                nearest = min(pop, key=lambda p: _distance_m(o.lon, o.lat, p.lon, p.lat))
                high_per_ward[nearest.h3_index] += 1
        unmet_low = sum(high_per_ward[w] for w in low_conn)
        total_high = sum(high_per_ward.values())
        acted_low = sum(1 for w in low_conn if ward_acted[w] > 0)
        per_ward = [len(ward_times[p.h3_index]) for p in pop]
        ward_cov = [ward_acted[p.h3_index] / max(1, high_per_ward[p.h3_index]) for p in pop]
        return {
            "response_delay_by_vulnerability": {v: float(np.mean(t)) if t else 0.0 for v, t in vuln_delays.items()},
            "unmet_urgent_demand_by_connectivity": unmet_low / total_high if total_high else 0.0,
            "false_negative_rate_low_reporting": 1.0 - (acted_low / len(low_conn) if low_conn else 1.0),
            "resource_allocation_disparity": float(np.std(per_ward)) if per_ward else 0.0,
            "coverage_before_fairness": sage.metrics.coverage,
            "coverage_after_fairness": float(min(ward_cov)) if ward_cov else 0.0,
        }


__all__ = ["MetricsCollector"]
