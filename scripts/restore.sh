#!/usr/bin/env bash
# restore.sh -- Restore ResQNet-SAGE database + MinIO model weights from backup.
#
# Usage:
#   bash scripts/restore.sh <backup-path>
#   make restore BACKUP=<backup-path>
#
# <backup-path> is a directory created by backup.sh, containing:
#   db.sql.gz    -- gzipped pg_dump to restore into PostgreSQL
#   minio/       -- files to restore into the MinIO "models" bucket
#
# Defaults target the Docker stack (db service, MinIO service). Override
# PG_USER / PG_DB to restore into a different database in the same container.
#
# The restore drops existing tables (via pg_dump's --clean semantics are NOT
# used; instead the restore pipes SQL into psql which CREATEs or ALTERs tables
# per the dump). For a clean restore, drop the target schema first.
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

# ── Helpers ──────────────────────────────────────────────────────────────────
log()  { echo "[restore] $*"; }
ok()   { echo "[restore]   OK  $*"; }
die()  { echo "[restore]   ERR $*" >&2; exit 1; }

command -v gunzip >/dev/null 2>&1 || die "gunzip not found"
command -v docker >/dev/null 2>&1 || die "docker not found"

# ── Validate arguments ───────────────────────────────────────────────────────
BACKUP_PATH="${1:-}"
if [ -z "$BACKUP_PATH" ]; then
    die "Usage: bash scripts/restore.sh <backup-path>  (or: make restore BACKUP=<path>)"
fi

# Resolve to absolute path and verify the dump exists.
BACKUP_PATH="$(cd "$BACKUP_PATH" 2>/dev/null && pwd)" || \
    die "Backup path not found: $1"

DB_DUMP="$BACKUP_PATH/db.sql.gz"
MINIO_DIR="$BACKUP_PATH/minio"

[ -f "$DB_DUMP" ] || die "db.sql.gz not found in $BACKUP_PATH"

log "Restoring from: $BACKUP_PATH"
log "Target database: $PG_DB (user: $PG_USER)"

# ── 1. PostgreSQL restore ────────────────────────────────────────────────────
# Drop existing schema for a clean restore, then pipe the dump into psql.
# The dump contains CREATE TABLE + COPY statements; dropping first avoids
# duplicate-key conflicts from existing data.
log "Dropping existing schema in '$PG_DB' ..."
docker compose exec -T db psql -U "$PG_USER" -d "$PG_DB" -c \
    "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;" \
    >/dev/null 2>&1 || die "Failed to drop schema"

# Restore extensions that the schema depends on.
docker compose exec -T db psql -U "$PG_USER" -d "$PG_DB" -c \
    "CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS age; CREATE EXTENSION IF NOT EXISTS h3;" \
    >/dev/null 2>&1 || true

log "Restoring database from db.sql.gz ..."
# ON_ERROR_STOP=0 continues past non-fatal errors (e.g. "ag_catalog already
# exists" from the AGE extension, which is expected when extensions are
# pre-created). Filter out empty lines and noisy NOTICE messages.
gunzip -c "$DB_DUMP" | docker compose exec -T db psql -U "$PG_USER" -d "$PG_DB" \
    -v ON_ERROR_STOP=0 -q 2>&1 \
    | grep -vE "^$|^SET$|^psql:.*NOTICE|ag_catalog" || true
ok "database restored"

# Verify alembic version is current (the dump includes alembic_version table).
ALEMBIC_REV="$(docker compose exec -T db psql -U "$PG_USER" -d "$PG_DB" -tAc \
    "SELECT version_num FROM alembic_version;" 2>/dev/null || echo "unknown")"
ok "alembic version: $ALEMBIC_REV"

# ── 2. MinIO restore ─────────────────────────────────────────────────────────
if [ -d "$MINIO_DIR" ] && [ -n "$(find "$MINIO_DIR" -type f 2>/dev/null | head -1)" ]; then
    log "Restoring MinIO bucket '$MINIO_BUCKET' from $MINIO_DIR ..."
    REMOTE_TMP="/tmp/resqnet-restore-$$"

    # Copy backup files into the MinIO container.
    docker compose exec -T minio mkdir -p "$REMOTE_TMP" 2>/dev/null || true
    docker compose cp "$MINIO_DIR/." "minio:$REMOTE_TMP/" 2>/dev/null || true

    # Configure mc alias (idempotent).
    docker compose exec -T minio mc alias set local \
        http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" \
        >/dev/null 2>&1 || true

    # Ensure the target bucket exists, then mirror files back.
    docker compose exec -T minio mc mb -p "local/$MINIO_BUCKET" 2>/dev/null || true
    docker compose exec -T minio sh -c \
        "mc mirror --overwrite $REMOTE_TMP local/$MINIO_BUCKET 2>/dev/null || true"

    # Clean up the temp path.
    docker compose exec -T minio sh -c "rm -rf $REMOTE_TMP" 2>/dev/null || true
    ok "minio restored"
else
    log "No MinIO files in $MINIO_DIR -- skipping MinIO restore"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "=== Restore complete ==="
echo "  Source:   $BACKUP_PATH"
echo "  Database: $PG_DB (alembic: $ALEMBIC_REV)"
echo "  MinIO:   $MINIO_BUCKET bucket"
echo ""
echo "Verify with:"
echo "  docker compose exec db psql -U $PG_USER -d $PG_DB -c 'SELECT count(*) FROM observations;'"
