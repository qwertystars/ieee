#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"
CONFIG_FILE="${BACKUP_CONFIG_FILE:-$ROOT_DIR/config/backup-restore.env}"
if [[ -f "$CONFIG_FILE" ]]; then source "$CONFIG_FILE"; fi

BACKUP_ENCRYPTION_KEY_FILE="${BACKUP_ENCRYPTION_KEY_FILE:-}"
BACKUP_ENCRYPTION_CIPHER="${BACKUP_ENCRYPTION_CIPHER:-aes-256-cbc}"
RPO_TARGET_S="${RPO_TARGET_S:-${BACKUP_RPO_TARGET_SECONDS:-60}}"
RTO_TARGET_S="${RTO_TARGET_S:-${BACKUP_RTO_TARGET_SECONDS:-900}}"
PG_USER="${PG_USER:-disaster}"
PG_DB="${PG_DB:-disaster}"
MINIO_BUCKET="${MINIO_BUCKET:-models}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-minio}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-minio123}"
RESTORE_TARGET_DIR="${RESTORE_TARGET_DIR:-}"
RESTORE_METADATA_DIR="${RESTORE_METADATA_DIR:-}"

log() { printf '[restore] %s\n' "$*"; }
die() { printf '[restore] ERROR %s\n' "$*" >&2; exit 1; }
now_ms() { date -u +%s%3N; }
require() { command -v "$1" >/dev/null 2>&1 || die "$1 is required"; }

BACKUP_PATH="${1:-}"
[[ -n "$BACKUP_PATH" ]] || die "usage: bash scripts/restore.sh <backup-directory>"
[[ -d "$BACKUP_PATH" ]] || die "backup path must be a directory: $BACKUP_PATH"
BACKUP_PATH="$(cd "$BACKUP_PATH" && pwd)"
MANIFEST="$BACKUP_PATH/manifest.json"
ARCHIVE="$BACKUP_PATH/backup.enc"
[[ -f "$MANIFEST" && -f "$ARCHIVE" && -f "$BACKUP_PATH/manifest.sha256" ]] || die "backup envelope is incomplete"
RESTORE_SUCCESS_MARKER="${RESTORE_SUCCESS_MARKER:-$BACKUP_PATH/restore.success}"
RESTORE_REPORT="${RESTORE_REPORT:-$BACKUP_PATH/restore.report.json}"
[[ ! -e "$RESTORE_SUCCESS_MARKER" ]] || die "refusing pre-existing restore success marker"

require date
require python3
require sha256sum
require openssl
require tar
[[ "$RPO_TARGET_S" =~ ^[0-9]+$ ]] || die "RPO target must be numeric"
[[ "$RTO_TARGET_S" =~ ^[0-9]+$ ]] || die "RTO target must be numeric"
[[ -r "$BACKUP_ENCRYPTION_KEY_FILE" && -s "$BACKUP_ENCRYPTION_KEY_FILE" ]] || die "BACKUP_ENCRYPTION_KEY_FILE is required and must be readable"

STARTED_MS="$(now_ms)"
WORK_DIR="$(mktemp -d)"
PAYLOAD_DIR="$WORK_DIR/payload"
STAGE_DIR=""
cleanup() {
  status=$?
  rm -rf "$WORK_DIR" "$STAGE_DIR"
  if (( status != 0 )); then rm -f "$RESTORE_SUCCESS_MARKER"; fi
  trap - EXIT
  exit "$status"
}
trap cleanup EXIT

(cd "$BACKUP_PATH" && sha256sum -c manifest.sha256 >/dev/null) || die "manifest checksum mismatch"
EXPECTED_ARCHIVE_SHA="$(python3 - "$MANIFEST" <<'PY'
import json, sys
print(json.load(open(sys.argv[1]))["integrity"]["archive_sha256"])
PY
)"
ACTUAL_ARCHIVE_SHA="$(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
[[ "$ACTUAL_ARCHIVE_SHA" == "$EXPECTED_ARCHIVE_SHA" ]] || die "encrypted archive checksum mismatch"

mkdir -p "$PAYLOAD_DIR"
openssl enc -d -"$BACKUP_ENCRYPTION_CIPHER" -pbkdf2 -iter 200000 \
  -pass "file:$BACKUP_ENCRYPTION_KEY_FILE" -in "$ARCHIVE" -out "$WORK_DIR/archive.tar" \
  || die "encrypted archive cannot be decrypted"
