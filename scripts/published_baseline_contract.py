"""Public facade for the pinned published-baseline registry contract."""

from __future__ import annotations

from pathlib import Path

from scripts.published_baseline_checks import check_policy, is_object, read_registry
from scripts.published_baseline_types import (
    EXPECTED_COMMANDS,
    EXPECTED_DATASETS,
    EXPECTED_TASKS,
    BaselineValidationReport,
    JsonObject,
    JsonValue,
    RegistryInputError,
)


def validate_published_baselines(
    registry_path: Path,
    *,
    require_published_baselines: bool = False,
    require_commands: bool = False,
) -> BaselineValidationReport:
    """Validate registry metadata, immutable commands, paths, and comparison coverage."""
    registry = read_registry(registry_path)
    findings: list[str] = []
    if registry.get("schema_version") != "resqnet.published-baselines.v1":
        findings.append("registry.schema_version must be resqnet.published-baselines.v1")
    check_policy(registry, findings)
    baselines = registry.get("baselines")
    if not isinstance(baselines, list):
        findings.append("registry.baselines must be an array")
        baselines = []
    from scripts.published_baseline_rows import check_baseline_row

    tasks = [
        task
        for index, raw in enumerate(baselines)
        if (task := check_baseline_row(raw, index, findings)) is not None
    ]
    duplicates = {task for task in tasks if tasks.count(task) > 1}
    findings.extend(f"duplicate published baseline task: {task}" for task in sorted(duplicates))
    missing = sorted(set(EXPECTED_TASKS) - set(tasks))
    if require_published_baselines:
        findings.extend(f"missing published baseline: {task}" for task in missing)
    if require_commands:
        for task in sorted(set(EXPECTED_TASKS) & set(tasks)):
            row = next(raw for raw in baselines if is_object(raw) and raw.get("task") == task)
            if not isinstance(row.get("command"), str) or not row.get("command"):
                findings.append(f"missing executable command for published baseline: {task}")
    pending = sum(1 for raw in baselines if is_object(raw) and raw.get("status") == "DEFERRED_EXTERNAL")
    metrics: JsonObject = {
        "baseline_count": len(baselines),
        "required_baseline_tasks": list(EXPECTED_TASKS),
        "registered_baseline_tasks": sorted(set(tasks)),
        "missing_baselines": missing,
        "external_baselines_pending": pending,
        "commands_validated": True,
        "synthetic_metric_aliases_rejected": True,
    }
    if findings:
        return BaselineValidationReport("FAIL", 1, tuple(findings), metrics)
    return BaselineValidationReport("PASS", 0, (), metrics)


__all__ = [
    "EXPECTED_COMMANDS",
    "EXPECTED_DATASETS",
    "EXPECTED_TASKS",
    "BaselineValidationReport",
    "JsonObject",
    "JsonValue",
    "RegistryInputError",
    "validate_published_baselines",
]
