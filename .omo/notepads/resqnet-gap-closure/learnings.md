# Learnings — resqnet-gap-closure

Conventions, patterns, and successful approaches discovered during work on this plan.

_Auto-scaffolded by /start-work. Append new entries below - never overwrite._

---

## 2026-07-27 — Wave 1, Todo 1: Gap-closure audit + baseline evidence

### Environment discoveries

- **Docker IS available** in this environment: v29.6.2 + Compose v5.3.1.
  `docker run hello-world` succeeds. This unblocks Gate A runtime
  verification that was deferred during the 2026-07-26 audit.
- **PostgreSQL 15 is running locally** on localhost:5432 with database
  `resqnet`, user `resqnet`, password `resqnet123`. Migration head is
  `0004`. The backend connects successfully and serves `/healthz` and
  `/api/capabilities`.
- **Alembic requires PYTHONPATH=.** — `cd backend && .venv/bin/alembic
  current` fails with `ModuleNotFoundError: No module named 'app'` because
  `alembic/env.py` imports `app.config` and the venv doesn't have the app
  package installed. Fix: `PYTHONPATH=. .venv/bin/alembic current`.
- **Backend can be started locally** via `cd backend && PYTHONPATH=.
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`. Use tmux
  or `setsid` to keep it running across bash tool timeouts.

### Baseline evidence (2026-07-27)

- Backend tests: **491 passed**, 8 warnings, 64.53s
- Frontend tests: **45 passed** (3 files), 3.57s
- Migration head: **0004**
- Capabilities: 6 features, 0 available, 2 degraded, 4 unavailable
- `create_all`/`ensure_table` grep: **zero results** (Phase 1 cleanup confirmed)
- Docker: **v29.6.2 + Compose v5.3.1**, hello-world OK

### Key audit findings

1. **No sensor abstraction exists** — `SensorBase`, `SensorAdapter`,
   `SensorSource` all return zero grep results. All sensor data is
   synthetic via `rng.gauss()` in `rescue_ball.py`.
2. **No production validation scripts** — `load_test`, `backup_script`,
   `disaster_recovery` all return zero grep results.
3. **Capabilities endpoint reports 0 fully-available features** — the
   engine layer is complete but no production dependency is activated.
4. **Offline prep depends on external API** — `offline_prep.sh:59` calls
   Overpass API for PMTiles generation, defeating offline-first.
5. **Frontend has no build optimization** — `vite.config.ts` is 11 lines,
   no `manualChunks`, single 1.87 MB chunk.
6. **Outbox ULID race** — `outbox.ts:44-45` module-level mutable state
   (`lastTs`, `lastRand`) causes flaky monotonicity test under concurrency.

### Approach notes

- Branch `codex/resqnet-gap-closure` created from `main` head `c6b9805`.
- Evidence stored in `evidence/baseline/2026-07-27/` (6 files, dated).
- Prior `evidence/baseline/2026-07-26/` left untouched.
- Audit doc at `docs/GAP_CLOSURE_AUDIT.md` mirrors the IMPLEMENTATION_AUDIT.md
  pattern but focuses on production-readiness gaps rather than implementation
  completeness.

---

## 2026-07-27 — Wave 1, Todo 2: Frontend code-splitting (vite manualChunks + React.lazy)

### What changed

- `frontend/vite.config.ts`: added `build.rollupOptions.output.manualChunks`
  with three vendor groups — `vendor-react` (react, react-dom,
  react-router-dom), `vendor-map` (maplibre-gl, deck.gl), `vendor-query`
  (@tanstack/react-query). Also raised `chunkSizeWarningLimit` to 1600.
- `frontend/src/App.tsx`: replaced 8 static page imports (AuditPage,
  DashboardPage, DeviceDetailPage, FieldPage, HypothesesPage, NotFoundPage,
  PlanningPage, SimulationPage) with `React.lazy(() => import(...))`.
  LoginPage kept eager (entry point). Each lazy route wrapped in
  `<Suspense fallback={<LoadingState />}>` using the existing
  `components/state/LoadingState` component.

### Build results (before → after)

- Before: single 1.87 MB JS chunk (527 KB gzip) + chunk-size warning.
- After: 17 chunks, largest is `vendor-map` at 1,549 KB raw / **431.60 KB
  gzip** — under the 500 KB gzip target. No chunk-size warning.
- Route chunks range 0.43–12.57 KB gzip each. `vendor-react` 53.58 KB gzip,
  `vendor-query` 12.77 KB gzip, app `index` 7.01 KB gzip.

