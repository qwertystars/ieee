# Disaster Situational Awareness & Response Platform

Real-time situational awareness and response coordination for urban flooding (v1 demo
region: **Rivertown**). Monorepo: FastAPI backend + APScheduler worker + React/Vite
frontend on PostgreSQL/PostGIS with Apache AGE, TimescaleDB, and h3 extensions.

See [`DESIGN.md`](./DESIGN.md) for the frozen interface contract.

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

Services:
- **db** — PostgreSQL 16 + PostGIS + AGE + TimescaleDB + h3 on `localhost:5432`
- **backend** — FastAPI on http://localhost:8000 (docs at `/docs`, health at `/healthz`)
- **worker** — APScheduler ingestion loop
- **frontend** — Vite dev server on http://localhost:5173
- **redis** — token denylist, rate limiting, caching
- **redpanda** — Kafka-compatible event streaming
- **minio** — S3-compatible object storage for model weights
- **ollama** — local LLM inference (llama3.1:8b)

The backend runs `alembic upgrade head` on start to create all tables and the PostGIS
extension. Seed the demo scenario after the stack is up:

```bash
docker compose exec backend python -m app.seed.seed_demo
```

## Deploying to a VM

The quick start above is a development stack (Vite dev server, internal ports
published, demo users). For a real server use the hardened single-VM stack —
Caddy with automatic HTTPS, only ports 80/443 exposed, production config
validation, no demo users:

```bash
scripts/vm/init_env.sh https://resq.example.org   # writes .env with fresh secrets; then set MINIO_IMAGE in it
docker compose up -d --build                      # uses docker-compose.prod.yml via .env
```

Full procedure, first-admin creation, backups and upgrades: [docs/DEPLOY_VM.md](docs/DEPLOY_VM.md).

## Quick start (local dev)

Prerequisites: PostgreSQL 16 with PostGIS at `localhost:5432` (db: `resqnet`,
user: `resqnet`, pw: `resqnet123`).

```bash
# Bootstrap Python venv + npm deps
make bootstrap

# Run migrations
make migrate

# Seed demo data
make seed

# Start backend (terminal 1)
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload

# Start frontend (terminal 2)
cd frontend && npm run dev
```

Or use the Makefile shortcuts:

```bash
make verify   # migrate + seed + test + build in sequence
make demo     # run the Phase 1 demo script
```

## Demo logins

Password `demo1234` for all accounts. Org ID: `org_demo`.

| Email | Role | Capabilities |
|---|---|---|
| `admin@demo.disaster` | admin | Full access, emergency overrides, audit |
| `emergency_manager@demo.disaster` | emergency_manager | Approve alerts, dispatch tasks, sensitive data |
| `responder_coordinator@demo.disaster` | responder_coordinator | Dispatch tasks, operational data |
| `field_responder@demo.disaster` | field_responder | Task execution, exact rescue locations |
| `shelter_manager@demo.disaster` | shelter_manager | Shelter ops, assigned-person info |
| `viewer@demo.disaster` | viewer | Ward-level aggregation only, no PII |

## Testing

```bash
# Backend tests (491 tests)
cd backend && .venv/bin/python -m pytest tests/ -q

# Frontend tests (45 tests)
cd frontend && npm run test

# Lint and typecheck (if tools installed)
make lint
make typecheck
```

## Architecture

```
                    ┌─────────────┐
                    │  Frontend   │  React + Vite + MapLibre
                    │  (PWA)      │  Service worker + IndexedDB outbox
                    └──────┬──────┘
                           │ REST + WebSocket
                    ┌──────▼──────┐
                    │   Backend   │  FastAPI + JWT auth + RBAC + ABAC
                    │  (FastAPI)  │  Progressive precision PII redaction
                    └──┬──┬──┬──┬─┘
           ┌───────────┘  │  │  └───────────┐
           ▼              ▼  ▼              ▼
     ┌──────────┐  ┌─────────┐ ┌────────┐ ┌──────────┐
     │PostgreSQL│  │ Redpanda│ │ Redis  │ │  MinIO   │
     │+PostGIS  │  │ (Kafka) │ │        │ │ (S3)     │
     │+AGE      │  └────┬────┘ └────────┘ └──────────┘
     │+Timescale│       │
     │+h3       │  ┌────▼────┐
     └──────────┘  │ Benthos │  Normalize + dedup + route
                   └────┬────┘
                   ┌────▼────┐
                   │  Worker │  APScheduler ingestion
                   └─────────┘
```

### Backend layout

