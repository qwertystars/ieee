from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TypeAlias

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_production_parity.sh"
MANIFEST = ROOT / "config" / "production-parity.json"
COMPOSE = ROOT / "docker-compose.production-parity.yml"
JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def run_parity(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def read_report(path: Path) -> dict[str, JsonValue]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_declares_finite_load_and_failure_budget() -> None:
    manifest: dict[str, JsonValue] = json.loads(MANIFEST.read_text(encoding="utf-8"))

    load_shape = manifest["load_shape"]
    thresholds = manifest["thresholds"]
    assert isinstance(load_shape, dict)
    assert isinstance(thresholds, dict)
    assert load_shape["operators"] == 50
    assert load_shape["ingest_events_per_second"] == 100
    assert manifest["duration_seconds"] == 3600
    assert thresholds["availability"] == 0.999
    assert thresholds["acknowledged_event_loss"] == 0.0
    assert thresholds["failure_budget"] == 0.001
    assert thresholds["latency_seconds"]["api_read"]["p50"] == 0.5
    assert thresholds["latency_seconds"]["api_read"]["p95"] == 0.5
    assert thresholds["latency_seconds"]["api_read"]["p99"] == 1.0


def test_parity_compose_has_two_instances_ordered_migration_and_no_latest() -> None:
    text = COMPOSE.read_text(encoding="utf-8")

    assert ":latest" not in text
    assert "backend_a:" in text
    assert "backend_b:" in text
    assert "migrate:" in text
    assert "service_completed_successfully" in text
    assert "/healthz/deep" in text
    assert "tls_bundle" in text
    assert "JWT_SECRET" in text


def test_migration_interrupt_fails_release_without_acknowledged_loss(tmp_path: Path) -> None:
    report = tmp_path / "migration-interrupt.json"
    result = run_parity(
        [
            "--mode",
            "fixture",
            "--scenario",
            "migration-interrupt-rollback",
            "--report",
            str(report),
        ]
    )

    assert result.returncode == 1
    evidence = read_report(report)
    assert evidence["status"] == "FAIL"
    metrics = evidence["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["release_status"] == "UNSAFE_RELEASE"
    reconciliation = metrics["reconciliation"]
    assert isinstance(reconciliation, dict)
    assert reconciliation["acknowledged_event_loss"] == 0
    assert reconciliation["hashes_identical"] is True


def test_acknowledged_loss_fixture_is_a_blocking_failure(tmp_path: Path) -> None:
    report = tmp_path / "ack-loss.json"
    result = run_parity(
        [
            "--mode",
            "fixture",
            "--scenario",
            "acknowledged-event-loss",
            "--report",
            str(report),
        ]
    )

    assert result.returncode == 1
    evidence = read_report(report)
    metrics = evidence["metrics"]
    assert isinstance(metrics, dict)
    reconciliation = metrics["reconciliation"]
    assert isinstance(reconciliation, dict)
    assert reconciliation["acknowledged_event_loss"] == 1


def test_happy_run_does_not_shrink_declared_duration(tmp_path: Path) -> None:
    report = tmp_path / "short-happy.json"
    result = run_parity(
        [
            "--instances",
            "2",
            "--operators",
            "50",
            "--ingest-rate",
            "100",
            "--duration",
            "60",
            "--report",
            str(report),
        ]
    )

    assert result.returncode == 1
    evidence = read_report(report)
    assert evidence["status"] == "FAIL"
    metrics = evidence["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["declared_duration_seconds"] == 3600
    assert metrics["requested_duration_seconds"] == 60


def test_exact_happy_command_defers_without_external_driver(tmp_path: Path) -> None:
    report = tmp_path / "happy.json"
    result = run_parity(
        [
            "--instances",
            "2",
            "--operators",
            "50",
            "--ingest-rate",
            "100",
            "--duration",
            "3600",
            "--report",
            str(report),
        ]
    )

    assert result.returncode == 2
    evidence = read_report(report)
    assert evidence["status"] == "DEFERRED_EXTERNAL"
    metrics = evidence["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["execution_mode"] == "external-driver-required"
    assert metrics["declared_duration_seconds"] == 3600


def test_adversarial_fixture_scenarios_are_named_and_executable(tmp_path: Path) -> None:
    scenarios = (
        "rolling-restart",
        "capacity",
        "readiness-liveness",
        "queue-saturation",
        "dependency-loss",
        "partial-instance-failure",
    )
    for scenario in scenarios:
        report = tmp_path / f"{scenario}.json"
        result = run_parity(
            ["--mode", "fixture", "--scenario", scenario, "--report", str(report)]
        )
        assert result.returncode == 0, result.stderr
        evidence = read_report(report)
        assert evidence["status"] == "PASS"


def test_rollback_fixture_is_an_unsafe_release(tmp_path: Path) -> None:
    report = tmp_path / "rollback.json"
    result = run_parity(
        ["--mode", "fixture", "--scenario", "rollback", "--report", str(report)]
    )

    assert result.returncode == 1
    evidence = read_report(report)
    assert evidence["status"] == "FAIL"
    metrics = evidence["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["release_status"] == "UNSAFE_RELEASE"
