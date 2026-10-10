"""Verify the committed production configuration contract without printing secrets."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Final, TypeAlias

ROOT: Final = Path(__file__).resolve().parents[1]
JSONValue: TypeAlias = (
    str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
)


def _resolve_path(value: str) -> Path:
    """Resolve a path from the caller directory or repository root."""
    candidate = Path(value)
    if candidate.is_file():
        return candidate
    return ROOT / candidate


def _read_env(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE lines while ignoring comments."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def _service_blocks(text: str) -> dict[str, str]:
    """Extract top-level Compose service blocks without a YAML dependency."""
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = re.match(r"^  ([a-zA-Z0-9_-]+):\s*$", line)
        if match:
            current = match.group(1)
            blocks[current] = [line]
            continue
        if current is not None:
            blocks[current].append(line)
    return {name: "\n".join(lines) for name, lines in blocks.items()}


def _settings_violations(values: dict[str, str]) -> list[str]:
    """Load Settings in isolation and return only named validation failures."""
    environment = values.get("ENVIRONMENT", "production")
    if environment != "production":
        return ["ENVIRONMENT"]
    original = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update(values)
        sys.path.insert(0, str(ROOT / "backend"))
        from app.config import Settings

        Settings(_env_file=None, **values)
    except ValueError as error:
        match = re.search(r"unsafe production configuration: ([A-Z0-9_, ]+)", str(error))
        return match.group(1).strip().split(", ") if match else ["SETTINGS_VALIDATION"]
    finally:
        for key, previous in original.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous
    return []


def _compose_violations(matrix: dict[str, JSONValue]) -> list[str]:
    """Check the production Compose surface for forbidden deployment shapes."""
    compose = matrix["compose"]
    if not isinstance(compose, dict):
        return ["MATRIX_COMPOSE"]
    compose_file = compose.get("file")
    forbidden_text = compose.get("forbidden_text")
    private_services = compose.get("private_services")
    public_services = compose.get("public_services")
    if not isinstance(compose_file, str) or not isinstance(forbidden_text, list):
        return ["MATRIX_COMPOSE"]
    if not isinstance(private_services, list) or not isinstance(public_services, list):
        return ["MATRIX_COMPOSE"]
    text = (ROOT / compose_file).read_text(encoding="utf-8")
    violations = [f"compose:{item}" for item in forbidden_text if isinstance(item, str) and item in text]
    if compose.get("source_mounts_must_not_exist") and re.search(
        r"^\s*-\s+\./", text, flags=re.MULTILINE
    ):
        violations.append("compose:source_mount")
    required_environment = compose.get("required_environment")
    if isinstance(required_environment, list):
        for name in required_environment:
            if isinstance(name, str) and f"${{{name}:?" not in text:
                violations.append(f"compose:required_environment:{name}")
    blocks = _service_blocks(text)
    for service in private_services:
        if isinstance(service, str) and "\n    ports:" in blocks.get(service, ""):
            violations.append(f"compose:private_port:{service}")
    for service in public_services:
        if isinstance(service, str) and service not in blocks:
            violations.append(f"compose:missing_public_service:{service}")
    return violations


def main() -> int:
    """Run the production matrix and return its CI exit contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--env-file")
    args = parser.parse_args()
    matrix_path = _resolve_path(args.matrix)
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    if args.environment != matrix.get("environment"):
        print("violation: ENVIRONMENT", file=sys.stderr)
        return 1
    safe_environment = matrix.get("safe_environment")
    if not isinstance(safe_environment, dict):
        print("violation: MATRIX_SAFE_ENVIRONMENT", file=sys.stderr)
        return 1
    values = {str(key): str(value) for key, value in safe_environment.items()}
    values["ENVIRONMENT"] = args.environment
    if args.env_file:
        values.update(_read_env(_resolve_path(args.env_file)))
        values["ENVIRONMENT"] = args.environment
    for key in tuple(values):
        if key in os.environ:
            values[key] = os.environ[key]
    values["ENVIRONMENT"] = args.environment

    violations = _settings_violations(values) + _compose_violations(matrix)
    if violations:
        for violation in dict.fromkeys(violations):
            print(f"violation: {violation}", file=sys.stderr)
        return int(matrix["verifier"]["failure_exit_code"])
    print("PASS: production configuration matrix")
    return int(matrix["startup"]["safe_exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
