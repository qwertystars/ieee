# ResQNet-SAGE

ResQNet-SAGE is a software-first disaster situational-awareness and response-support platform for emergency managers, responder coordinators, field responders, and supporting agencies. The active monorepo uses FastAPI, a dedicated aiokafka worker, React/Vite, PostgreSQL/PostGIS/AGE/TimescaleDB/h3, Redpanda, Redis, MinIO, and optional local Ollama.

Start with [`docs/INDEX.md`](docs/INDEX.md) for the documentation router and [`docs/execution/current-state.md`](docs/execution/current-state.md) for the current implementation/verification baseline.

The historical Cloudflare `platform/` implementation is not active and has been removed.

## Quick start with Docker

```bash
cp .env.example .env
docker compose up --build
```

Core services include:
- **db** — PostgreSQL 16 with PostGIS/AGE/TimescaleDB/h3
- **backend** — FastAPI on `http://localhost:8000`
- **worker** — dedicated Kafka consumer (`python -m app.worker.main`)
- **frontend** — React/Vite PWA on `http://localhost:5173`
- **redis** — shared ephemeral coordination and credential freshness paths
- **redpanda** — Kafka-compatible event streaming
- **minio** — S3-compatible object storage

Profiled/optional services include Benthos, Ollama, Prometheus, and Grafana depending on the selected Compose profile.

The backend container runs forward Alembic migrations before Uvicorn startup. Seed the demo after the stack is healthy:

```bash
docker compose exec backend python -m app.seed.seed_demo
```

## Local development

```bash
make bootstrap
make migrate
make seed
```

Backend:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm run dev
```

## Verification

Use the commands below as executable checks, not as evergreen claims about the current HEAD:

```bash
make test
make lint
make typecheck
make build
make verify
make e2e
make load-test PROFILE=full SOAK_DURATION=<seconds>
make backup-restore-verify
```

Direct suites:

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
cd frontend && npm run test
cd frontend && npm run build
cd frontend && npx playwright test
```

Test counts change as the repository evolves, so this README does not hard-code them. See `evidence/`, `.omo/evidence/`, and `docs/execution/current-state.md` for revision-specific recorded results.

## Architecture

```text
Sources / sensors / simulator
           |
           v
      FastAPI ingest
        /      \
       v        v
PostgreSQL    Redpanda/Kafka
  system           |
 of record          v
                Benthos/worker
                    |
                    v
             fusion/derived state

FastAPI <-> Redis
   |
   +-> MinIO / model artifacts
   +-> optional Ollama
   |
   v
React/Vite PWA -> MapLibre/deck.gl
   |
 encrypted offline outbox
```

See [`docs/architecture/system-architecture.md`](docs/architecture/system-architecture.md) for responsibilities, consistency boundaries, and failure paths.

## Key safety and data rules

- tenant isolation is enforced through authenticated `org_id` scope;
- durable domain IDs are uppercase 26-character ULIDs;
- external geometry is GeoJSON;
- PostgreSQL is the primary durable system of record;
- schema changes use forward Alembic migrations;
- AI/ML/optimization outputs remain non-authoritative until required human review;
- no autonomous emergency dispatch or public-warning authority is delegated to models;
- missing required model calibration/domain evidence must abstain rather than fake readiness;
- protected authorization fails closed when credential revocation/freshness cannot be verified;
- offline safety-critical conflicts are not silently last-write-wins;
- simulation, machine tests, physical hardware, and field evidence remain distinct claim classes.

## ML readiness

The repository contains registered pretrained ONNX models and a versioned inference contract. Installed/validated weights do **not** mean operational disaster-response readiness. Current model readiness also depends on calibration, domain/regional validation, and explicit production approval. See:

- [`docs/execution/current-state.md`](docs/execution/current-state.md)
- [`docs/execution/gap-analysis.md`](docs/execution/gap-analysis.md)
- [`docs/MODEL_DATA_LICENSING.md`](docs/MODEL_DATA_LICENSING.md)
- `backend/data/models/manifests.json`

## Hardware and field status

The software contains a rescue-ball simulator and real-sensor integration boundaries through supported source/adapters. Physical rescue-ball hardware and field effectiveness are separate external milestones. Software tests must not be represented as proof of floodwater mobility, sensor calibration, thermal human detection, agency acceptance, or field readiness.

See `docs/HARDWARE_SPECIFICATION.md`, `docs/PHYSICAL_TEST_PLAN.md`, and `docs/FIELD_TRIAL_PROTOCOL.md`.

## Documentation

Use [`docs/INDEX.md`](docs/INDEX.md) instead of loading every document for every task. Important canonical documents are:

- [`docs/product/product-spec.md`](docs/product/product-spec.md)
- [`docs/domain/rules-and-invariants.md`](docs/domain/rules-and-invariants.md)
- [`docs/architecture/system-architecture.md`](docs/architecture/system-architecture.md)
- [`docs/contracts/contract-map.md`](docs/contracts/contract-map.md)
- [`docs/execution/current-state.md`](docs/execution/current-state.md)
- [`docs/execution/gap-analysis.md`](docs/execution/gap-analysis.md)
- [`docs/execution/implementation-plan.md`](docs/execution/implementation-plan.md)
- [`docs/quality/verification-strategy.md`](docs/quality/verification-strategy.md)

Existing detailed security, offline, observability, hardware, field, historical audit, and final-report documents remain part of the repository and are routed from the index.