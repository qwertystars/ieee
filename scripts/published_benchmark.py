"""Published-baseline report assembly without external artifact substitution."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.benchmark_statistics import (
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_CONFIDENCE_LEVEL,
    DEFAULT_SUPERIORITY_MARGIN,
)
from scripts.published_baseline_contract import (
    EXPECTED_DATASETS,
    JsonObject,
    RegistryInputError,
    validate_published_baselines,
)


def _read(path: Path) -> JsonObject:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise RegistryInputError(f"{path}: expected JSON object")
    source = parsed.get("source")
    mutation = parsed.get("mutation")
    if isinstance(source, str) and mutation == "remove dataset xbd-damage":
        source_manifest = _read((path.parent / source).resolve())
        datasets = source_manifest.get("datasets")
        if isinstance(datasets, list):
            source_manifest["datasets"] = [
                dataset
                for dataset in datasets
                if not isinstance(dataset, dict) or dataset.get("dataset_id") != "xbd-damage"
            ]
        return source_manifest
    return parsed


def _metric_report(names: list[str], status: str) -> JsonObject:
    return {
        name: {
            "value": None,
            "confidence_interval": {"lower": None, "upper": None},
            "status": status,
            "source": "external_artifact_not_executed",
        }
        for name in names
    }


def _task_report(row: JsonObject) -> JsonObject:
    protocol = row.get("metric_protocol")
    protocol_object = protocol if isinstance(protocol, dict) else {}
    required = [
        value
        for value in protocol_object.get("required_metrics", [])
        if isinstance(value, str)
    ]
    per_class = [
        value
        for value in protocol_object.get("per_class_metrics", [])
        if isinstance(value, str)
    ]
    per_event = [
        value
        for value in protocol_object.get("per_event_metrics", [])
        if isinstance(value, str)
    ]
    metrics = _metric_report(required + per_class + per_event, "DEFERRED_EXTERNAL")
    return {
        "status": "DEFERRED_EXTERNAL",
        "baseline_id": row.get("baseline_id"),
        "primary_metric": protocol_object.get("primary_metric"),
        "metrics": metrics,
        "per_class": _metric_report(per_class, "DEFERRED_EXTERNAL"),
        "per_event": _metric_report(per_event, "DEFERRED_EXTERNAL"),
        "variants": row.get("variants", []),
        "superiority": {
            "status": "DEFERRED_EXTERNAL",
            "ci_lower_bound_rule": "candidate_lower_bound >= baseline + 0.02",
            "passed": False,
        },
        "external_limitation": row.get("pending_reason"),
    }


def build_published_report(
    manifest_path: Path,
    registry_path: Path,
    *,
    seeds: tuple[int, ...],
    require_published_baselines: bool,
    require_commands: bool,
) -> tuple[int, tuple[str, ...], JsonObject]:
    """Build a truthful benchmark summary and return exit code, findings, metrics."""
    validation = validate_published_baselines(
        registry_path,
        require_published_baselines=require_published_baselines,
        require_commands=require_commands,
    )
    registry = _read(registry_path)
    baseline_rows = [row for row in registry.get("baselines", []) if isinstance(row, dict)]
    manifest = _read(manifest_path)
    datasets = {
        dataset.get("dataset_id")
        for dataset in manifest.get("datasets", [])
        if isinstance(dataset, dict) and isinstance(dataset.get("dataset_id"), str)
    }
    findings = list(validation.findings)
    task_by_dataset = {dataset_id: task for task, dataset_id in EXPECTED_DATASETS.items()}
    if require_published_baselines:
        for task, dataset_id in EXPECTED_DATASETS.items():
            if task != "incident-nlp" and dataset_id not in datasets:
                findings.append(f"missing published baseline for benchmark dataset: {dataset_id}")
    for dataset_id in sorted(datasets):
        task = task_by_dataset.get(dataset_id)
        if task is None:
            continue
        if not any(row.get("task") == task for row in baseline_rows):
            findings.append(f"missing published baseline for benchmark dataset: {dataset_id}")
    reports = {
        str(row["task"]): _task_report(row)
        for row in baseline_rows
        if isinstance(row.get("task"), str)
    }
    policy = registry.get("policy")
    policy_object = policy if isinstance(policy, dict) else {}
    ablation_plan = [
        value for value in registry.get("ablation_plan", []) if isinstance(value, str)
    ]
    ablation_results = {
        name: {
            "status": "DEFERRED_EXTERNAL",
            "confidence_interval": {"lower": None, "upper": None},
            "holm_adjusted_p_value": None,
            "source": "external_artifact_not_executed",
        }
        for name in ablation_plan
    }
    report_metrics: JsonObject = {
        "published_registry": validation.metrics,
        "published_tasks": reports,
        "statistics": {
            "seeds": list(seeds),
            "seed_count": len(seeds),
            "bootstrap_unit": "incident",
            "bootstrap_resamples": policy_object.get("bootstrap_resamples", DEFAULT_BOOTSTRAP_RESAMPLES),
            "confidence_level": policy_object.get("confidence_level", DEFAULT_CONFIDENCE_LEVEL),
            "holm_correction": policy_object.get("holm_correction", "holm"),
            "holm_adjusted_p_values": {},
            "superiority_threshold": policy_object.get("superiority_threshold", DEFAULT_SUPERIORITY_MARGIN),
            "final_test_tuning": policy_object.get("final_test_tuning", False),
        },
        "modality_variants_covered": all(
            isinstance(report.get("variants"), list) and bool(report["variants"])
            for report in reports.values()
        ),
        "ablation_plan": ablation_plan,
        "ablation_results": ablation_results,
        "ablation_coverage": len(ablation_results) == 9,
        "real_external_metrics_published": False,
        "research_claim_status": "DEFERRED_EXTERNAL",
        "synthetic_fixture_claim": "validation-only",
    }
    return (1 if findings else 0), tuple(findings), report_metrics


__all__ = ["build_published_report"]