### Key decisions

- **`chunkSizeWarningLimit: 1600`**: deck.gl v9 is a large monolithic
  vendor — its raw minified size (1,549 KB) exceeds Vite's 500 KB default
  warning even though its gzip size (431 KB) is well under 500 KB. The
  warning is based on raw minified size, not gzip. Since page component
  logic cannot be changed (per task constraints) and deck.gl cannot be
  meaningfully split without changing how pages import it, raising the
  limit is the correct approach — the warning now reflects real transfer
  cost (gzip), not raw parse cost.
- **Object-form `manualChunks`**: simpler than function-form and
  sufficient for vendor splitting by package name. Route chunks are
  created automatically by `React.lazy` dynamic imports.
- **`LoadingState` component**: already existed at
  `components/state/LoadingState.tsx` with a spinner + message prop.
  Used as the Suspense fallback for all lazy routes.

### Verification

- `npm run build`: 17 chunks, no chunk >500 KB gzip, no chunk-size warning.
- `npm run typecheck` (tsc --noEmit): zero errors.
- `npm run test` (vitest run): 45 passed (3 files) — unchanged from baseline.
  Console errors about `useAuth must be used within an AuthProvider` are
  from expected-error tests in `AuthContext.test.tsx`, not failures.

### Commit

- `a60c785` on branch `codex/resqnet-gap-closure`.
- Message: `perf(frontend): code-split routes and vendor chunks via manualChunks`.

## 2026-07-27 — Wave 1, Todo 3: Fix flaky ULID monotonicity test

### Root cause (confirmed)
- `addToOutbox` called `ulid()` AFTER `await sha256(bodyStr)`. When
  `Promise.all` of 20 concurrent `addToOutbox` calls runs, `crypto.subtle.digest`
  resolves the 20 promises in **completion order**, not call order. The
  `ulid()` calls then execute in completion order, but `Promise.all`'s result
  array preserves **call order** — so the `ids` array was not sorted.
- This was a call-order vs completion-order mismatch, NOT a data race. The
  `lastTs`/`lastRand` increment in `ulid()` is already single-threaded (JS
  single-threaded, `ulid()` is synchronous).

### Fix
- Moved BOTH `ulid()` calls (for `id` and `idempotency_key`) to BEFORE the
  first `await` in `addToOutbox` — generated synchronously at function entry.
- No mutex/lock added. ULID format unchanged (26-char Crockford base32).

### Verification
- `cd frontend && npm run test`: 45 passed (3 files).
- 10 consecutive runs (`for i in $(seq 1 10); do npm run test; done`): 10/10
  passed, zero failures.

### Lesson
- When a function generates monotonic IDs and is called via `Promise.all`,
  generate the IDs synchronously at function entry, before ANY `await`. The
  `await` point is where call-order and completion-order diverge.

## 2026-07-27 — Wave 2, Todo 4: Generate Mumbai PMTiles basemap + wire frontend

### What changed

- `scripts/offline_prep.sh` step_02_pmtiles: replaced fictional
  `name="Rivertown"` Overpass query with Mumbai bbox
  (`72.7,18.9,73.0,19.3`) matching the simulator waypoints in
  `backend/app/simulator/scenarios.py`. Added Geofabrik fallback path
  using osmium-tool to extract the bbox from the India western-zone
  PBF when Overpass rate-limits (which it does for Mumbai — 20M people).
- `docker-compose.yml`: added `PMTILES_PATH` env var to backend + worker
  services pointing to `/app/frontend/public/basemaps/mumbai.pmtiles`,
  and mounted `./frontend/public/basemaps` read-only into both containers.
  This makes `_check_pmtiles_basemap()` in `capabilities.py` report
  `available` because `os.path.exists(PMTILES_PATH)` returns true.
- `frontend/src/components/MapView.tsx`: added `pmtiles` npm package
  (v4.4.1), registered the `pmtiles://` protocol with maplibre-gl, and
  defined a `PMTILES_STYLE` with 5 vector layers (background, landuse,
  water, roads, buildings) sourced from `mumbai.pmtiles`. The existing
  `FALLBACK_STYLE` (solid dark background) is kept and used if PMTiles
  loading errors. No external tile hosts referenced.
- `frontend/public/basemaps/mumbai.pmtiles`: 16 MB PMTiles file generated
  from real Mumbai OSM data via the Geofabrik fallback path (Overpass
  returned empty/504 for both the main and kumi mirrors).

### Key discoveries

