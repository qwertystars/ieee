"""Calibration manifest validation shared by the Task 16 CLI and tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.benchmark_contract_types import JsonObject, JsonValue
from scripts.calibration_contract_validation import (
    OUTPUT_TYPES,
    read_json,
    validate_model,
    validate_split_policy,
)


class CalibrationInputError(ValueError):
    """Raised when a calibration manifest cannot be interpreted."""


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    """Machine-readable calibration contract evaluation."""

    status: str
    exit_code: int
    findings: tuple[str, ...]
    metrics: JsonObject
    model_reports: dict[str, JsonValue]


def evaluate_calibration(manifest_path: Path, models_path: Path | None, enforce_no_test_tuning: bool) -> CalibrationReport:
    """Evaluate split policy and every supplied model calibration contract."""
    findings: list[str] = []
    try:
        validate_split_policy(manifest_path, findings, enforce_no_test_tuning)
    except (ValueError, TypeError) as error:
        raise CalibrationInputError(str(error)) from error
    model_reports: dict[str, JsonValue] = {}
    pending = 0
    if models_path is not None:
        try:
            models = read_json(models_path)
        except (ValueError, TypeError) as error:
            raise CalibrationInputError(str(error)) from error
        if not isinstance(models, list) or not models:
            findings.append("models manifest must be a non-empty array")
        else:
            for index, raw in enumerate(models):
                report = validate_model(raw, f"models[{index}]", findings)
                model_id = str(report.get("model_id", f"models[{index}]"))
                model_reports[model_id] = report
                if report.get("status") == "DEFERRED_EXTERNAL":
                    pending += 1
    metrics: JsonObject = {
        "model_count": len(model_reports),
        "external_calibration_pending": pending,
        "calibration_data_status": "DEFERRED_EXTERNAL" if pending else "AVAILABLE",
        "final_test_tuning_forbidden": True,
        "named_output_types": sorted(OUTPUT_TYPES),
        "all_safety_outputs_abstain_when_unavailable": all(report.get("release_gate") == "abstain" for report in model_reports.values()),
        "untouched_test_partition": "test",
    }
    if findings:
        return CalibrationReport("FAIL", 1, tuple(findings), metrics, model_reports)
    return CalibrationReport("PASS", 0, (), metrics, model_reports)


__all__ = ["CalibrationInputError", "CalibrationReport", "evaluate_calibration"]
