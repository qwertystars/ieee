from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_plan_contract_accepts_exact_roadmap() -> None:
    result = subprocess.run(
        [
            "backend/.venv/bin/python",
            "scripts/verify_plan.py",
            "--plan",
            ".omo/plans/resqnet-sota-roadmap.md",
            "--implementation-count",
            "27",
            "--final-count",
            "4",
            "--check-fields",
            "references,acceptance,qa,evidence,commit",
            "--expand-range-dependencies",
            "--check-dag",
            "--check-dependency-field-equality",
            "--check-external-statuses",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "status=PASS"
