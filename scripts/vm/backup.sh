#!/usr/bin/env bash
# Nightly logical backup of the production database and MinIO data.
# usage: scripts/vm/backup.sh [backup-dir]   (default: ./backups)
# Keeps the newest BACKUP_RETENTION (default 14) backups. Copy the output
# directory off the VM: a backup that lives only on the VM is not a backup.
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
set -a; source ./.env; set +a

DEST_ROOT="${1:-$ROOT_DIR/backups}"
RETENTION="${BACKUP_RETENTION:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$DEST_ROOT/$STAMP"
compose() { docker compose -f docker-compose.prod.yml "$@"; }

umask 077
mkdir -p "$DEST"
compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$DEST/db.dump"
compose exec -T minio tar -C /data -cf - . | gzip > "$DEST/minio.tar.gz"
(cd "$DEST" && sha256sum db.dump minio.tar.gz > SHA256SUMS)
echo "backup written to $DEST"

ls -1d "$DEST_ROOT"/*/ 2>/dev/null | sort | head -n "-$RETENTION" | xargs -r rm -rf
