"""Record executable evidence for the unified dashboard's local contracts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evidence" / "unified-dashboard"


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    commands = [
        ("typecheck", ROOT / "frontend", ["npm", "run", "typecheck"]),
        ("lint", ROOT / "frontend", ["npm", "run", "lint"]),
        ("frontend-tests", ROOT / "frontend", ["npm", "test"]),
        ("build", ROOT / "frontend", ["npm", "run", "build"]),
        ("field-service-tests", ROOT / "modules", [str(ROOT / "backend/.venv/bin/python"),
            "-m", "pytest", "tests/test_dashboard_services.py", "-q"]),
        ("live-api", ROOT, [str(ROOT / "backend/.venv/bin/python"), "scripts/check_dashboard_live.py"]),
        ("live-browser", ROOT / "frontend", ["npm", "run", "test:dashboard-live"]),
        ("cache-migration", ROOT / "frontend", ["node", "scripts/check-cache-migration.cjs"]),
        ("browser", ROOT / "frontend", ["npm", "run", "test:dashboard-browser"]),
    ]
    checks = []
    for name, directory, command in commands:
        try:
            result = subprocess.run(command, cwd=directory, capture_output=True,
                                    text=True, timeout=90, env=os.environ.copy())
            log = result.stdout + result.stderr
            code = result.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            log, code = str(exc), 1
        path = OUTPUT / f"{name}.log"
        path.write_text(log)
        checks.append({"name": name, "command": command,
            "cwd": str(directory.relative_to(ROOT)), "exit_code": code,
            "log": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        print(f"{name}: exit {code}", flush=True)

    sources = [*ROOT.glob("frontend/src/**/*.ts"), *ROOT.glob("frontend/src/**/*.tsx"),
        ROOT / "frontend/public/sw.js", ROOT / "frontend/scripts/check-dashboard.cjs", ROOT / "frontend/scripts/check-dashboard-live.cjs", ROOT / "frontend/scripts/check-cache-migration.cjs",
        ROOT / "scripts/check_dashboard_live.py", ROOT / "scripts/start_dashboard_local.py",
        ROOT / "backend/app/config.py", ROOT / "backend/app/api/routes/simulator.py",
        *ROOT.glob("backend/app/simulator/*.py"), ROOT / "modules/ble_localization/main.py",
        ROOT / "modules/ble_localization/cli.py", ROOT / "modules/route_engine/thermal_server.py",
        ROOT / "modules/tests/test_dashboard_services.py",
        ROOT / "modules/mesh_app/lib/services/api_service.dart"]
    report = {"created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Real local API/database reads, simulator persistence/controls, all eight browser workspaces, mobile layouts, field API contracts and mocked outage/role handling",
        "status": "PASS" if all(check["exit_code"] == 0 for check in checks) else "FAIL",
        "checks": checks,
        "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sorted(sources)},
        "limitations": ["Development PostgreSQL 18 differs from production PostgreSQL 16/TimescaleDB",
            "Kafka, object storage and Ollama are not running; simulator uses explicit development database transport",
            "No physical phone/controller/drone test; Flutter SDK unavailable",
            "Desktop PyTorch route model and thermal analysis tools do not have web adapters",
            "Field services remain separate, with no production authentication/tenancy integration"]}
    (OUTPUT / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
