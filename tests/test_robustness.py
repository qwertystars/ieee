from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.eval.failures import FailureInjector
from app.eval.robustness_metrics import (
    compute_false_alert_burden,
    compute_harm_weighted_error,
    compute_risk_coverage,
    compute_severe_error_rate,
)
from app.eval.testbed_types import ObservationSource
from app.eval.testbed_types import TestbedObservation as Observation
from app.optimizer.fairness_metrics import compute_subgroup_gap

from scripts.benchmark_contract_types import JsonValue
from scripts.run_robustness_suite import (
    FAMILIES,
    evaluate_fixture,
    evaluate_suite,
)

POLICY = ROOT / "tests/fixtures/robustness-policy-v1.json"
STALE = ROOT / "tests/fixtures/stale-conflicting-sensors.json"
MANIFEST = ROOT / "data/datasets/benchmark-v1.json"


def _policy() -> dict[str, JsonValue]:
    parsed = json.loads(POLICY.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def test_all_failure_families_have_metrics_and_pass_thresholds() -> None:
    code, status, metrics = evaluate_suite(_policy())

    assert code == 0
    assert status == "PASS"
    families = metrics["families"]
    assert isinstance(families, dict)
    assert set(families) == set(FAMILIES)
    assert all(isinstance(result, dict) and result["passed"] is True for result in families.values())
    assert metrics["release_blocked_by_external_data"] is True


def test_metric_formulas_measure_burden_severe_errors_and_harm() -> None:
    predictions = (True, False, True, None)
    actual = (False, True, False, True)

    assert compute_false_alert_burden(predictions, (False, True, False, True)) == 1.0
    assert compute_severe_error_rate(predictions, actual, (False, True, False, True)) == 0.5
    assert compute_harm_weighted_error((True, False), (False, True)) == 1.0


def test_selective_prediction_risk_coverage_retains_confident_predictions() -> None:
    result = compute_risk_coverage(
        (True, False, True, False),
        (True, True, False, False),
        (0.9, 0.8, 0.7, 0.6),
        requested_coverage=0.5,
    )

    assert result.selected_count == 2
    assert result.observed_coverage == 0.5
    assert result.risk == 0.5


def test_subgroup_gap_excludes_underpowered_groups_and_reports_privacy_boundary() -> None:
    gap = compute_subgroup_gap(
        {"low": 0.8, "connected": 0.95, "small": 0.1},
        {"low": 200, "connected": 200, "small": 199},
    )

    assert abs(gap.value - 0.15) < 1e-9
    assert gap.eligible_groups == ("connected", "low")
    assert gap.excluded_groups == ("small",)
    assert _policy()["privacy"]["raw_pii"] is False


def test_attack_budget_and_release_threshold_reject_unsafe_policy() -> None:
    policy = _policy()
    thresholds = policy["thresholds"]
    assert isinstance(thresholds, dict)
    thresholds["severe_error_rate_max"] = 0.0

    code, status, metrics = evaluate_suite(policy)

    assert code == 1
    assert status == "FAIL"
    assert any("release-blocking" in finding for finding in metrics["findings"])


def test_sensor_injectors_preserve_provenance_and_mark_conflicts() -> None:
    observations = [
        Observation(1, ObservationSource.sensor, 1.0, 1.0, 0.2, "m", "water"),
        Observation(2, ObservationSource.official_alert, 1.0, 1.0, 0.8, "m", "water"),
    ]
    injector = FailureInjector(seed=2025)

    delayed = injector.inject_sensor_delay(observations, delay_minutes=1)
    duplicated = injector.inject_sensor_duplicates(observations, count=1)
    conflicting = injector.inject_conflicting_sensors(observations, count=1)

    assert delayed[0].timestamp_ms == 60_001
    assert delayed[1].timestamp_ms == 2
    assert len(duplicated) == 3
    assert conflicting[-1].event_type == "sensor_conflict"
    assert conflicting[-1].value == 0.8


def test_stale_conflict_fixture_requires_every_affected_route_to_abstain() -> None:
    code, status, metrics = evaluate_fixture(_policy(), STALE)

    assert code == 0
    assert status == "PASS"
    assert metrics["routes_checked"] == 5
    assert metrics["conflict_resolution"]["truth_selected"] is False


def test_stale_conflict_fixture_rejects_prediction_or_missing_uncertainty(tmp_path: Path) -> None:
    fixture = json.loads(STALE.read_text(encoding="utf-8"))
    assert isinstance(fixture, dict)
    routes = fixture["routes"]
    assert isinstance(routes, list)
    routes[0]["status"] = "available"
    routes[0]["uncertainty_labeled"] = False
    path = tmp_path / "unsafe-stale.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    code, status, metrics = evaluate_fixture(_policy(), path)

    assert code == 1
    assert status == "FAIL"
    assert metrics["routes_checked"] == 5


def test_exact_happy_cli_writes_normative_validation_only_report(tmp_path: Path) -> None:
    report = tmp_path / "task-18-happy.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_robustness_suite.py",
            "--manifest",
            str(MANIFEST),
            "--report",
            str(report),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "status=PASS"
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["task_id"] == "18"
    assert payload["status"] == "PASS"
    assert payload["metrics"]["external_validation"]["status"] == "DEFERRED_EXTERNAL"
