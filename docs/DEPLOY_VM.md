# Deploying to a single VM

This runs the whole platform on one Linux VM with Docker Compose
(`docker-compose.prod.yml`). Caddy is the only service with published ports
(80/443). It serves the built PWA, proxies `/api`, `/ws` and `/healthz` to the
backend, and gets a Let's Encrypt certificate automatically. Postgres, Redis,
Redpanda and MinIO can only be reached on the internal compose network.

> Scope: this is an operational deployment of the software. It does not
> change the claim boundaries in `docs/KNOWN_LIMITATIONS.md`. ML outputs stay
> `draft` and the uncalibrated models abstain. Field and production-readiness
> claims remain `DEFERRED_EXTERNAL`.

## 1. VM requirements

| | Minimum | Recommended |
|---|---|---|
| CPU | 4 vCPU | 8 vCPU |
| RAM | 8 GB | 16 GB (+8 GB for the optional Ollama LLM) |
| Disk | 40 GB SSD | 100 GB SSD |
| OS | Ubuntu 22.04/24.04 or Debian 12, x86_64 | |

Open inbound **22, 80, 443** only (`ufw allow OpenSSH && ufw allow 80,443/tcp && ufw allow 443/udp && ufw enable`).
For a real domain, create a DNS `A` record that points at the VM before the first start.

Docker publishes ports through its own iptables rules, which bypass `ufw`. That's
why the prod compose file publishes nothing except Caddy. Don't add `ports:` to
the other services.

## 2. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # log out/in afterwards
```

## 3. Get the code and configure

```bash
git clone <repo-url> resqnet && cd resqnet
scripts/vm/init_env.sh https://resq.example.org     # or http://<vm-ip> for an HTTP-only trial
```

`init_env.sh` writes `.env` (mode 600) with random database, MinIO and JWT
secrets. It also sets `COMPOSE_FILE=docker-compose.prod.yml`, so plain
`docker compose ...` commands target the production stack from the repo root.
Keep a copy of `.env` in your password manager. Losing `JWT_SECRET` signs
everyone out. Losing `POSTGRES_PASSWORD` locks you out of the volume.

**Choose the MinIO image.** MinIO Inc. stopped publishing container images in
October 2025, and `docker pull minio/minio` now fails. Set `MINIO_IMAGE` in
`.env` to an image you trust, pinned to a tag. The actively maintained
community fork `pgsty/minio` (for example
`pgsty/minio:RELEASE.2026-06-18T00-00-00Z`) is a drop-in replacement. The
stack won't start until this is set. MinIO only holds the model-weights
bucket here, so any S3-compatible server that accepts `MINIO_ROOT_USER`,
`MINIO_ROOT_PASSWORD` and `server /data` works.

The backend refuses to start in production with weak or default secrets, a
`*` CORS origin, or dev flags enabled (`backend/app/config.py`).

## 4. Start

```bash
docker compose up -d --build      # first build takes 10-20 min (PostGIS/AGE, torch)
docker compose ps                 # all services healthy; migrate shows "exited (0)"
curl -fsS https://resq.example.org/healthz
```

Startup order: `db` → `migrate` (`alembic upgrade head`, one-shot) →
`backend` + `worker` → `web`. If a migration fails, the stack doesn't start
(`docker compose logs migrate`).

## 5. Create the first admin

Production never seeds demo users. Create real accounts with:

```bash
docker compose run --rm backend \
  python -m app.auth.create_user --email you@example.org --role admin --org-id org_main
```

It prompts for the password (min 12 chars). Pass `-e RESQNET_USER_PASSWORD=...`
for non-interactive use. Re-running it for an existing email resets that
user's role, org and password. Roles: `admin`, `emergency_manager`,
`responder_coordinator`, `field_responder`, `shelter_manager`, `viewer`.
Everyone in one agency should share the same `--org-id`. Tenancy is enforced
on that value.

Demo data (`make seed`) is for development and should not be loaded here.

## 6. Optional capabilities

`GET /api/capabilities` reports what's available. Without the following, the
platform runs and the affected features report `unavailable` or degrade
gracefully.

- **ONNX models** (flood, damage, NLP). Weights aren't in git. Fetch them into
  `backend/data/models/` (mounted read-only into the containers) and restart:
  ```bash
  docker compose run --rm --no-deps -v "$PWD:/repo" -w /repo \
    backend python scripts/download_real_models.py --model sar   # repeat: damage, nlp
  docker compose restart backend worker
  ```
  Check each model's license before operational use (`docs/MODEL_DATA_LICENSING.md`).
- **Local LLM.** Run `docker compose --profile llm up -d ollama`, then
  `docker compose exec ollama ollama pull llama3.1:8b`.
- **Basemap.** `frontend/public/basemaps/mumbai.pmtiles` ships in the repo and
  is served by Caddy.

## 7. Operations

| Task | Command |
|---|---|
| Logs | `docker compose logs -f backend worker` (rotated, 5×10 MB per service) |
| Upgrade | `git pull && docker compose up -d --build` (migrations run automatically) |
| Restart one service | `docker compose restart backend` |
| Back up | `scripts/vm/backup.sh` → `backups/<UTC stamp>/` (pg_dump + MinIO + checksums, keeps 14) |
| Restore | `scripts/vm/restore.sh backups/<stamp>` (destructive, asks for confirmation) |
| Stop | `docker compose down` (volumes are kept; `down -v` deletes all data) |

Nightly backups via cron (`crontab -e`). Then copy `backups/` off the VM with
rclone, restic or similar:

```
15 2 * * * cd /home/<user>/resqnet && scripts/vm/backup.sh >> backups/backup.log 2>&1
```

Test a restore on a scratch VM before you rely on the backups.

Prometheus metrics (`/metrics`) are blocked at the edge. The Grafana and
Prometheus stack in `docker-compose.yml --profile full` is for development.
For production, scrape `backend:8000/metrics` and `worker:8001/metrics` from
inside the compose network.

## 8. Known single-VM trade-offs

- Everything is a single point of failure: one Postgres, one Redpanda broker
  (dev-container mode, no replication) and one MinIO. Backups are your recovery
  path. RPO is the backup interval.
- Secrets live in `.env` on disk, not in a secret manager or HSM.
- Images are built on the VM rather than pulled as signed, pinned digests.
  `docker-compose.production-parity.yml` describes the attested multi-instance
  target.
