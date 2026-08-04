#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run: uv run scripts/replay_event_log.py --fixture backend/tests/fixtures/replay-v1.ndjson
# 3. Or use the backend environment:
#      cd backend && .venv/bin/python ../scripts/replay_event_log.py --help
# ──────────────────

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Final

BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.fusion.replay import (
    ReplayConfig,
    ReplayOutput,
    event_from_mapping,
    replay_events,
)
from app.lib.audit import JSONValue
from app.models.events import RawEvent


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay canonical ResQNet events deterministically")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--seeds", default="0")
    parser.add_argument("--float-tolerance", type=float, default=1e-6)
    parser.add_argument("--expect-identical-decision-hashes", action="store_true")
    parser.add_argument("--expect-declared-merge-or-abstain", action="store_true")
    return parser


def _load_events(path: Path) -> tuple[RawEvent, ...]:
    events: list[RawEvent] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"fixture line {line_number} is not JSON") from exc
        if not isinstance(record, dict):
            raise TypeError(f"fixture line {line_number} must be a JSON object")
        events.append(event_from_mapping(record))
    return tuple(events)


def _numbers_equal(left: JSONValue, right: JSONValue, tolerance: float) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), abs_tol=tolerance, rel_tol=0.0)
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _numbers_equal(left[key], right[key], tolerance) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _numbers_equal(a, b, tolerance) for a, b in zip(left, right, strict=True)
        )
    return left == right


def _outputs_equal(first: tuple[ReplayOutput, ...], second: tuple[ReplayOutput, ...], tolerance: float) -> bool:
    if len(first) != len(second):
        return False
    return all(
        a.output_type == b.output_type
        and a.output_key == b.output_key
        and a.decision_hash == b.decision_hash
        and _numbers_equal(a.payload, b.payload, tolerance)
        for a, b in zip(first, second, strict=True)
    )


def main() -> int:
    args = _parser().parse_args()
    seeds = tuple(int(seed.strip()) for seed in args.seeds.split(",") if seed.strip())
    if not seeds:
        raise ValueError("--seeds must contain at least one integer")
    events = _load_events(args.fixture)
    config = ReplayConfig(float_tolerance=args.float_tolerance)
    results = tuple(replay_events(events, seed=seed, config=config) for seed in seeds)
    first = results[0]
    if first.errors:
        return 1
    identical_hashes = all(result.decision_hash == first.decision_hash for result in results)
    equivalent_outputs = all(
        _outputs_equal(first.outputs, result.outputs, args.float_tolerance)
        for result in results[1:]
    )
    conflicts = [output for output in first.outputs if output.output_type == "conflict"]
    declared_conflicts = bool(conflicts) and all(
        output.payload.get("resolution") in {"abstain", "declared_merge"}
        for output in conflicts
    )
    if args.expect_identical_decision_hashes and not identical_hashes:
        return 1
    if args.expect_identical_decision_hashes and not equivalent_outputs:
        return 1
    if args.expect_declared_merge_or_abstain and not declared_conflicts:
        return 1
    print(json.dumps({
        "status": "PASS",
        "fixture": str(args.fixture),
        "seed_count": len(seeds),
        "input_hash": first.input_hash,
        "decision_hash": first.decision_hash,
        "output_hash": first.output_hash,
        "lineage_hash": first.lineage.lineage_hash,
        "identical_decision_hashes": identical_hashes,
        "float_equivalent": equivalent_outputs,
        "declared_conflicts": declared_conflicts,
        "error_count": len(first.errors),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
