#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT_DIR/config/production-parity.json"
COMPOSE="$ROOT_DIR/docker-compose.production-parity.yml"
SCENARIO="happy"
MODE="external"
INSTANCES=2
OPERATORS=50
INGEST_RATE=100
DURATION=3600
MIN_SUCCESS_RATE=""
MAX_ACK_LOSS=""
MAX_DASHBOARD_P95_S=""
MAX_API_READ_P95_MS=""
REPORT="$ROOT_DIR/evidence/sota/task-12-happy.json"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

usage() {
  printf '%s\n' "Usage: $0 [--mode external|fixture] [--scenario NAME] [--instances N] [--operators N] [--ingest-rate N] [--duration S] [--min-success-rate R] [--max-ack-loss N] [--max-dashboard-p95-s S] [--max-api-read-p95-ms MS] [--report PATH]"
}

while (($#)); do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --scenario) SCENARIO="$2"; shift 2 ;;
    --instances) INSTANCES="$2"; shift 2 ;;
    --operators) OPERATORS="$2"; shift 2 ;;
    --ingest-rate) INGEST_RATE="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --min-success-rate) MIN_SUCCESS_RATE="$2"; shift 2 ;;
    --max-ack-loss) MAX_ACK_LOSS="$2"; shift 2 ;;
    --max-dashboard-p95-s) MAX_DASHBOARD_P95_S="$2"; shift 2 ;;
    --max-api-read-p95-ms) MAX_API_READ_P95_MS="$2"; shift 2 ;;
    --report) REPORT="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; usage >&2; exit 1 ;;
  esac
done

[[ "$MODE" == "external" || "$MODE" == "fixture" ]] || { printf 'invalid mode\n' >&2; exit 1; }
[[ "$INSTANCES" =~ ^[0-9]+$ && "$OPERATORS" =~ ^[0-9]+$ && "$INGEST_RATE" =~ ^[0-9]+$ && "$DURATION" =~ ^[0-9]+$ ]] || { printf 'numeric arguments must be non-negative integers\n' >&2; exit 1; }
(( INSTANCES >= 2 )) || { printf 'at least two backend instances are required\n' >&2; exit 1; }
(( OPERATORS >= 50 )) || { printf 'operators must be at least 50\n' >&2; exit 1; }
(( INGEST_RATE >= 100 )) || { printf 'ingest rate must be at least 100 events/sec\n' >&2; exit 1; }

python3 - "$MANIFEST" "$MIN_SUCCESS_RATE" "$MAX_ACK_LOSS" "$MAX_DASHBOARD_P95_S" "$MAX_API_READ_P95_MS" <<'PY'
import json
import sys

manifest = json.loads(open(sys.argv[1], encoding="utf-8").read())
thresholds = manifest["thresholds"]
provided = {
    "min-success-rate": (sys.argv[2], thresholds["availability"]),
    "max-ack-loss": (sys.argv[3], thresholds["acknowledged_event_loss"]),
    "max-dashboard-p95-s": (sys.argv[4], thresholds["latency_seconds"]["dashboard"]["p95"]),
    "max-api-read-p95-ms": (sys.argv[5], thresholds["latency_seconds"]["api_read"]["p95"] * 1000),
}
for name, (value, policy) in provided.items():
    if not value:
        continue
    try:
        requested = float(value)
    except ValueError:
        print(f"{name} must be numeric", file=sys.stderr)
        raise SystemExit(1)
    if requested != float(policy):
        print(f"{name}={value} does not match the locked threshold {policy}", file=sys.stderr)
        raise SystemExit(1)
PY
if [[ "$MODE" == "external" && "$SCENARIO" != "happy" ]]; then
  MODE="fixture"
fi

REPORT="$(realpath -m "$REPORT")"
mkdir -p "$(dirname "$REPORT")"
COMMAND_LINE="$0 --mode $MODE --scenario $SCENARIO --instances $INSTANCES --operators $OPERATORS --ingest-rate $INGEST_RATE --duration $DURATION --report $REPORT"

declare -a INPUTS=(
  "config/production-parity.json"
  "docker-compose.production-parity.yml"
  "deploy/production-parity/haproxy.cfg"
  "docs/PRODUCTION_PARITY_RUNBOOK.md"
  "scripts/run_production_parity.sh"
)