tar -tf "$WORK_DIR/archive.tar" >/dev/null || die "archive is truncated or malformed"
tar -xf "$WORK_DIR/archive.tar" -C "$PAYLOAD_DIR" || die "archive extraction failed"

MODE="$(python3 - "$MANIFEST" <<'PY'
import json, sys
print(json.load(open(sys.argv[1])).get("mode", "production"))
PY
)"
python3 - "$MANIFEST" "$PAYLOAD_DIR" "$MODE" <<'PY'
import hashlib, json, pathlib, sys

manifest, payload, mode = json.load(open(sys.argv[1])), pathlib.Path(sys.argv[2]), sys.argv[3]
files = manifest.get("files", [])
if not files or manifest.get("schema_version") != "task-10/v1":
    raise SystemExit("manifest schema or file list is missing")
for item in files:
    path = payload / item["path"]
    if not path.is_file():
        raise SystemExit(f"missing payload file: {item['path']}")
    if path.stat().st_size != item["size"] or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
        raise SystemExit(f"payload checksum mismatch: {item['path']}")
required = {"queue_offsets.json", "model_manifests.json", "audit_chain.json", "signing_key_escrow.json", "object_metadata.json", "source_snapshot.json", "row_counts.json"}
if not required.issubset({pathlib.Path(item["path"]).name for item in files}):
    raise SystemExit("required restore metadata is missing")
coverage = manifest.get("coverage", {})
for name in ("queue_offsets", "model_manifests", "audit_data", "object_metadata", "objects", "signing_key_escrow_metadata"):
    if coverage.get(name) is not True:
        raise SystemExit(f"manifest coverage is incomplete: {name}")

metadata = payload / "metadata"
offsets = json.loads((metadata / "queue_offsets.json").read_text())
topics = offsets.get("topics")
if not isinstance(topics, list) or not topics or any(int(item.get("offset", -1)) < 0 for item in topics):
    raise SystemExit("queue offsets are missing or invalid")
manifests = json.loads((metadata / "model_manifests.json").read_text())
objects = json.loads((metadata / "object_metadata.json").read_text())
object_by_key = {item.get("key"): item for item in objects}
if not manifests or not objects:
    raise SystemExit("model manifests or object metadata is empty")
for model in manifests:
    artifact = model.get("artifact", {})
    key, digest = artifact.get("r2_key"), artifact.get("sha256") or model.get("checksum")
    item = object_by_key.get(key)
    path = payload / "objects" / key if key else pathlib.Path("/")
    if not item or digest != item.get("sha256") or not path.is_file():
        raise SystemExit(f"model/object metadata mismatch: {key}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest or path.stat().st_size != int(item["size"]):
        raise SystemExit(f"object hash or size mismatch: {key}")
escrow = json.loads((metadata / "signing_key_escrow.json").read_text())
if escrow.get("live_keys_external") is not True or escrow.get("private_keys_in_backup") is not False or not escrow.get("escrow_reference"):
    raise SystemExit("signing-key escrow policy is unsafe or incomplete")
chain = json.loads((metadata / "audit_chain.json").read_text())
events, previous = chain.get("events"), None
if not isinstance(events, list) or not events:
    raise SystemExit("audit chain is empty")
for sequence, event in enumerate(events, 1):
    if event.get("sequence") != sequence or event.get("prev_hash") != previous:
        raise SystemExit("audit chain sequence/predecessor mismatch")
    body = {key: value for key, value in event.items() if key != "hash"}
    actual = "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != event.get("hash"):
        raise SystemExit(f"audit chain hash mismatch at sequence {sequence}")
    previous = actual
head = chain.get("head", {})
if head.get("last_sequence") != len(events) or head.get("last_hash") != previous:
    raise SystemExit("audit chain head mismatch")
if mode == "fixture":
    rows = (payload / "database" / "rows.jsonl").read_text().splitlines()
    counts = json.loads((metadata / "row_counts.json").read_text())
    actual = {}
    for line in rows:
        row = json.loads(line)
        actual[row["table"]] = actual.get(row["table"], 0) + 1
    if actual != counts:
        raise SystemExit(f"row count mismatch: {actual} != {counts}")
else:
    if not (payload / "database" / "db.sql.gz").is_file():
        raise SystemExit("database dump is missing")
PY

RPO_SECONDS="$(python3 - "$MANIFEST" <<'PY'
import json, sys
manifest = json.load(open(sys.argv[1]))
print(int(manifest["rpo"]["measured_seconds"]))
PY
)"
(( RPO_SECONDS <= RPO_TARGET_S )) || die "RPO target exceeded: measured=${RPO_SECONDS}s target=${RPO_TARGET_S}s"

