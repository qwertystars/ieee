#!/usr/bin/env bash
# e2e_up.sh — Bring up the full ResQNet-SAGE stack for Playwright e2e tests.
#
# Starts the Docker backend stack, seeds the Rivertown demo scenario, waits for
# health, then launches the Vite preview server (built dist) on port 4173.
# Playwright's webServer manages this process — the script stays alive (via
# exec into vite preview) until Playwright kills it after tests complete.
#
# Prerequisites:
#   - frontend/dist built (cd frontend && npm run build)
#   - Docker daemon running
#
# Usage:
#   bash scripts/e2e_up.sh           # foreground (Playwright webServer)
#   make e2e                         # starts stack + seeds + runs playwright
#
# Exits non-zero on any failure during startup. Once vite preview starts,
# the process runs until killed by Playwright (or Ctrl-C).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
PREVIEW_PORT="${PREVIEW_PORT:-4173}"
PREVIEW_URL="http://localhost:${PREVIEW_PORT}"

echo "=== e2e_up: starting Docker stack (profile: full) ==="
docker compose --profile full up -d --wait

echo "=== e2e_up: seeding demo data ==="
docker compose exec -T backend python -m app.seed.seed_demo

echo "=== e2e_up: stopping any running simulator ==="
SIM_TOKEN=$(curl -sf -X POST "${BACKEND_URL}/api/auth/login" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=admin@demo.disaster&password=demo1234' 2>/dev/null | \
  python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)
if [ -n "$SIM_TOKEN" ]; then
  curl -sf -X POST "${BACKEND_URL}/api/simulator/stop" \
    -H "Authorization: Bearer ${SIM_TOKEN}" >/dev/null 2>&1 || true
else
  echo "  WARNING: could not obtain auth token to stop simulator"
fi

echo "=== e2e_up: waiting for backend at ${BACKEND_URL}/healthz ==="
timeout=60
elapsed=0
until curl -sf "${BACKEND_URL}/healthz" >/dev/null 2>&1; do
  if [ "$elapsed" -ge "$timeout" ]; then
    echo "ERROR: backend did not become healthy within ${timeout}s" >&2
    exit 1
  fi
  sleep 2
  elapsed=$((elapsed + 2))
done
echo "=== e2e_up: backend healthy (${elapsed}s) ==="

echo "=== e2e_up: starting frontend preview on ${PREVIEW_URL} ==="
# exec replaces the shell with vite preview so Playwright can manage the
# process lifecycle directly (sends SIGTERM after tests complete).
cd "${ROOT_DIR}/frontend"
exec npx vite preview --host 0.0.0.0 --port "${PREVIEW_PORT}"