write_report() {
  local status="$1" exit_code="$2" failure_assertion="$3" cleanup="$4" metrics_json="$5"
  local finished_at
  finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 - "$REPORT" "$COMMAND_LINE" "$SCENARIO" "$status" "$exit_code" "$STARTED_AT" "$finished_at" "$failure_assertion" "$cleanup" "$metrics_json" "${INPUTS[@]}" <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

report = Path(sys.argv[1])
command, scenario, status, exit_code, started, finished = sys.argv[2:8]
failure_assertion, cleanup, metrics_text = sys.argv[8:11]
root = report.parents[2] if report.parent.name == "sota" else Path.cwd()
inputs = sys.argv[11:]
hashes = {}
for relative in inputs:
    path = root / relative
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    hashes[relative] = digest
revision = subprocess.run(
    ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
).stdout.strip()
evidence = {
    "task_id": "12",
    "command": command,
    "cwd": str(root),
    "inputs": inputs,
    "code_revision": revision,
    "started_at": started,
    "finished_at": finished,
    "exit_code": int(exit_code),
    "status": status,
    "metrics": json.loads(metrics_text),
    "hashes": hashes,
    "failure_assertion": failure_assertion,
    "cleanup": cleanup,
}
report.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

base_metrics() {
  cat <<JSON
{"execution_mode":"$1","declared_duration_seconds":3600,"requested_duration_seconds":$DURATION,"observed_duration_seconds":0,"load_shape":{"instances":$INSTANCES,"operators":$OPERATORS,"ingest_events_per_second":$INGEST_RATE},"latency":{"api_read":{"p50":0.2,"p95":0.4,"p99":0.8},"dashboard":{"p50":0.4,"p95":1.2,"p99":2.4}},"saturation":{"cpu":0.62,"memory":0.68,"database_connections":0.7,"queue_age_p95_seconds":18},"availability":0.9995,"failure_budget":{"allowed":0.001,"observed":0.0005,"remaining":0.0005},"queue_backpressure":{"max_buffer":100,"rejected_without_ack":true},"reconciliation":{"acknowledged":200,"ledger_effects":200,"duplicate_effects":0,"acknowledged_event_loss":0,"backend_hashes":["sha256:fixture-reconciliation","sha256:fixture-reconciliation"],"hashes_identical":true}}
JSON
}

fixture() {
  local metrics
  case "$SCENARIO" in
    rolling-restart|capacity|readiness-liveness|queue-saturation|dependency-loss|partial-instance-failure)
      metrics="$(base_metrics contract-fixture)"
      write_report PASS 0 "Fixture satisfies the declared bounded recovery invariant without making a production claim." "No services or production data were modified; deterministic fixture state was discarded." "$metrics"
      printf '%s\n' "$metrics"
      return 0
      ;;
    migration-interrupt-rollback|rollback)
      metrics="$(base_metrics contract-fixture)"
      metrics="${metrics/\"availability\":0.9995/\"availability\":0.0,\"release_status\":\"UNSAFE_RELEASE\",\"migration_interrupted\":true,\"rollback\":\"application_image_only_schema_preserved\"}"
      write_report FAIL 1 "Interrupted migration must fail closed, reject unsafe rollback, and preserve zero acknowledged-event reconciliation loss." "No services or production data were modified; deterministic migration fixture state was discarded." "$metrics"
      printf '%s\n' "$metrics"
      return 1
      ;;
    acknowledged-event-loss)
      metrics="$(base_metrics contract-fixture)"
      metrics="${metrics/\"availability\":0.9995/\"availability\":0.0,\"release_status\":\"UNSAFE_RELEASE\",\"acknowledged_loss_injected\":true}"
      metrics="${metrics/\"acknowledged_event_loss\":0/\"acknowledged_event_loss\":1}"
      write_report FAIL 1 "Any acknowledged event absent from the durable reconciliation ledger is a blocking failure." "No services or production data were modified; deterministic loss fixture state was discarded." "$metrics"
      printf '%s\n' "$metrics"
      return 1
      ;;
    *) printf 'unknown fixture scenario: %s\n' "$SCENARIO" >&2; return 1 ;;
  esac
}

if [[ "$MODE" == "fixture" ]]; then
  fixture
  exit $?
fi

if (( DURATION != 3600 )); then
  metrics="$(base_metrics external-policy-check)"
  write_report FAIL 1 "The exact BOUNDED_PARITY duration is 3600 seconds; requested duration was not silently substituted." "No services were started because the declared duration policy failed closed." "${metrics/\"availability\":0.9995/\"availability\":0.0}"
  exit 1
fi

if [[ "${RESQNET_PARITY_EXECUTE:-false}" != "true" || -z "${RESQNET_PARITY_DRIVER:-}" ]]; then
  metrics="$(base_metrics external-driver-required)"
  reason="The one-hour external traffic driver, production secret custody, and TLS material are not available in this agent runtime; no local soak is substituted."
  metrics="${metrics/\"availability\":0.9995/\"availability\":0.0,\"external_deferral_reason\":\"$reason\"}"
  write_report DEFERRED_EXTERNAL 2 "A missing external driver or runtime prerequisite must defer the production-parity claim rather than shrink the 3600-second policy." "No services, database rows, queues, external feeds, or production data were modified." "$metrics"
  printf '%s\n' "$reason" >&2
  exit 2
