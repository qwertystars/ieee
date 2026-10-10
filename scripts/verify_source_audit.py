"""Run deterministic source checks for the files selected by a git range."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files-from", required=True)
    parser.add_argument("--checks", required=True)
    return parser


def _files(path: Path) -> list[Path]:
    return [Path(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _audit_file(path: Path, checks: set[str]) -> list[str]:
    text = path.read_text(encoding="utf-8")
    findings: list[str] = []
    if path.suffix == ".py":
        try:
            ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            findings.append(f"{path}: syntax error: {exc.msg}")
    if "security" in checks and "allow_origins=[\"*\"]" in text.replace(" ", ""):
        findings.append(f"{path}: wildcard CORS is forbidden")
    if "durability" in checks and "asyncio.create_task" in text:
        findings.append(f"{path}: fire-and-forget asyncio task is forbidden")
    if "contracts" in checks and ("# type: ignore" in text or "# pyright: ignore" in text):
        findings.append(f"{path}: type suppression directive is forbidden")
    return findings


def main() -> int:
    args = _parser().parse_args()
    checks = {check.strip() for check in args.checks.split(",") if check.strip()}
    unknown = checks - {"security", "durability", "contracts"}
    if unknown:
        print(f"unknown source-audit checks: {sorted(unknown)}", file=sys.stderr)
        return 1
    selected = _files(Path(args.files_from))
    if not selected:
        print("source audit PASS: git diff scope contains no files")
        return 0
    findings: list[str] = []
    for path in selected:
        if not path.is_file():
            findings.append(f"{path}: selected source file does not exist")
            continue
        findings.extend(_audit_file(path, checks))
    if findings:
        print("\n".join(findings), file=sys.stderr)
        return 1
    print(f"source audit PASS: checked {len(selected)} files with {sorted(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
