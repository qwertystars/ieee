#!/usr/bin/env python3
"""Validate and, when available, dispatch one pinned baseline configuration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.published_baseline_contract import (
    EXPECTED_COMMANDS,
    JsonObject,
    RegistryInputError,
)


def _read_config(path: Path) -> JsonObject:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryInputError(f"{path}: invalid baseline config: {error}") from error
    if not isinstance(parsed, dict):
        raise RegistryInputError(f"{path}: baseline config must be a JSON object")
    return parsed


def validate_config(path: Path) -> tuple[str, JsonObject]:
    """Validate a pinned config and return its status plus machine metadata."""
    config = _read_config(path)
    findings: list[str] = []
    if config.get("schema_version") != "resqnet.published-baseline-config.v1":
        findings.append("schema_version must be resqnet.published-baseline-config.v1")
    task = config.get("task")
    if not isinstance(task, str) or task not in EXPECTED_COMMANDS:
        findings.append("task must identify a registered published baseline")
    command = config.get("command")
    if isinstance(task, str) and command != EXPECTED_COMMANDS.get(task):
        findings.append("command does not match the immutable registry command")
    if not isinstance(command, str) or not command:
        findings.append("command is required")
    artifact_available = config.get("artifact_available")
    if not isinstance(artifact_available, bool):
        findings.append("artifact_available must be boolean")
    status = config.get("status")
    if status not in {"AVAILABLE", "DEFERRED_EXTERNAL"}:
        findings.append("status must be AVAILABLE or DEFERRED_EXTERNAL")
    if status == "DEFERRED_EXTERNAL" and not isinstance(config.get("reason"), str):
        findings.append("reason is required for DEFERRED_EXTERNAL")
    if findings:
        raise RegistryInputError("; ".join(findings))
    return str(status), config


def main(argv: list[str] | None = None) -> int:
    """Validate a baseline config without downloading or substituting artifacts."""
    parser = argparse.ArgumentParser(description="Validate a pinned ResQNet baseline command")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        status, config = validate_config(args.config)
    except RegistryInputError as error:
        print(f"status=FAIL\nfinding={error}")
        return 1
    if status == "DEFERRED_EXTERNAL":
        print("status=DEFERRED_EXTERNAL")
        print(f"task={config['task']}")
        print(f"reason={config['reason']}")
        print("metrics_not_published=true")
        return 2
    print("status=FAIL")
    print("finding=execution adapter is not available in the offline workspace")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
