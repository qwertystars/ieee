from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Final, TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
STATUS_SET: Final = {"NOT_ATTEMPTED", "AVAILABLE", "PASSED", "FAILED", "DEFERRED_EXTERNAL", "REVOKED"}
PREREQUISITE_FIELDS: Final = {"id", "owner", "authority", "status", "evidence_type", "evidence_hash", "hash_algorithm", "source_url", "recorded_at", "expires_at", "depends_on", "deferred_reason", "claim_classes"}
EVIDENCE_FIELDS: Final = {"kind", "consent_status", "IRB_status", "geographic_privacy_status", "validator_status", "key_custody_status"}
CLAIMS: Final = {"research", "production", "shadow", "field"}
FIELD_LABELS: Final = {"references": "References", "acceptance": "Acceptance criteria", "qa": "QA scenarios", "evidence": "Evidence", "commit": "Commit"}
ROW_RE: Final = re.compile(r"^- \[[ xX]\] (\d+)\.\s+(.+)$")
FINAL_RE: Final = re.compile(r"^\s*- \[[ xX]\] F(\d+)\.\s+(.+)$")


def expand(value: str) -> set[int]:
    if value.strip().lower() == "none":
        return set()
    result: set[int] = set()
    for part in value.split(","):
        piece = part.strip()
        bounds = piece.split("-", maxsplit=1)
        if len(bounds) == 1:
            result.add(int(bounds[0]))
        else:
            result.update(range(int(bounds[0]), int(bounds[1]) + 1))
    return result


def _fields(lines: list[str], start: int, end: int, label: str) -> str | None:
    for line in lines[start:end]:
        if label == "Evidence" and " Evidence " in f" {line}":
            return line.split("Evidence", maxsplit=1)[1].strip()
        for segment in line.split("|"):
            value = segment.strip()
            if value.startswith(label) and ":" in value:
                result = value.split(":", maxsplit=1)[1].strip()
                return result if result else None
    return None


def _prerequisites(path: Path) -> list[str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    records = value if isinstance(value, list) else value.get("prerequisites") if isinstance(value, dict) else None
    if not isinstance(records, list):
        raise TypeError("prerequisite register must be an array")
    errors: list[str] = []
    ids: list[str] = []
    for index, item in enumerate(records):
        if not isinstance(item, dict) or set(item) != PREREQUISITE_FIELDS:
            errors.append(f"prerequisites[{index}] must contain exactly 13 fields")
            continue
        identifier = item.get("id")
        status = item.get("status")
        evidence = item.get("evidence_type")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"prerequisites[{index}].id is required")
        else:
            ids.append(identifier)
        if status not in STATUS_SET:
            errors.append(f"prerequisites[{index}].status is unsupported")
        if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_FIELDS:
            errors.append(f"prerequisites[{index}].evidence_type must contain six fields")
        claims = item.get("claim_classes")
        if not isinstance(claims, list) or not claims or not all(isinstance(claim, str) and claim in CLAIMS for claim in claims):
            errors.append(f"prerequisites[{index}].claim_classes is invalid")
    if errors:
        raise ValueError("; ".join(errors))
    return ids


def verify(args: argparse.Namespace) -> list[str]:
    lines = args.plan.read_text(encoding="utf-8").splitlines()
    rows: dict[int, tuple[int, int]] = {}
    finals: set[int] = set()
    findings: list[str] = []
    for index, line in enumerate(lines):
        row = ROW_RE.match(line)
        if row is not None:
            number = int(row.group(1))
            if number in rows:
                findings.append(f"duplicate implementation row {number}")
            rows[number] = (index, len(lines))
            continue
        final = FINAL_RE.match(line)
        if final is not None:
            finals.add(int(final.group(1)))
    ordered = sorted(rows)
    if ordered != list(range(1, args.implementation_count + 1)):
        findings.append("implementation row count or numbering is invalid")
    if finals != set(range(1, args.final_count + 1)):
        findings.append("final verification wave count or numbering is invalid")
    for number, (start, _) in rows.items():
        next_starts = [position for candidate, (position, _) in rows.items() if candidate > number]
        end = min(next_starts, default=len(lines))
        rows[number] = (start, end)
        for field in args.check_fields.split(","):
            field_name = field.strip()
            if _fields(lines, start + 1, end, FIELD_LABELS.get(field_name, field_name)) is None:
                findings.append(f"todo {number} missing {field_name} field")
    matrix: dict[int, tuple[set[int], set[int]]] = {}
    in_matrix = False
    for line in lines:
        if line.startswith("| Todo | Depends on | Blocks |"):
            in_matrix = True
            continue
        if in_matrix and line.startswith("| ---"):
            continue
        if in_matrix and line.startswith("| "):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) == 4 and cells[0].isdigit():
                matrix[int(cells[0])] = (expand(cells[1]), expand(cells[2]))
        elif in_matrix and line and not line.startswith("|"):
            in_matrix = False
    if args.check_dependency_field_equality:
        for number, (start, end) in rows.items():
            blocked = _fields(lines, start + 1, end, "Blocked by")
            blocks = _fields(lines, start + 1, end, "Blocks")
            if number not in matrix or blocked is None or blocks is None:
                findings.append(f"todo {number} has no dependency matrix row")
                continue
            if expand(blocked) != matrix[number][0] or expand(blocks) != matrix[number][1]:
                findings.append(f"todo {number} dependency fields differ from matrix")
    if args.check_dag:
        graph = {number: matrix.get(number, (set(), set()))[0] for number in rows}
        visiting: set[int] = set()
        visited: set[int] = set()
        def visit(node: int) -> None:
            if node in visiting:
                findings.append(f"dependency cycle includes {node}")
                return
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph.get(node, set()):
                if dependency not in graph:
                    findings.append(f"todo {node} depends on unknown todo {dependency}")
                else:
                    visit(dependency)
            visiting.remove(node)
            visited.add(node)
        for node in graph:
            visit(node)
    if args.check_external_statuses:
        try:
            _prerequisites(args.prerequisites)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            findings.append(str(error))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--prerequisites", type=Path, default=Path("evidence/sota/prerequisites.json"))
    parser.add_argument("--implementation-count", type=int, required=True)
    parser.add_argument("--final-count", type=int, required=True)
    parser.add_argument("--check-fields", default="references,acceptance,qa,evidence,commit")
    parser.add_argument("--expand-range-dependencies", action="store_true")
    parser.add_argument("--check-dag", action="store_true")
    parser.add_argument("--check-dependency-field-equality", action="store_true")
    parser.add_argument("--check-external-statuses", action="store_true")
    args = parser.parse_args(argv)
    try:
        findings = verify(args)
    except (OSError, UnicodeError, TypeError, ValueError) as error:
        print(f"status=FAIL\nfinding={error}")
        return 1
    if findings:
        print("status=FAIL")
        for finding in findings:
            print(f"finding={finding}")
        return 1
    print("status=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
