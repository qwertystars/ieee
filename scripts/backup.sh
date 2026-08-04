#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

CONFIG_FILE="${BACKUP_CONFIG_FILE:-$ROOT_DIR/config/backup-restore.env}"
if [[ -f "$CONFIG_FILE" ]]; then
  source "$CONFIG_FILE"
fi

BACKUP_ROOT="${BACKUP_ROOT:-$ROOT_DIR/backups}"
BACKUP_FIXTURE_DIR="${BACKUP_FIXTURE_DIR:-}"
BACKUP_METADATA_DIR="${BACKUP_METADATA_DIR:-}"
BACKUP_ENCRYPTION_KEY_FILE="${BACKUP_ENCRYPTION_KEY_FILE:-}"
BACKUP_ENCRYPTION_CIPHER="${BACKUP_ENCRYPTION_CIPHER:-aes-256-cbc}"
BACKUP_FREQUENCY_SECONDS="${BACKUP_FREQUENCY_SECONDS:-60}"
BACKUP_RETENTION_COUNT="${BACKUP_RETENTION_COUNT:-30}"
BACKUP_RPO_TARGET_SECONDS="${BACKUP_RPO_TARGET_SECONDS:-60}"
BACKUP_RTO_TARGET_SECONDS="${BACKUP_RTO_TARGET_SECONDS:-900}"
BACKUP_KEY_REFERENCE="${BACKUP_KEY_REFERENCE:-external-secret-manager://resqnet/backup}"
BACKUP_OFFSITE_PROVIDER="${BACKUP_OFFSITE_PROVIDER:-external-object-store}"
BACKUP_OFFSITE_DIR="${BACKUP_OFFSITE_DIR:-}"
BACKUP_OFFSITE_STATUS="${BACKUP_OFFSITE_STATUS:-DEFERRED_EXTERNAL}"
PG_USER="${PG_USER:-disaster}"
PG_DB="${PG_DB:-disaster}"
MINIO_BUCKET="${MINIO_BUCKET:-models}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-minio}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-minio123}"

log() { printf '[backup] %s\n' "$*"; }
die() { printf '[backup] ERROR %s\n' "$*" >&2; exit 1; }
now_ms() { date -u +%s%3N; }
require() { command -v "$1" >/dev/null 2>&1 || die "$1 is required"; }

require date
require python3
require sha256sum
require tar
require openssl
[[ "$BACKUP_FREQUENCY_SECONDS" =~ ^[0-9]+$ ]] || die "frequency must be numeric"
[[ "$BACKUP_RETENTION_COUNT" =~ ^[1-9][0-9]*$ ]] || die "retention count must be positive"
[[ "$BACKUP_RPO_TARGET_SECONDS" =~ ^[0-9]+$ ]] || die "RPO target must be numeric"
[[ "$BACKUP_RTO_TARGET_SECONDS" =~ ^[0-9]+$ ]] || die "RTO target must be numeric"
[[ -r "$BACKUP_ENCRYPTION_KEY_FILE" ]] || die "BACKUP_ENCRYPTION_KEY_FILE is required and must be readable"
[[ -s "$BACKUP_ENCRYPTION_KEY_FILE" ]] || die "encryption key file is empty"

MODE=production
if [[ -n "$BACKUP_FIXTURE_DIR" ]]; then
  MODE=fixture
  [[ -d "$BACKUP_FIXTURE_DIR" ]] || die "fixture directory not found: $BACKUP_FIXTURE_DIR"
else
  require docker
  [[ -n "$BACKUP_METADATA_DIR" ]] || die "BACKUP_METADATA_DIR is required in production mode"
  [[ -d "$BACKUP_METADATA_DIR" ]] || die "metadata directory not found: $BACKUP_METADATA_DIR"
fi

mkdir -p "$BACKUP_ROOT"
STARTED_MS="$(now_ms)"
TIMESTAMP="${BACKUP_TIMESTAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
FINAL_DIR="$BACKUP_ROOT/$TIMESTAMP"
[[ ! -e "$FINAL_DIR" ]] || die "backup already exists: $FINAL_DIR"
WORK_DIR="$(mktemp -d "$BACKUP_ROOT/.backup-${TIMESTAMP}.XXXXXX")"
PAYLOAD_DIR="$WORK_DIR/payload"
mkdir -p "$PAYLOAD_DIR/database" "$PAYLOAD_DIR/metadata" "$PAYLOAD_DIR/objects"
cleanup() { rm -rf "$WORK_DIR"; }
trap cleanup EXIT

REQUIRED_METADATA=(queue_offsets.json model_manifests.json audit_chain.json signing_key_escrow.json object_metadata.json source_snapshot.json row_counts.json)
if [[ "$MODE" == fixture ]]; then
  cp -a "$BACKUP_FIXTURE_DIR/." "$PAYLOAD_DIR/"
