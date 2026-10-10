#!/usr/bin/env bash
# Create .env for docker-compose.prod.yml with freshly generated secrets.
# usage: scripts/vm/init_env.sh <public-url>   e.g. https://resq.example.org
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
PUBLIC_URL="${1:-}"

[[ "$PUBLIC_URL" =~ ^https?://[^/]+$ ]] || {
  echo "usage: $0 <public-url>  (e.g. https://resq.example.org, no trailing slash)" >&2
  exit 2
}
if [[ -e "$ENV_FILE" ]]; then
  echo "$ENV_FILE already exists; refusing to overwrite existing secrets" >&2
  exit 1
fi

secret() { openssl rand -hex "$1"; }

umask 077
sed \
  -e "s|^PUBLIC_URL=.*|PUBLIC_URL=$PUBLIC_URL|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(secret 24)|" \
  -e "s|^MINIO_SECRET_KEY=.*|MINIO_SECRET_KEY=$(secret 24)|" \
  -e "s|^JWT_SECRET=.*|JWT_SECRET=$(secret 32)|" \
  "$ROOT_DIR/.env.production.example" > "$ENV_FILE"

echo "wrote $ENV_FILE (mode 600) for $PUBLIC_URL"