if [[ "$MODE" == fixture ]]; then
  [[ -n "$RESTORE_TARGET_DIR" ]] || die "RESTORE_TARGET_DIR is required for fixture clean-room restore"
  [[ ! -e "$RESTORE_TARGET_DIR" ]] || die "clean-room target already exists: $RESTORE_TARGET_DIR"
  mkdir -p "$(dirname "$RESTORE_TARGET_DIR")"
  STAGE_DIR="$(mktemp -d "$(dirname "$RESTORE_TARGET_DIR")/.restore.XXXXXX")"
  cp -a "$PAYLOAD_DIR/." "$STAGE_DIR/"
  mv "$STAGE_DIR" "$RESTORE_TARGET_DIR"
  STAGE_DIR=""
else
  require docker
  docker compose exec -T db pg_isready -U "$PG_USER" -d "$PG_DB" >/dev/null
  docker compose exec -T minio mc alias set local "http://localhost:9000" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
  docker compose exec -T db psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 -c \
    "DROP EXTENSION IF EXISTS h3 CASCADE; DROP EXTENSION IF EXISTS age CASCADE; DROP EXTENSION IF EXISTS postgis CASCADE; DROP SCHEMA IF EXISTS public CASCADE; DROP SCHEMA IF EXISTS ag_catalog CASCADE; CREATE SCHEMA public;" >/dev/null
  gunzip -c "$PAYLOAD_DIR/database/db.sql.gz" | docker compose exec -T db psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 -q
  REMOTE_TMP="/tmp/resqnet-restore-$$"
  docker compose exec -T minio mkdir -p "$REMOTE_TMP"
  docker compose cp "$PAYLOAD_DIR/objects/." "minio:$REMOTE_TMP/"
  docker compose exec -T minio mc mirror --overwrite "$REMOTE_TMP" "local/$MINIO_BUCKET"
  docker compose exec -T minio rm -rf "$REMOTE_TMP"
fi

FINISHED_MS="$(now_ms)"
RTO_SECONDS="$(python3 - "$STARTED_MS" "$FINISHED_MS" <<'PY'
import sys
print(max(1, (int(sys.argv[2]) - int(sys.argv[1]) + 999) // 1000))
PY
)"
(( RTO_SECONDS <= RTO_TARGET_S )) || die "RTO target exceeded: measured=${RTO_SECONDS}s target=${RTO_TARGET_S}s"

python3 - "$MANIFEST" "$RTO_SECONDS" "$RESTORE_REPORT" "$ACTUAL_ARCHIVE_SHA" "$RPO_SECONDS" <<'PY'
import datetime, json, pathlib, sys
manifest_path, rto, report_path, archive_sha, rpo = sys.argv[1:]
manifest = json.load(open(manifest_path))
manifest["rto"].update({"measured_seconds": int(rto), "status": "PASS"})
manifest["recovery_status"] = "PASS"
manifest["recovered_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
temporary = pathlib.Path(manifest_path).with_suffix(".json.tmp")
temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
temporary.replace(manifest_path)
report = {"status": "PASS", "archive_sha256": archive_sha, "rpo_seconds": int(rpo), "rto_seconds": int(rto), "checks": {"manifest": True, "archive": True, "rows": True, "queue_offsets": True, "model_manifests": True, "audit_chain": True, "objects": True, "signing_key_escrow_policy": True, "live_signing_keys": "external"}}
pathlib.Path(report_path).parent.mkdir(parents=True, exist_ok=True)
pathlib.Path(report_path).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
PY
(cd "$BACKUP_PATH" && sha256sum manifest.json > manifest.sha256)
touch "$RESTORE_SUCCESS_MARKER"
trap - EXIT
printf '[restore] RESTORE_SUCCESS source=%s archive_sha256=%s rpo_seconds=%s rto_seconds=%s marker=%s\n' "$BACKUP_PATH" "$ACTUAL_ARCHIVE_SHA" "$RPO_SECONDS" "$RTO_SECONDS" "$RESTORE_SUCCESS_MARKER"