```
backend/app/
  api/routes/    — Hono route handlers (auth, observations, alerts, tasks, simulator, ...)
  auth/          — JWT, RBAC (6 roles), ABAC engine, emergency overrides
  middleware/    — request_id, org_context (server-side org_id), error_handler
  lib/           — ulid, time, audit (hash-chained), privacy (progressive precision)
  models/        — SQLAlchemy ORM (observation, entities, hypotheses, scenarios, events)
  simulator/     — rescue-ball digital twin, fault injection, simulation engine
  perception/    — ML model serving (ONNX), SAR flood mapping, damage assessment, NLP
  fusion/        — confidence vectors, freshness decay, reliability, calibration, world state
  knowledge/     — Apache AGE temporal crisis knowledge graph
  ingestion/     — CAP, SensorThings, OGC Features, STAC, HDX adapters + federation
  streaming/     — Kafka producer + consumer
  seed/          — demo scenario data (Rivertown cyclone-flood)
```

### Frontend layout

```
frontend/
  public/        — manifest.json, service worker (sw.js), icons
  src/
    lib/outbox.ts     — IndexedDB outbox with conflict-aware replay
    components/       — MapView, dashboards, forms
    pages/           — command center, field responder, shelter manager
```

## Key features

- **Alert-to-task loop**: draft alerts from sensors/simulators, human approval, task dispatch
- **Rescue-ball simulator**: deterministic digital twin with 10 fault injection types
- **Progressive precision**: same entity serialized differently per viewer role
- **Offline-first PWA**: service worker caching + IndexedDB outbox with conflict resolution
- **Hash-chained audit**: tamper-evident event log with `prev_hash`/`hash` chain
- **Capabilities endpoint**: `GET /api/capabilities` reports runtime feature availability
- **Graceful degradation**: every external dependency has a fallback path

## Field modules and hardware

Beyond the platform, the repo carries the field team's modules and the drone firmware:

- [`modules/`](modules/README.md) holds the BLE mesh localization service, the Flutter mesh app,
  the AI route engine and thermal drone server, and thermal image analysis. The mesh
  service feeds the frontend's **Rescue** page (`/rescue`).
- [`hardware/drone/`](hardware/drone) is the ESP32 flight controller (PlatformIO). Build it with
  `cd hardware/drone && pio run -e flight`, or `-e esc_test` for the ESC bench tool.

## Documentation

| Document | Description |
|---|---|
| [docs/PHASE1_DEMO.md](docs/PHASE1_DEMO.md) | Step-by-step demo walkthrough |
| [docs/SIMULATOR.md](docs/SIMULATOR.md) | Rescue-ball simulator usage and fault injection |
| [docs/OFFLINE_OPERATION.md](docs/OFFLINE_OPERATION.md) | PWA, service worker, IndexedDB outbox |
| [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) | Auth, RBAC, ABAC, tenancy, PII redaction |
| [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | Blockers, disclaimers, activation steps |
| [docs/offline-prep.md](docs/offline-prep.md) | Offline pre-deployment preparation |
| [docs/db-extensions.md](docs/db-extensions.md) | PostgreSQL extension coexistence notes |
| [DESIGN.md](DESIGN.md) | Frozen interface contract |

## Make targets

| Target | Description |
|---|---|
| `make bootstrap` | Install Python deps + npm deps |
| `make migrate` | Run `alembic upgrade head` |
| `make seed` | Seed demo data (Rivertown scenario) |
| `make test` | Run pytest (skips pre-existing broken test) |
| `make build` | Build frontend (`npm run build`) |
| `make demo` | Run the Phase 1 demo script |
| `make verify` | migrate + seed + test + build in sequence |
| `make docker-up` | Start full Docker stack |
| `make docker-up-full` | Start stack with observability (Prometheus + Grafana) |

## Environment

See [`.env.example`](.env.example) for all configuration variables. Key settings:

- `DATABASE_URL` — PostgreSQL connection string
- `JWT_SECRET` — must be 32+ chars outside development
- `CORS_ORIGINS` — comma-separated origins or `*` for dev
- `OLLAMA_BASE_URL` — local LLM endpoint
- `PMTILES_PATH` — offline basemap tiles
- `KAFKA_BOOTSTRAP_SERVERS` — event streaming broker
- `OTEL_EXPORTER` — set to `none` to disable, or OTLP endpoint
- `VITE_MESH_API_BASE` — BLE mesh localization service for the Rescue page (default `http://<host>:8001`)

## License

Model weights are downloaded from HuggingFace under the `resqnet` organization.
See [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) for model licensing details.
