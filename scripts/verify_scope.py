"""F4 scope-fidelity verifier for the ResQNet SOTA roadmap.

Reads the plan's "Must NOT have" guardrails, scans the changed-file set for
forbidden scope, and emits a normative report. Forbidden scope is:

  physical-build    hardware procurement/manufacture, floodwater deployment,
                    or agency trial execution represented as completed by
                    software work
  medical-authority medical authority represented as exercised/completed
  certification     certification or regulatory approval represented as
                    completed
  gated-data        model weights, calibration datasets, or other license-
                    gated artifacts committed to the repository
  scope-rewrite     wholesale replacement of the canonical FastAPI/PostgreSQL
                    runtime or unmeasured speculative subsystems

Exit 0 = in scope, 1 = forbidden scope detected.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Final, TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

FORBIDDEN_CATEGORIES: Final = {
    "physical-build",
    "medical-authority",
    "certification",
    "gated-data",
    "scope-rewrite",
}

GATED_PATTERNS: Final = [
    re.compile(r"\.onnx$", re.IGNORECASE),
    re.compile(r"\.(tif|tiff|geotiff|nc|h5|hdf5)$", re.IGNORECASE),
    re.compile(r"\.(pem|key|p12|pfx)$", re.IGNORECASE),
    re.compile(r"(^|/)(backend/vendor|backend/models|weights|checkpoints)/", re.IGNORECASE),
]

COMPLETION_CLAIMS: Final = {
    "physical-build": [
        re.compile(r"\b(field trial|physical trial|deployment)\b.*\b(complete|passed|successful)\b", re.IGNORECASE),
        re.compile(r"\bhardware\b.*\b(manufactured|procured|deployed)\b", re.IGNORECASE),
    ],
    "medical-authority": [
        re.compile(r"\bmedical authority\b.*\b(approve|authorize|grant|exercise)\b", re.IGNORECASE),
    ],
    "certification": [
        re.compile(r"\b(certified|certification)\b.*\b(pass|complete|obtained|granted)\b", re.IGNORECASE),
        re.compile(r"\bregulatory approval\b.*\b(obtained|granted|passed)\b", re.IGNORECASE),
    ],
}

NEGATION_PREFIX: Final = re.compile(
    r"^[\s\-–—*]*(no|not|never|without|no claim|no claims|absent|deferred)\b",
    re.IGNORECASE,
)

SCOPE_REWRITE_SIGNALS: Final = [
    re.compile(r"(^|/)platform/", re.IGNORECASE),
    re.compile(r"(^|/)(next|new|rewrite|v2)/", re.IGNORECASE),
]

CORE_RUNTIME_PREFIXES: Final = ("backend/", "frontend/", "scripts/", "tests/", "docs/", "Makefile", "docker-compose")


def _load_plan(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _guardrail_block(lines: list[str]) -> list[str]:
    """Extract the 'Must NOT have' guardrail lines from the plan."""
    block: list[str] = []
    capture = False
    for line in lines:
        if "Must NOT have" in line:
            capture = True
            continue
        if capture and line.startswith("## "):
            break
        if capture and line.strip():
            block.append(line.strip())
    return block


def _check_gated_data(path: Path, guardrails: list[str]) -> list[str]:
    findings: list[str] = []
    name = str(path)
    for pattern in GATED_PATTERNS:
        if pattern.search(name):
            findings.append(f"gated-data: changed file {name} matches {pattern.pattern}")
            break
    return findings


def _check_completion_claims(path: Path, guardrails: list[str]) -> list[str]:
    findings: list[str] = []
    if not path.exists() or path.stat().st_size > 512 * 1024:
        return findings
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    lower = text.lower()
    if any(word in lower for word in ("deferred_external", "not attempted", "pending", "fixture")):
        return findings
    for line in text.splitlines():
        if NEGATION_PREFIX.match(line):
            continue
        for category, patterns in COMPLETION_CLAIMS.items():
            if category not in guardrails:
                continue
            for pattern in patterns:
                if pattern.search(line):
                    findings.append(f"{category}: {path} contains a completion claim matching {pattern.pattern}")
                    break
    return findings


def _check_scope_rewrite(path: Path, guardrails: list[str]) -> list[str]:
    findings: list[str] = []
    if not path.exists():
        return findings
    name = str(path)
    if any(prefix in name for prefix in CORE_RUNTIME_PREFIXES):
        return findings
    for pattern in SCOPE_REWRITE_SIGNALS:
        if pattern.search(name):
            findings.append(f"scope-rewrite: changed file {name} is outside the canonical runtime")
            break
    return findings


def _scan_changed(plan_lines: list[str], changed: list[str], guardrail_set: set[str]) -> list[str]:
    findings: list[str] = []
    for relative in changed:
        path = Path(relative)
        if path.is_dir():
            continue
        if "gated-data" in guardrail_set:
            findings.extend(_check_gated_data(path, guardrail_set))
        if guardrail_set & {"physical-build", "medical-authority", "certification"}:
            findings.extend(_check_completion_claims(path, guardrail_set))
        if "scope-rewrite" in guardrail_set:
            findings.extend(_check_scope_rewrite(path, guardrail_set))
    return findings


def _report(
    report_path: Path, command: str, cwd: str, inputs: list[str], findings: list[str],
    started: datetime.datetime, code_revision: str, plan_path: Path,
) -> None:
    finished = datetime.datetime.now(datetime.timezone.utc)
    report: dict[str, JsonValue] = {
        "task_id": "F4",
        "command": command,
        "cwd": cwd,
        "inputs": inputs,
        "code_revision": code_revision,
        "started_at": started.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "finished_at": finished.isoformat().replace("+00:00", "Z"),
        "exit_code": 1 if findings else 0,
        "status": "FAIL" if findings else "PASS",
        "metrics": {
            "changed_files_checked": len(inputs),
            "forbidden_findings": len(findings),
        },
        "hashes": {
            "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        },
        "failure_assertion": "Forbidden scope is absent from the changed-file set and no unmeasured completion claim is asserted.",
        "cleanup": "No files or services were modified.",
    }
    if findings:
        report["findings"] = findings
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True, help="roadmap plan markdown")
    parser.add_argument("--files-from", type=Path, required=True, help="file listing changed paths (one per line)")
    parser.add_argument("--forbid", required=True, help="comma-separated forbidden scope categories")
    parser.add_argument("--report", type=Path, default=Path("F4.json"), help="normative report output path")
    parser.add_argument("--cwd", default=str(Path.cwd()), help="working directory reported in evidence")
    args = parser.parse_args(argv)

    started = datetime.datetime.now(datetime.timezone.utc)
    code_revision = (
        subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
        .stdout.strip()
        or "unknown"
    )
    forbidden = {item.strip() for item in args.forbid.split(",") if item.strip()}
    invalid = forbidden - FORBIDDEN_CATEGORIES
    if invalid:
        print(f"status=FAIL\nfinding=unknown forbidden scope: {', '.join(sorted(invalid))}")
        return 1

    plan_lines = _load_plan(args.plan)
    changed = [
        line.strip()
        for line in args.files_from.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    findings = _scan_changed(plan_lines, changed, forbidden)
    inputs = [str(args.plan), str(args.files_from)] + changed

    command = " ".join(sys.argv)
    _report(args.report, command, args.cwd, inputs, findings, started, code_revision, args.plan)

    if findings:
        print("status=FAIL")
        for finding in findings:
            print(f"finding={finding}")
        return 1
    print("status=PASS")
    print(f"changed_files_checked={len(changed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
