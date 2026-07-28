#!/usr/bin/env bash
# backup.sh -- ResQNet-SAGE disaster database + MinIO model weights backup.
#
# Creates a timestamped directory under backups/ containing:
#   db.sql.gz    -- gzipped pg_dump of the full database (schema + data)
#   minio/       -- mirror of the MinIO "models" bucket
#   manifest.txt -- backup metadata (timestamp, sizes, file counts)
#
# Defaults target the Docker stack (db service, MinIO service). The database
# is dumped via `docker compose exec -T db pg_dump` so the pg_dump version
# always matches the server version inside the container.
#
# Override PG_USER / PG_DB to back up a different database in the same container.
#
# Usage:
#   bash scripts/backup.sh
#   make backup
#   PG_DB=resqnet_backup_test bash scripts/backup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# ── Configuration (defaults match docker-compose.yml) ────────────────────────
PG_USER="${PG_USER:-disaster}"
PG_DB="${PG_DB:-disaster}"
MINIO_BUCKET="${MINIO_BUCKET:-models}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-minio}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-minio123}"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="backups/$TIMESTAMP"
MINIO_DIR="$BACKUP_DIR/minio"

# ── Helpers ──────────────────────────────────────────────────────────────────
log()  { echo "[backup] $*"; }
ok()   { echo "[backup]   OK  $*"; }
die()  { echo "[backup]   ERR $*" >&2; exit 1; }

command -v gzip >/dev/null 2>&1 || die "gzip not found"
command -v docker >/dev/null 2>&1 || die "docker not found"

mkdir -p "$BACKUP_DIR" "$MINIO_DIR"

# ── 1. PostgreSQL backup (via docker compose exec for version match) ─────────
log "Backing up database '$PG_DB' (user: $PG_USER) ..."
docker compose exec -T db pg_dump -U "$PG_USER" "$PG_DB" \
    --no-owner --no-privileges | gzip > "$BACKUP_DIR/db.sql.gz"
DB_SIZE="$(du -h "$BACKUP_DIR/db.sql.gz" | cut -f1)"
ok "db.sql.gz ($DB_SIZE)"

# ── 2. MinIO backup ──────────────────────────────────────────────────────────
# mc is not installed on the host; run it inside the MinIO container and copy
# the mirrored files out via docker compose cp.
log "Backing up MinIO bucket '$MINIO_BUCKET' ..."
REMOTE_TMP="/tmp/resqnet-backup-$$"

# Configure mc alias inside the container (idempotent).
docker compose exec -T minio mc alias set local \
    http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" \
    >/dev/null 2>&1 || true

# Mirror the bucket to a temp path inside the container.
# --overwrite makes the operation idempotent; ignore errors if bucket is empty.
docker compose exec -T minio sh -c \
    "mc mirror --overwrite local/$MINIO_BUCKET $REMOTE_TMP 2>/dev/null || true"

# Copy the mirrored files out to the host backup directory.
docker compose cp minio:"$REMOTE_TMP/." "$MINIO_DIR/" 2>/dev/null || true

# Clean up the temp path inside the container.
docker compose exec -T minio sh -c "rm -rf $REMOTE_TMP" 2>/dev/null || true

MINIO_FILES="$(find "$MINIO_DIR" -type f | wc -l | tr -d ' ')"
ok "minio/ ($MINIO_FILES files)"

# ── 3. Manifest ──────────────────────────────────────────────────────────────
MANIFEST="$BACKUP_DIR/manifest.txt"
{
    echo "ResQNet-SAGE Backup Manifest"
    echo "Timestamp (UTC): $TIMESTAMP"
    echo "Database: $PG_DB (user: $PG_USER) via docker compose exec db"
    echo "DB dump:   db.sql.gz ($DB_SIZE)"
    echo "MinIO:     $MINIO_BUCKET bucket -> minio/ ($MINIO_FILES files)"
    echo "Host:      $(hostname)"
    echo "Created by: $0"
} > "$MANIFEST"

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "=== Backup complete ==="
echo "  Path:     $BACKUP_DIR"
echo "  DB dump:  $BACKUP_DIR/db.sql.gz ($DB_SIZE)"
echo "  MinIO:    $MINIO_DIR ($MINIO_FILES files)"
echo "  Manifest: $MANIFEST"
echo ""
echo "Restore with:"
echo "  bash scripts/restore.sh $BACKUP_DIR"
echo "  make restore BACKUP=$BACKUP_DIR"
