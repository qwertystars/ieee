# Resqnet-Sage Issues

## T1 — Stale docker-compose.yml (2026-07-18)

### Problem
The `docker-compose.yml` was NOT updated by the T1 subagent. It still uses:
- `image: postgis/postgis:16-3.4` instead of `build: ./db` (Dockerfile.db)
- `DATABASE_URL: postgresql+psycopg2://...` instead of `postgresql+psycopg://...`
- Missing services: Redis, Redpanda, MinIO, Ollama, Benthos, Prometheus, Grafana
- Has a `worker` service referencing `app.worker` which doesn't exist yet

### Fix
Replace docker-compose.yml with full stack: db (build ./db with shared_preload_libraries=timescaledb,age), redis, redpanda, minio, ollama, benthos, backend, frontend, prometheus, grafana.

### Status
RESUMING subagent ses_08be05a10ffe3hk6O9ppupa5dU to fix.
