"""Row-level published-baseline validation kept separate from registry policy."""

from __future__ import annotations

from scripts.published_baseline_checks import (
    check_artifact,
    check_command,
    check_license,
    check_metrics,
    check_repository,
    check_variants,
    nested_object,
    text,
    url,
)
from scripts.published_baseline_contract import (
    EXPECTED_DATASETS,
    EXPECTED_TASKS,
    JsonValue,
)


def check_baseline_row(raw: JsonValue, index: int, findings: list[str]) -> str | None:
    """Validate one row and return its task identifier."""
    path = f"baselines[{index}]"
    if not isinstance(raw, dict):
        findings.append(f"{path} must be an object")
        return None
    task = text(raw, "task", path, findings)
    if task not in EXPECTED_TASKS:
        findings.append(f"{path}.task is not one of the required benchmark tasks")
        return task
    if raw.get("status") not in {"AVAILABLE", "DEFERRED_EXTERNAL"}:
        findings.append(f"{path}.status must be AVAILABLE or DEFERRED_EXTERNAL")
    text(raw, "baseline_id", path, findings)
    if raw.get("dataset_id") != EXPECTED_DATASETS[task]:
        findings.append(f"{path}.dataset_id is not the pinned dataset for {task}")
    url(raw, "paper_url", path, findings)
    text(raw, "paper_title", path, findings)
    check_repository(raw, task, path, findings)
    check_license(raw, path, findings)
    check_artifact(raw, path, findings)
    check_command(raw, task, path, findings)
    check_metrics(raw, task, path, findings)
    for field in ("preprocessing", "hyperparameters", "hardware"):
        nested_object(raw, field, path, findings)
    split_hashes = nested_object(raw, "split_hashes", path, findings)
    if split_hashes is not None:
        for split in ("train", "calibration", "test"):
            digest = split_hashes.get(split)
            if task == "incident-nlp" and raw.get("status") == "DEFERRED_EXTERNAL" and digest is None:
                continue
            if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                findings.append(f"{path}.split_hashes.{split} must be an immutable SHA-256 digest")
    check_variants(raw, path, findings)
    pending_reason = raw.get("pending_reason")
    if raw.get("status") == "DEFERRED_EXTERNAL" and (not isinstance(pending_reason, str) or not pending_reason):
        findings.append(f"{path}.pending_reason is required for DEFERRED_EXTERNAL")
    return task