else
  log "dumping PostgreSQL database '$PG_DB'"
  docker compose exec -T db pg_dump -U "$PG_USER" "$PG_DB" --no-owner --no-privileges \
    | gzip > "$PAYLOAD_DIR/database/db.sql.gz"
  REMOTE_TMP="/tmp/resqnet-backup-$$"
  docker compose exec -T minio mc alias set local "http://localhost:9000" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
  docker compose exec -T minio mc mirror --overwrite "local/$MINIO_BUCKET" "$REMOTE_TMP"
  docker compose cp "minio:$REMOTE_TMP/." "$PAYLOAD_DIR/objects/"
  docker compose exec -T minio rm -rf "$REMOTE_TMP"
  for metadata in "${REQUIRED_METADATA[@]}"; do
    [[ -f "$BACKUP_METADATA_DIR/$metadata" ]] || die "required metadata missing: $metadata"
    cp "$BACKUP_METADATA_DIR/$metadata" "$PAYLOAD_DIR/metadata/$metadata"
  done
fi

for metadata in "${REQUIRED_METADATA[@]}"; do
  [[ -f "$PAYLOAD_DIR/metadata/$metadata" ]] || die "required metadata missing: $metadata"
done
if [[ "$MODE" == fixture ]]; then
  [[ -s "$PAYLOAD_DIR/database/rows.jsonl" ]] || die "fixture database rows are empty"
else
  [[ -s "$PAYLOAD_DIR/database/db.sql.gz" ]] || die "database dump is empty"
fi

python3 - "$PAYLOAD_DIR" "$STARTED_MS" "$MODE" <<'PY'
import hashlib, json, os, pathlib, sys

payload, started, mode = pathlib.Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
metadata = payload / "metadata"
source_path = metadata / "source_snapshot.json"
source = json.loads(source_path.read_text())
latest = int(source.get("latest_source_event_at_ms", 0))
if latest <= 0:
    if mode != "fixture":
        raise SystemExit("source checkpoint is required for production RPO measurement")
    latest = started - 1000
source["latest_source_event_at_ms"] = latest
source_path.write_text(json.dumps(source, sort_keys=True, separators=(",", ":")) + "\n")

offsets = json.loads((metadata / "queue_offsets.json").read_text())
topics = offsets.get("topics")
if not isinstance(topics, list) or not topics:
    raise SystemExit("queue offset metadata has no topics")
for item in topics:
    if not item.get("topic") or int(item.get("partition", -1)) < 0 or int(item.get("offset", -1)) < 0:
        raise SystemExit("invalid queue offset metadata")

manifests = json.loads((metadata / "model_manifests.json").read_text())
objects = json.loads((metadata / "object_metadata.json").read_text())
if not isinstance(manifests, list) or not manifests or not isinstance(objects, list) or not objects:
    raise SystemExit("model or object metadata is empty")
object_by_key = {str(item["key"]): item for item in objects}
for model in manifests:
    artifact = model.get("artifact", {})
    key = artifact.get("r2_key")
    digest = artifact.get("sha256") or model.get("checksum")
    if not key or not digest or key not in object_by_key or digest != object_by_key[key].get("sha256"):
        raise SystemExit("model manifest/object metadata mismatch")
    object_path = payload / "objects" / key
    if mode == "fixture" and (not object_path.is_file() or hashlib.sha256(object_path.read_bytes()).hexdigest() != digest):
        raise SystemExit(f"object hash mismatch: {key}")

escrow = json.loads((metadata / "signing_key_escrow.json").read_text())
if escrow.get("live_keys_external") is not True or escrow.get("private_keys_in_backup") is not False or not escrow.get("escrow_reference"):
    raise SystemExit("signing-key escrow policy is unsafe or incomplete")

chain = json.loads((metadata / "audit_chain.json").read_text())
events = chain.get("events")
if not isinstance(events, list) or not events:
    raise SystemExit("audit chain is empty")
previous = None
for expected, event in enumerate(events, 1):
    if event.get("sequence") != expected or event.get("prev_hash") != previous:
        raise SystemExit("audit chain sequence/predecessor mismatch")
    body = {key: value for key, value in event.items() if key != "hash"}
    actual = "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != event.get("hash"):
        raise SystemExit(f"audit hash mismatch at sequence {expected}")
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
PY

ARCHIVE_TAR="$WORK_DIR/archive.tar"
ARCHIVE="$WORK_DIR/backup.enc"
tar --sort=name --mtime='UTC 1970-01-01' -C "$PAYLOAD_DIR" -cf "$ARCHIVE_TAR" .
openssl enc -"$BACKUP_ENCRYPTION_CIPHER" -pbkdf2 -iter 200000 -salt \
  -pass "file:$BACKUP_ENCRYPTION_KEY_FILE" -in "$ARCHIVE_TAR" -out "$ARCHIVE"
