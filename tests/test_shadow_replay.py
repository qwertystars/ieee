from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.run_shadow_replay import (
    ReplayRequest,
    evaluate_replay,
    load_baseline,
    load_fixture,
    load_prerequisites,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_shadow_replay.py"
BASELINE = ROOT / "config/shadow-baseline-v1.json"
HAPPY = ROOT / "tests/fixtures/shadow-incident.ndjson"
ACTUATION = ROOT / "tests/fixtures/shadow-actuation-attempt.ndjson"


def _request(fixture: Path) -> ReplayRequest:
    manifest, records = load_fixture(fixture)
    return ReplayRequest(
        baseline=load_baseline(BASELINE),
        manifest=manifest,
        records=records,
        prerequisites=load_prerequisites(ROOT / "evidence/sota/prerequisites.json"),
        min_incidents=100,
        min_window_days=30,
    )


def test_happy_fixture_passes_machine_gate_and_defers_external_claim() -> None:
    code, status, metrics = evaluate_replay(_request(HAPPY))

    assert code == 0
    assert status == "PASS"
    assert metrics["sample_count"] == 100
    assert metrics["window_days"] == 30
    assert metrics["false_alert_rate"] <= 0.05
    assert metrics["p95_end_to_end_latency_ms"] <= 2_000
    assert metrics["availability"] >= 0.999
    assert metrics["disagreement"]["attribution_rate"] == 1.0
    assert metrics["external_shadow_claim"] == "DEFERRED_EXTERNAL"


def test_actuation_attempt_fails_closed() -> None:
    code, status, metrics = evaluate_replay(_request(ACTUATION))

    assert code == 1
    assert status == "FAIL"
    assert metrics["actuation"]["attempts"] == 1
    assert any("actuation attempt" in finding for finding in metrics["findings"])


def test_exact_happy_cli_writes_normative_report(tmp_path: Path) -> None:
    report = tmp_path / "task-23-happy.json"
    result = subprocess.run(
        [
            "backend/.venv/bin/python",
            str(SCRIPT),
            "--fixture",
            str(HAPPY),
            "--baseline",
            str(BASELINE),
            "--min-incidents",
            "100",
            "--min-window-days",
            "30",
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
    assert payload["task_id"] == "23"
    assert payload["claim_class"] == "shadow_machine"
    assert payload["metrics"]["external_shadow_claim"] == "DEFERRED_EXTERNAL"


def test_exact_actuation_cli_exits_one() -> None:
    result = subprocess.run(
        [
            "backend/.venv/bin/python",
            str(SCRIPT),
            "--fixture",
            str(ACTUATION),
            "--baseline",
            str(BASELINE),
            "--assert-no-actuation",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout.startswith("status=FAIL")