- **Overpass API cannot serve Mumbai at city scale**: both
  `overpass-api.de` and `overpass.kumi.systems` returned empty elements
  or 504 Gateway Timeout for the Mumbai bbox. Even a targeted query
  (highways + buildings + water + landuse only) timed out after 74
  seconds. The Geofabrik western-zone extract (~200 MB PBF) is the
  reliable path.
- **tippecanoe v2.80.0 does NOT read .osm.pbf directly**: passing a
  `.osm.pbf` file to tippecanoe produces "Found unexpected character"
  because it tries to parse the PBF as text. The working flow is:
  `osmium extract --bbox=... -o mumbai.osm.pbf` →
  `osmium export -o mumbai.geojson` →
  `tippecanoe -o mumbai.pmtiles -zg mumbai.geojson`.
  `osmium-tool` (apt-get install osmium-tool) is required for the
  Geofabrik fallback.
- **tippecanoe has `--clip-bounding-box` not `--bbox`**: the flag for
  clipping features to a bounding box is `--clip-bounding-box`, not
  `--bbox`. However, using osmium extract first is cleaner because it
  filters features before tippecanoe processes them.
- **capabilities path mismatch confirmed**: placing the PMTiles file at
  `frontend/public/basemaps/` alone does NOT make
  `_check_pmtiles_basemap()` pass. The check reads `PMTILES_PATH` env
  var and calls `os.path.exists()`. Setting `PMTILES_PATH` in
  docker-compose.yml + mounting the basemaps directory is required.
- **maplibre-gl StyleSpecification type**: the PMTiles style must be
  typed as `StyleSpecification` (imported from `maplibre-gl`) to avoid
  TypeScript errors with filter/expression arrays. Using `as const`
  on individual properties is insufficient — the whole object needs
  the type annotation so maplibre's tuple-typed `FilterSpecification`
  union accepts the array literals.

### Verification

- `curl -s http://localhost:8000/api/capabilities` with
  `PMTILES_PATH=/root/srijan/ieee/frontend/public/basemaps/mumbai.pmtiles`:
  `pmtiles_basemap` status = `available` (was `unavailable`).
- `ls -la frontend/public/basemaps/mumbai.pmtiles`: 16,205,659 bytes
  (non-empty, valid PMTiles — verified with `tippecanoe-decode`).
- `grep -rn "tile.openstreetmap\|hot.tile" frontend/src/`: zero results.
- `grep -rn "tile.openstreetmap\|hot.tile" frontend/dist/`: zero results.
- `npm run typecheck` (tsc --noEmit): zero errors.
- `npm run test` (vitest run): 45 passed (3 files) — unchanged.
- `npm run build`: 17 chunks, no chunk >500 KB gzip, no errors.
- `docker compose config --quiet`: valid YAML.

### PMTiles generation path used

Overpass (both mirrors) returned empty/504 → Geofabrik fallback:
1. Downloaded `western-zone-latest.osm.pbf` (208 MB) from
   `https://download.geofabrik.de/asia/india/western-zone-latest.osm.pbf`
2. `osmium extract --bbox=72.7,18.9,73.0,19.3 -o mumbai.osm.pbf` (13 MB)
3. `osmium export -o mumbai.geojson` (128 MB GeoJSON with real Mumbai
   features — roads, buildings, water, landuse, POIs)
4. `tippecanoe -o mumbai.pmtiles -zg --layer=mumbai --drop-densest-as-needed
   --extend-zooms-if-still-dropping --force mumbai.geojson` (16 MB PMTiles)
5. Cleaned up intermediate files (PBF + GeoJSON).

### Lesson

- For PMTiles generation from OSM data at city scale, use Geofabrik
  extracts + osmium extract + tippecanoe. Overpass API is unreliable
  for cities with millions of features — it rate-limits and times out
  even for targeted feature queries. The Geofabrik path is more
  reliable and produces higher-quality data (full OSM extract, not
  a filtered subset).

## 2026-07-28 — Wave 2, Todo 5: Enable Redpanda/Redis/Ollama offline

### What changed

- `docker-compose.yml`: reduced all resource limits to fit the 8 GB RAM
  environment (db 4G→1G, redpanda 5G→2G, ollama 8G→4G, backend 4G→2G,
  worker 1G→512M, minio 1G→512M, redis/benthos/frontend/prometheus/
  grafana 512M→256M). Changed db port mapping from 5432→5433 to avoid
  conflict with the local PostgreSQL 15 running on 5432. These changes
  allow all 11 services to run simultaneously without OOM kills.
