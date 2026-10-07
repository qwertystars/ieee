#!/usr/bin/env bash
# Restore a backup made by scripts/vm/backup.sh. DESTRUCTIVE: replaces the
# current database contents and MinIO data.
# usage: scripts/vm/restore.sh <backup-dir>
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
set -a; source ./.env; set +a

SRC="${1:?usage: $0 <backup-dir>}"
compose() { docker compose -f docker-compose.prod.yml "$@"; }

(cd "$SRC" && sha256sum -c SHA256SUMS)
read -r -p "Replace ALL current data with $SRC? Type 'restore' to continue: " answer
[[ "$answer" == "restore" ]] || { echo "aborted"; exit 1; }

compose stop web backend worker
compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner < "$SRC/db.dump"
gunzip -c "$SRC/minio.tar.gz" | compose exec -T minio tar -C /data -xf -
compose up -d
echo "restore complete"
