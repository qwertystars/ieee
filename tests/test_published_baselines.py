from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.benchmark_statistics import (
    SeedMetric,
    holm_correction,
    pair_incident_metrics,
    paired_incident_bootstrap,
    superiority_gate,
)
from scripts.published_baseline_contract import JsonValue, validate_published_baselines

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/published-baselines-v1.json"
MISSING_BASELINE = ROOT / "tests/fixtures/benchmark-missing-baseline.json"


def _load_registry() -> dict[str, JsonValue]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _write_registry(tmp_path: Path, registry: dict[str, JsonValue]) -> Path:
    path = tmp_path / "published-baselines.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    return path


def test_complete_registry_has_required_pins_and_variants() -> None:
    report = validate_published_baselines(REGISTRY, require_published_baselines=True, require_commands=True)

    assert report.status == "PASS"
    assert report.exit_code == 0
    assert report.metrics["external_baselines_pending"] == 4
    assert report.metrics["registered_baseline_tasks"] == ["floodnet", "incident-nlp", "sen1floods11", "xview2"]


def test_missing_command_is_named(tmp_path: Path) -> None:
    registry = _load_registry()
    baselines = registry["baselines"]
    assert isinstance(baselines, list) and isinstance(baselines[0], dict)
    baselines[0].pop("command")

    report = validate_published_baselines(_write_registry(tmp_path, registry), require_commands=True)

    assert report.status == "FAIL"
    assert any("command" in finding for finding in report.findings)


def test_unresolved_command_path_is_named(tmp_path: Path) -> None:
    registry = _load_registry()
    baselines = registry["baselines"]
    assert isinstance(baselines, list) and isinstance(baselines[0], dict)
    baselines[0]["command"] = "python scripts/run_baseline.py --config benchmarks/baselines/missing.yaml"
    baselines[0]["config_path"] = "benchmarks/baselines/missing.yaml"

    report = validate_published_baselines(_write_registry(tmp_path, registry))

    assert report.status == "FAIL"
    assert any("unresolved" in finding for finding in report.findings)


def test_unpinned_available_artifact_is_rejected(tmp_path: Path) -> None:
    registry = _load_registry()
    baselines = registry["baselines"]
    assert isinstance(baselines, list) and isinstance(baselines[0], dict)
    artifact = baselines[0]["artifact"]
    assert isinstance(artifact, dict)
    baselines[0]["status"] = "AVAILABLE"
    artifact["available"] = True
    artifact["sha256"] = None

    report = validate_published_baselines(_write_registry(tmp_path, registry))

    assert report.status == "FAIL"
    assert any("SHA-256" in finding for finding in report.findings)


def test_synthetic_metric_alias_is_rejected(tmp_path: Path) -> None:
    registry = _load_registry()
    baselines = registry["baselines"]
    assert isinstance(baselines, list) and isinstance(baselines[0], dict)
    protocol = baselines[0]["metric_protocol"]
    assert isinstance(protocol, dict)
    protocol["required_metrics"] = ["synthetic_miou"]

    report = validate_published_baselines(_write_registry(tmp_path, registry))

    assert report.status == "FAIL"
    assert any("synthetic metric alias" in finding for finding in report.findings)


def test_paired_bootstrap_holm_and_superiority_are_deterministic() -> None:
    candidate = [SeedMetric(incident, seed, 0.80 + seed / 1000) for incident in ("a", "b") for seed in range(1, 6)]
    baseline = [SeedMetric(incident, seed, 0.70) for incident in ("a", "b") for seed in range(1, 6)]

    paired = pair_incident_metrics(candidate, baseline)
    first = paired_incident_bootstrap(paired, resamples=100, random_seed=7)
    second = paired_incident_bootstrap(paired, resamples=100, random_seed=7)

    assert first == second
    assert first.resamples == 100
    assert first.lower_bound > 0.02
    assert holm_correction({"a": 0.01, "b": 0.02}) == {"a": 0.02, "b": 0.02}
    assert superiority_gate(0.73, 0.70) is True
    assert superiority_gate(0.719, 0.70) is False


def test_exact_missing_baseline_command_fails_with_named_finding() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_benchmark.py"),
            "--manifest",
            str(MISSING_BASELINE),
            "--require-published-baselines",
            "--require-commands",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "missing published baseline" in result.stdout