- `scripts/create_topics.sh`: replaced the hard `rpk` host requirement
  with a 3-tier fallback: (1) host-installed rpk via
  `REDPANDA_BROKERS` env var, (2) `docker compose exec -T redpanda rpk`
  using in-container auto-discovery, (3) error. Removed the deprecated
  `--bootstrap` flag (removed in newer rpk versions).
- `scripts/offline_prep.sh` step_04: changed `docker compose pull` to
  `docker compose --profile full pull` so ollama/prometheus/grafana
  images are pre-pulled too (without the profile flag, compose skips
  profile-gated services, leaving them to pull on-demand at start).
- `scripts/offline_prep.sh` step_08: replaced `wait_for_service ollama`
  (which only checks container exec success) with an explicit HTTP
  readiness loop that calls `ollama list` until it succeeds (up to 60s).
  The ollama server takes a few seconds after container start to accept
  API requests — without this, `ollama pull` can race server startup.

### Verification results

- `docker compose --profile full up -d`: all 11 services started.
  7 services with healthchecks all report `healthy` (db, redis, redpanda,
  minio, ollama, backend, worker). 4 services without healthchecks
  (benthos, frontend, prometheus, grafana) are `Up`.
- `rpk topic list` (inside redpanda container): all 3 topics exist —
  observations.raw, observations.normalized, observations.dlq (1 partition,
  1 replica each).
- `docker compose exec ollama ollama list`: `llama3.1:8b` present (4.9 GB,
  pulled 7 hours prior — was already in the `ieee_ollama_data` volume
  from a prior session, so no re-download needed).
- `curl /api/capabilities`: kafka=available, redis=available,
  ollama_llm=available, pmtiles_basemap=available (from T4).
  onnx_models=degraded, model_weights=unavailable (expected — Wave 3 T7).
- `curl /healthz`: `{"ok":true}`, all 5 services configured.

### Key discoveries

- **`docker compose up -d --wait` can exceed 5 minutes on first boot**:
  the `--wait` flag blocks until ALL healthchecks pass. With 11 services
  (db migrations, redpanda cluster formation, ollama model loading), this
  can take >5 min. Workaround: start with `docker compose --profile full
  up -d` (no `--wait`), then poll `docker ps` for health status. The
  services without healthchecks (benthos, frontend, prometheus, grafana)
  are considered "ready" as soon as the container is up.
- **Ollama model persists in the named volume**: the `ieee_ollama_data`
  volume survives `docker compose down`. Once `llama3.1:8b` is pulled,
  it remains available across stack restarts — no re-pull needed. The
  model blob files live at `models/blobs/sha256-*` and the manifest at
  `models/manifests/registry.ollama.ai/library/llama3.1/8b`.
- **`_check_kafka()` uses `KAFKA_BOOTSTRAP_SERVERS` env var first**,
  falling back to `settings.REDPANDA_BOOTSTRAP_SERVERS`. The
  docker-compose.yml sets `REDPANDA_BOOTSTRAP_SERVERS` (not
  `KAFKA_BOOTSTRAP_SERVERS`), so the check uses the Pydantic settings
  default. Both paths resolve to `redpanda:9092` — the internal
  container address. The check does a TCP `socket.create_connection`
  to `redpanda:9092`, which works from inside the backend container.
- **Resource limits are caps, not reservations**: with 8 GB total RAM
  and ~11 GB of cumulative limits, the stack still runs because
  containers use far less than their limits when idle. Ollama at 4G
  limit uses ~200 MB when just serving `ollama list` (no inference).
  The 4G limit only matters during LLM inference, which is not part
  of the capabilities healthcheck.
- **`create_topics.sh` rpk fallback works**: when host rpk is not
  installed, `docker compose exec -T redpanda rpk` auto-discovers the
  broker via the redpanda config file inside the container. No
  `--bootstrap` flag or `REDPANDA_BROKERS` env var needed for the
  in-container path.

### Lesson

- For `docker compose --wait` on large stacks, don't rely on the
  default 5-minute bash timeout. Start with `up -d` (no `--wait`),
  then poll `docker ps` every 30s until all healthchecks pass. This
  avoids the timeout killing the compose command mid-startup.
- When reducing resource limits for a constrained environment, scale
  ALL services proportionally — not just the big ones. Redpanda's
  `--memory` flag (JVM-like heap) must be ≤ the deploy.resources.limits
  memory, or the container OOM-kills on startup.