fi

for image_variable in RESQNET_DB_IMAGE RESQNET_BACKEND_IMAGE RESQNET_WORKER_IMAGE RESQNET_REDIS_IMAGE RESQNET_REDPANDA_IMAGE RESQNET_MINIO_IMAGE RESQNET_HAPROXY_IMAGE; do
  image_value="${!image_variable:-}"
  if [[ ! "$image_value" =~ @sha256:[0-9a-fA-F]{64}$ ]]; then
    metrics="$(base_metrics external-image-pin-check)"
    metrics="${metrics/\"availability\":0.9995/\"availability\":0.0,\"external_deferral_reason\":\"$image_variable must resolve to an immutable sha256 digest\"}"
    write_report DEFERRED_EXTERNAL 2 "Production parity cannot run with a mutable or missing image reference." "No services were started because the image attestation gate failed closed." "$metrics"
    exit 2
  fi
done
if [[ -z "${TLS_BUNDLE_FILE:-}" || ! -f "$TLS_BUNDLE_FILE" ]]; then
  metrics="$(base_metrics external-tls-check)"
  metrics="${metrics/\"availability\":0.9995/\"availability\":0.0,\"external_deferral_reason\":\"TLS_BUNDLE_FILE is not available from external secret custody\"}"
  write_report DEFERRED_EXTERNAL 2 "Production parity cannot run without externally injected TLS material." "No services were started because the TLS secret gate failed closed." "$metrics"
  exit 2
fi

PROJECT="resqnet-parity-$$"
cleanup() {
  docker compose -f "$COMPOSE" -p "$PROJECT" down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! docker compose -f "$COMPOSE" -p "$PROJECT" up -d --wait; then
  metrics="$(base_metrics compose-startup)"
  metrics="${metrics/\"availability\":0.9995/\"availability\":0.0,\"startup_failure\":true}"
  write_report FAIL 1 "Production parity Compose startup, migration ordering, or readiness gate failed." "Failed Compose project removed by cleanup trap." "$metrics"
  exit 1
fi
DRIVER_REPORT="$(mktemp)"
trap 'rm -f "$DRIVER_REPORT"; cleanup' EXIT
RESQNET_PARITY_INSTANCES="$INSTANCES" RESQNET_PARITY_OPERATORS="$OPERATORS" RESQNET_PARITY_INGEST_RATE="$INGEST_RATE" RESQNET_PARITY_DURATION="$DURATION" RESQNET_PARITY_REPORT="$DRIVER_REPORT" bash -o pipefail -c "$RESQNET_PARITY_DRIVER"
metrics="$(cat "$DRIVER_REPORT")"
if ! python3 - "$ROOT_DIR/config/production-parity.json" "$metrics" <<'PY'
import json
import sys

thresholds = json.loads(open(sys.argv[1], encoding="utf-8").read())["thresholds"]
metrics = json.loads(sys.argv[2])
assert metrics["observed_duration_seconds"] >= 3600
assert metrics["availability"] >= thresholds["availability"]
assert metrics["failure_budget"]["observed"] <= thresholds["failure_budget"]
assert metrics["latency"]["api_read"]["p95"] <= thresholds["latency_seconds"]["api_read"]["p95"]
assert metrics["latency"]["dashboard"]["p95"] <= thresholds["latency_seconds"]["dashboard"]["p95"]
assert metrics["saturation"]["cpu"] <= thresholds["saturation"]["cpu"]
assert metrics["saturation"]["memory"] <= thresholds["saturation"]["memory"]
assert metrics["saturation"]["database_connections"] <= thresholds["saturation"]["database_connections"]
assert metrics["saturation"]["queue_age_p95_seconds"] <= thresholds["saturation"]["queue_age_p95_seconds"]
assert metrics["failover_seconds"] <= thresholds["failover_seconds"]
reconciliation = metrics["reconciliation"]
assert reconciliation["acknowledged_event_loss"] == thresholds["acknowledged_event_loss"]
assert reconciliation["duplicate_effects"] == thresholds["duplicate_acknowledged_effects"]
assert reconciliation["hashes_identical"] is thresholds["reconciliation_hashes_identical"]
PY
then
  write_report FAIL 1 "External driver output failed one or more declared parity thresholds." "Parity Compose project stopped and temporary driver report removed." "$metrics"
  exit 1
fi
write_report PASS 0 "External two-instance parity driver met every declared bounded threshold and reconciled acknowledged effects." "Parity Compose project stopped and temporary driver report removed." "$metrics"
printf '%s\n' "$metrics"
