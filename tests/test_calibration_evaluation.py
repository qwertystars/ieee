from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.fusion.calibration_metrics import (
    compute_ensemble_disagreement,
    compute_risk_coverage,
    compute_segmentation_confidence,
)
from app.fusion.calibration_policy import (
    AbstentionInput,
    OutputType,
    decide_abstention,
    policy_for_output_type,
    release_gate,
)

from scripts.evaluate_calibration import evaluate_calibration

BENCHMARK = ROOT / "data/datasets/benchmark-v1.json"
MODELS = ROOT / "backend/data/models/manifests.json"
FINAL_TEST_FIXTURE = ROOT / "tests/fixtures/calibration-on-final-test.json"


def test_happy_manifest_reports_thresholds_and_abstention() -> None:
    report = evaluate_calibration(BENCHMARK, MODELS, True)

    assert report.status == "PASS"
    assert report.exit_code == 0
    assert report.metrics["model_count"] == 3
    assert report.metrics["external_calibration_pending"] == 3
    assert report.metrics["all_safety_outputs_abstain_when_unavailable"] is True
    assert all(
        isinstance(model, dict) and model["thresholds"]["ece_max"] == 0.05
        for model in report.model_reports.values()
    )


def test_final_test_tuning_fails_closed() -> None:
    report = evaluate_calibration(FINAL_TEST_FIXTURE, None, True)

    assert report.status == "FAIL"
    assert report.exit_code == 1
    assert any("may not be test" in finding for finding in report.findings)


def test_missing_calibration_object_is_not_proxy_success(tmp_path: Path) -> None:
    models = json.loads(MODELS.read_text(encoding="utf-8"))
    assert isinstance(models, list)
    models[0]["calibration"] = None
    path = tmp_path / "missing-calibration.json"
    path.write_text(json.dumps(models), encoding="utf-8")

    report = evaluate_calibration(BENCHMARK, path, True)

    assert report.status == "FAIL"
    assert any("explicit object" in finding for finding in report.findings)


def test_abstention_and_release_gate_fail_closed() -> None:
    policy = policy_for_output_type(OutputType.SAR_SEGMENTATION)
    decision = decide_abstention(AbstentionInput(OutputType.SAR_SEGMENTATION, False))
    gate = release_gate(policy, False, None, None)

    assert decision.abstain is True
    assert decision.reason == "calibration_unavailable"
    assert gate.allowed is False
    assert gate.status == "abstain"


def test_uncertainty_metrics_are_named_and_bounded() -> None:
    probabilities = np.array(
        [
            [[0.9, 0.2], [0.8, 0.4]],
            [[0.1, 0.8], [0.7, 0.6]],
        ]
    )
    members = np.array(
        [
            [[0.1, 0.2], [0.8, 0.4]],
            [[0.3, 0.2], [0.6, 0.4]],
        ]
    )
    risk = compute_risk_coverage(np.array([0.0, 1.0, 1.0, 0.0]), np.array([0.1, 0.8, 0.7, 0.2]))

    assert 0.0 <= compute_segmentation_confidence(probabilities) <= 1.0
    assert compute_ensemble_disagreement(members) >= 0.0
    assert len(risk) == 3
    assert all(0.0 <= point.risk <= 1.0 for point in risk)


def test_final_test_cli_returns_nonzero() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/evaluate_calibration.py"),
            "--manifest",
            str(FINAL_TEST_FIXTURE),
            "--enforce-no-test-tuning",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "calibration_fit_partition" in result.stdout
