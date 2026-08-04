from __future__ import annotations

import json
from pathlib import Path

from scripts.benchmark_contract import validate_benchmark
from scripts.benchmark_contract_types import JsonObject, JsonValue

REQUIRED_METRIC_FIELDS = {
    "reliability", "ece", "brier", "nll", "segmentation_confidence",
    "ensemble_disagreement", "conformal_coverage", "conformal_interval_width",
    "risk_coverage", "subgroup_ece", "hazard_ece", "subgroup_coverage", "hazard_coverage",
}
THRESHOLD_FIELDS = (
    "confidence_min", "disagreement_max", "ece_max", "brier_max", "nll_max",
    "coverage_min", "coverage_max", "risk_max", "shift_ece_delta", "shift_coverage_delta",
)
OUTPUT_TYPES = {
    "sar_segmentation_confidence", "damage_probability", "nlp_probability",
    "ensemble_disagreement", "conformal_interval", "risk_coverage",
}


def read_json(path: Path) -> JsonValue:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: invalid JSON: {error}") from error


def check_test_tuning(value: JsonValue, path: str, findings: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in {"calibration_fit_partition", "threshold_fit_partition", "tuning_split"} and child == "test":
                findings.append(f"{child_path} may not be test")
            if key == "test_tuning" and child is True:
                findings.append(f"{child_path} must be false")
            check_test_tuning(child, child_path, findings)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            check_test_tuning(child, f"{path}[{index}]", findings)


def validate_split_policy(manifest_path: Path, findings: list[str], enforce: bool) -> JsonObject:
    parsed = read_json(manifest_path)
    if not isinstance(parsed, dict):
        raise TypeError(f"{manifest_path}: top-level value must be an object")
    if enforce:
        check_test_tuning(parsed, "$", findings)
    if parsed.get("schema_version") == "resqnet.benchmark-manifest.v1":
        benchmark = validate_benchmark(manifest_path, check_leakage=True)
        findings.extend(benchmark.findings)
        if benchmark.metrics.get("final_test_hash_verified") is not True:
            findings.append("final test hash is not verified")
        return parsed
    if parsed.get("schema_version") != "resqnet.calibration-evaluation.v1":
        findings.append("schema_version must identify a benchmark or calibration evaluation manifest")
        return parsed
    if enforce and parsed.get("calibration_fit_partition") == "test":
        findings.append("calibration_fit_partition may not be test")
    if parsed.get("evaluation_partition") != "test":
        findings.append("evaluation_partition must be test")
    if parsed.get("final_test_hash_verified") is not True:
        findings.append("final_test_hash_verified must be true before evaluation")
    return parsed


def metric_threshold_finding(name: str, value: JsonValue, thresholds: JsonObject) -> str | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return f"observed metric {name} must be numeric"
    numeric = float(value)
    ece_max = thresholds.get("ece_max")
    brier_max = thresholds.get("brier_max")
    nll_max = thresholds.get("nll_max")
    coverage_min = thresholds.get("coverage_min")
    coverage_max = thresholds.get("coverage_max")
    risk_max = thresholds.get("risk_max")
    if name in {"ece", "subgroup_ece", "hazard_ece"} and isinstance(ece_max, (int, float)) and numeric > float(ece_max):
        return f"{name}={numeric} exceeds ece_max"
    if name == "brier" and isinstance(brier_max, (int, float)) and numeric > float(brier_max):
        return f"brier={numeric} exceeds brier_max"
    if name == "nll" and isinstance(nll_max, (int, float)) and numeric > float(nll_max):
        return f"nll={numeric} exceeds nll_max"
    if name in {"conformal_coverage", "subgroup_coverage", "hazard_coverage"}:
        if isinstance(coverage_min, (int, float)) and numeric < float(coverage_min):
            return f"{name}={numeric} is below coverage_min"
        if isinstance(coverage_max, (int, float)) and numeric > float(coverage_max):
            return f"{name}={numeric} exceeds coverage_max"
    if name in {"risk_coverage", "subgroup_risk_coverage", "hazard_risk_coverage"} and isinstance(risk_max, (int, float)) and numeric > float(risk_max):
        return f"{name}={numeric} exceeds risk_max"
    return None


def validate_model(raw: JsonValue, path: str, findings: list[str]) -> JsonObject:
    if not isinstance(raw, dict):
        findings.append(f"{path} must be an object")
        return {}
    model_id = raw.get("model_id")
    if not isinstance(model_id, str) or not model_id:
        findings.append(f"{path}.model_id must be non-empty")
        model_id = path
    calibration = raw.get("calibration")
    contract = raw.get("contract")
    if not isinstance(contract, dict):
        findings.append(f"{path}.contract must be an object")
        contract = {}
    if not isinstance(calibration, dict):
        findings.append(f"{path}.calibration must be an explicit object, not null")
        calibration = {}
    status = calibration.get("status")
    if status not in {"available", "DEFERRED_EXTERNAL"}:
        findings.append(f"{path}.calibration.status must be available or DEFERRED_EXTERNAL")
    output_type = calibration.get("output_type")
    method = calibration.get("method")
    if not isinstance(output_type, str) or not output_type:
        findings.append(f"{path}.calibration.output_type is required")
    if not isinstance(method, str) or not method:
        findings.append(f"{path}.calibration.method is required")
    artifact_claim = raw.get("artifact")
    artifact_filename = artifact_claim.get("filename", "") if isinstance(artifact_claim, dict) else ""
    if isinstance(method, str) and "linear" in method.lower() and isinstance(artifact_filename, str) and artifact_filename.endswith(".onnx"):
        findings.append(f"{path}.calibration may not call a linear proxy an ONNX calibration")
    if isinstance(output_type, str) and output_type not in OUTPUT_TYPES:
        findings.append(f"{path}.calibration.output_type is not a named output contract")
    output_types = calibration.get("output_types")
    if not isinstance(output_types, list) or not output_types:
        findings.append(f"{path}.calibration.output_types must be non-empty")
    elif isinstance(output_type, str) and output_type not in output_types:
        findings.append(f"{path}.calibration.output_types must include output_type")
    for field in ("confidence_level", "minimum_samples", "subgroup_minimum_samples", "hazard_minimum_samples", "recalibration_cadence_days", "shift_trigger"):
        if field not in calibration:
            findings.append(f"{path}.calibration.{field} is required")
    for field in ("minimum_samples", "subgroup_minimum_samples", "hazard_minimum_samples"):
        value = calibration.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 200:
            findings.append(f"{path}.calibration.{field} must be at least 200")
    if calibration.get("test_tuning_forbidden") is not True:
        findings.append(f"{path}.calibration.test_tuning_forbidden must be true")
    thresholds = calibration.get("thresholds")
    if not isinstance(thresholds, dict):
        findings.append(f"{path}.calibration.thresholds must be an object")
        thresholds = {}
    for field in THRESHOLD_FIELDS:
        value = thresholds.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            findings.append(f"{path}.calibration.thresholds.{field} must be numeric")
    metrics = calibration.get("metrics")
    if not isinstance(metrics, dict):
        findings.append(f"{path}.calibration.metrics must be an object")
        metrics = {}
    required_metrics = metrics.get("required")
    if not isinstance(required_metrics, list) or not required_metrics:
        findings.append(f"{path}.calibration.metrics.required must be non-empty")
        required_metrics = []
    unknown = [metric for metric in required_metrics if metric not in REQUIRED_METRIC_FIELDS]
    findings.extend(f"{path}.calibration.metrics.required has unknown metric {metric}" for metric in unknown)
    split = calibration.get("split")
    if not isinstance(split, dict):
        findings.append(f"{path}.calibration.split must be an object")
        split = {}
    if split.get("calibration_partition") != "calibration":
        findings.append(f"{path}.calibration.split.calibration_partition must be calibration")
    if split.get("evaluation_partition") != "test":
        findings.append(f"{path}.calibration.split.evaluation_partition must be test")
    if split.get("final_test_tuning") is not False:
        findings.append(f"{path}.calibration.split.final_test_tuning must be false")
    artifact = calibration.get("artifact")
    if not isinstance(artifact, dict):
        findings.append(f"{path}.calibration.artifact must be an object")
        artifact = {}
    if status == "available":
        for field in ("version", "sha256", "reference"):
            if not isinstance(artifact.get(field), str) or not artifact[field]:
                findings.append(f"{path}.calibration.artifact.{field} is required when available")
        observed = metrics.get("observed")
        if not isinstance(observed, dict):
            findings.append(f"{path}.calibration.metrics.observed is required when available")
        else:
            for metric in required_metrics:
                if metric not in observed:
                    findings.append(f"{path}.calibration.metrics.observed is missing {metric}")
                else:
                    finding = metric_threshold_finding(metric, observed[metric], thresholds)
                    if finding:
                        findings.append(f"{path}: {finding}")
    else:
        if not isinstance(calibration.get("deferred_reason"), str) or not calibration["deferred_reason"]:
            findings.append(f"{path}.calibration.deferred_reason is required when unavailable")
        if artifact.get("status") != "unavailable" or artifact.get("sha256") is not None:
            findings.append(f"{path}.calibration.artifact must explicitly be unavailable")
        if contract.get("calibration_version") != "unavailable":
            findings.append(f"{path}.contract.calibration_version must be unavailable")
        abstention = calibration.get("abstention")
        if not isinstance(abstention, dict) or abstention.get("status") != "abstain":
            findings.append(f"{path}.calibration.abstention.status must be abstain")
    observed_metrics = metrics.get("observed")
    observed_coverage = observed_metrics.get("conformal_coverage") if isinstance(observed_metrics, dict) else None
    return {
        "model_id": model_id, "output_type": output_type, "status": status, "method": method,
        "required_metrics": required_metrics, "thresholds": thresholds,
        "release_gate": "available" if status == "available" else "abstain",
        "nominal_coverage": calibration.get("confidence_level"),
        "observed_coverage": observed_coverage, "observed_metrics": observed_metrics,
        "abstention": calibration.get("abstention"), "external_limitation": calibration.get("deferred_reason"),
    }