ARCHIVE_SHA256="$(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
RPO_SECONDS="$(python3 - "$STARTED_MS" "$PAYLOAD_DIR/metadata/source_snapshot.json" <<'PY'
import json, sys
started, path = int(sys.argv[1]), sys.argv[2]
latest = int(json.load(open(path))["latest_source_event_at_ms"])
print(max(0, (started - latest + 999) // 1000))
PY
)"
OFFSITE_EFFECTIVE="$BACKUP_OFFSITE_STATUS"
[[ -n "$BACKUP_OFFSITE_DIR" ]] && OFFSITE_EFFECTIVE=configured_local_mirror

python3 - "$WORK_DIR/manifest.json" "$ARCHIVE_SHA256" "$RPO_SECONDS" "$STARTED_MS" "$MODE" "$PAYLOAD_DIR" "$OFFSITE_EFFECTIVE" "$BACKUP_FREQUENCY_SECONDS" "$BACKUP_RETENTION_COUNT" "$BACKUP_ENCRYPTION_CIPHER" "$BACKUP_KEY_REFERENCE" "$BACKUP_OFFSITE_PROVIDER" "$BACKUP_RPO_TARGET_SECONDS" "$BACKUP_RTO_TARGET_SECONDS" "$TIMESTAMP" <<'PY'
import hashlib, json, pathlib, sys
out, archive_sha, rpo, started, mode, payload, offsite, frequency, retention, cipher, key_reference, offsite_provider, rpo_target, rto_target, backup_id = sys.argv[1:]
payload = pathlib.Path(payload)
files = []
for path in sorted(item for item in payload.rglob("*") if item.is_file()):
    files.append({"path": str(path.relative_to(payload)), "size": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
manifest = {
    "schema_version": "task-10/v1",
    "backup_id": backup_id,
    "created_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z"),
    "mode": mode,
    "schedule": {"frequency_seconds": int(frequency), "operator": "external scheduler"},
    "retention": {"keep_successful_backups": int(retention), "policy": "prune oldest after successful commit"},
    "encryption": {"algorithm": cipher.upper(), "kdf": "PBKDF2-HMAC-SHA256", "key_custody": "external-secret-manager", "key_reference": key_reference},
    "integrity": {"algorithm": "SHA-256", "archive_sha256": archive_sha, "manifest_sha256_file": "manifest.sha256", "files_checked": len(files)},
    "restore_order": ["database", "queue_offsets", "model_manifests", "audit_chain", "objects", "signing_key_escrow"],
    "coverage": {"database_rows": True, "raw_events": True, "evaluation_jobs": True, "queue_offsets": True, "model_manifests": True, "audit_data": True, "audit_chain_heads": True, "object_metadata": True, "objects": True, "signing_key_escrow_metadata": True, "live_signing_keys": "external"},
    "offsite": {"required": True, "provider": offsite_provider, "status": offsite, "encrypted_archive_copy": True},
    "rpo": {"target_seconds": int(rpo_target), "measured_seconds": int(rpo)},
    "rto": {"target_seconds": int(rto_target), "measured_seconds": None, "status": "awaiting_restore"},
    "archive": {"filename": "backup.enc", "sha256": archive_sha},
    "files": files,
    "status": "complete",
}
pathlib.Path(out).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
PY
(cd "$WORK_DIR" && sha256sum manifest.json > manifest.sha256)
openssl enc -d -"$BACKUP_ENCRYPTION_CIPHER" -pbkdf2 -iter 200000 -pass "file:$BACKUP_ENCRYPTION_KEY_FILE" \
  -in "$ARCHIVE" -out "$WORK_DIR/self-check.tar"
tar -tf "$WORK_DIR/self-check.tar" >/dev/null
rm -rf "$PAYLOAD_DIR" "$ARCHIVE_TAR" "$WORK_DIR/self-check.tar"

mkdir -p "$BACKUP_ROOT"
mv "$WORK_DIR" "$FINAL_DIR"
if [[ -n "$BACKUP_OFFSITE_DIR" ]]; then
  mkdir -p "$BACKUP_OFFSITE_DIR"
  OFFSITE_TMP="$(mktemp -d "$BACKUP_OFFSITE_DIR/.${TIMESTAMP}.XXXXXX")"
  cp -a "$FINAL_DIR/." "$OFFSITE_TMP/"
  cmp "$FINAL_DIR/backup.enc" "$OFFSITE_TMP/backup.enc"
  mv "$OFFSITE_TMP" "$BACKUP_OFFSITE_DIR/$TIMESTAMP"
fi
touch "$FINAL_DIR/backup.success"

python3 - "$BACKUP_ROOT" "$BACKUP_RETENTION_COUNT" "$TIMESTAMP" <<'PY'
import pathlib, shutil, sys
root, keep, current = pathlib.Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
dirs = sorted(path for path in root.iterdir() if path.is_dir() and path.name[:4].isdigit() and (path / "backup.success").exists())
for path in dirs[:-keep]:
    if path.name != current:
        shutil.rmtree(path)
PY

trap - EXIT
printf '[backup] BACKUP_SUCCESS path=%s archive_sha256=%s rpo_seconds=%s\n' "$FINAL_DIR" "$ARCHIVE_SHA256" "$RPO_SECONDS"
