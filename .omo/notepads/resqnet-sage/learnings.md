# Resqnet-Sage Learnings

## T51 — PostgreSQL extension coexistence spike (2026-07-18)

### Outcome
All four extensions (PostGIS, Apache AGE, TimescaleDB, h3) coexist successfully on
PostgreSQL 16 in a single Docker image. No extension was dropped.

### Key findings

1. **The plan's compatibility note was outdated.** The plan said "AGE v1.8.0 requires
   PG 18.0.0" and "PostGIS 3.4 may not support PG 18." In reality:
   - AGE v1.6.0 stable supports PG 16 (tag `PG16/v1.6.0-rc0`).
   - AGE v1.7.0 stable supports PG 17 and PG 18.
   - PostGIS 3.5.x supports PG 12-18 (3.5.5+ supports PG 18 GA).
   - TimescaleDB 2.23+ supports PG 15-18.

2. **AGE must be in `shared_preload_libraries`.** Without it, `cypher()` fails with
   `ERROR: unhandled cypher(cstring) function call`. The `LOAD 'age';` command works
   as a per-session workaround but is fragile. Setting
   `shared_preload_libraries=timescaledb,age` in the Docker CMD is the clean fix.

3. **AGE functions live in `ag_catalog` schema.** Application code must set
   `search_path = ag_catalog, public` or schema-qualify all calls
   (`ag_catalog.cypher()`, `ag_catalog.agtype`).

4. **h3-pg v4.x takes a `point` type, not separate lat/lng args.**
   `h3_lat_lng_to_cell(point '(lat, lng)', resolution)` works.
   `h3_lat_lng_to_cell(40.7, -73.9, 9)` does NOT exist.
   `h3_lat_lng_to_cell` is deprecated in favor of `h3_latlng_to_cell` (same signature).

5. **AGE is not in apt — must build from source.** The build requires
   `postgresql-server-dev-16`, `flex`, `bison`, `build-essential`, `git`. The
   Dockerfile purges these after `make install` to keep the image lean.

6. **PG 16 is the right choice over PG 18.** PG 16 has the most mature AGE release
   (v1.6.0), matches the existing `docker-compose.yml`, and all three extensions have
   production-quality packages for it. PG 18 would work too, but AGE v1.8.0 for PG 18
   is still a release candidate.

### Versions installed
- PostgreSQL 16 (Debian Bookworm base)
- PostGIS 3.6.4 (from PGDG apt)
- Apache AGE 1.6.0 (built from source, `PG16/v1.6.0-rc0` tag)
- TimescaleDB 2.28.3 (from Timescale packagecloud apt)
- h3 4.2.3 (from PGDG apt)

### Files produced
- `Dockerfile.db` — custom PostgreSQL 16 image with all four extensions.
- `docs/db-extensions.md` — decision document with usage notes.
- `.omo/evidence/task-0a-resqnet-sage.txt` — full test output.

## T1 — Project skeleton + Docker Compose (2026-07-18)

### Outcome
Full Docker Compose stack boots successfully with all 10 services: db, redis,
redpanda, minio, ollama, benthos, backend, frontend, prometheus, grafana.
`curl http://localhost:8000/healthz` returns `{"ok":true}` with all service
bindings. Frontend `npm install && npm run build` exits 0.

### Key findings

1. **PYTHONPATH must be set in docker-compose.yml.** The `alembic` command
   (at `/usr/local/bin/alembic`) does not include the WORKDIR in `sys.path`.
   Without `PYTHONPATH: /app`, `alembic upgrade head` fails with
   `ModuleNotFoundError: No module named 'app'`. uvicorn works without it
   because it adds the current directory to the path, but alembic does not.

2. **Ollama image has no curl or wget.** The `ollama/ollama:latest` image is
   based on a minimal Ubuntu and does not include `curl` or `wget`. The
   healthcheck must use `ollama list` (built-in command) instead of
   `curl -f http://localhost:11434/api/tags`.

3. **Redpanda `--memory 4G` is required, not 1G.** The original T1 plan note
   was correct: 1G is below Redpanda's minimum. The `--memory 4G` flag in the
   `redpanda start` command works reliably.

4. **Redpanda internal/external address split works with `--kafka-addr` and
   `--advertise-kafka-addr` flags.** The pattern:
   ```
   --kafka-addr internal://0.0.0.0:9092,external://0.0.0.0:19092
   --advertise-kafka-addr internal://redpanda:9092,external://localhost:19092
   ```
   Internal address (`redpanda:9092`) for container-to-container, external
   (`localhost:19092`) for host access. Both work simultaneously.

5. **Backend Dockerfile builds successfully with all heavy packages.** torch
   (CPU-only from `https://download.pytorch.org/whl/cpu`), torchgeo, rasterio,
   and gdal all install correctly. The GDAL Python package is installed
   separately with `pip install gdal==$(gdal-config --version)` to match the
   system GDAL version (3.6.2 on Debian Bookworm). Total pip install time:
   ~90 seconds.

6. **`docker compose up -d --wait` requires healthchecks on all services.**
   Services without healthchecks are considered ready immediately. Services
   with healthchecks must pass before `--wait` returns. The ollama healthcheck
   initially failed because it used `curl` (not available); switching to
   `ollama list` fixed it.

7. **Frontend port 5173 can conflict with host processes.** If a Vite dev
   server is already running on the host, `docker compose up frontend` will
   fail with "address already in use". Kill the host process before starting
   the container.

### Files produced
- `docker-compose.yml` — full 10-service stack.
- `backend/` — FastAPI project with all package structure.
- `frontend/` — React + Vite + TypeScript + Tailwind project.
- `benthos/disaster_pipeline.yaml` — minimal placeholder.
- `prometheus.yml` — scrape config.
- `.env.example` — all env vars with defaults.
- `.omo/evidence/task-1-resqnet-sage.txt` — healthz + AGE test output.
