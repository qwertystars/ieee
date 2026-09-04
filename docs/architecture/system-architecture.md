# ResQNet-SAGE System Architecture

## Scope and status

**Status:** canonical architecture overview for the active brownfield system.

**Describes:** current architecture and accepted boundaries, with target changes called out explicitly. Detailed API/event/data semantics remain owned by executable code and [`../contracts/contract-map.md`](../contracts/contract-map.md).

Evidence baseline: `main` at `8ab15daf5c2a42f407b6d0ed75c3a8762fa13a3c`.

## System context

ResQNet-SAGE turns heterogeneous disaster observations into tenant-scoped situational state, human-reviewed alerts/decisions, operational task coordination, and auditable evidence. The architecture is deliberately local/self-hostable and supports explicit degraded/offline modes.

```text
Sources / Sensors / Simulators / Public feeds
                  |
                  v
        FastAPI ingest boundaries
                  |
        +---------+---------+
        |                   |
        v                   v
  PostgreSQL           Redpanda/Kafka
  canonical/data            |
  + PostGIS/AGE             v
  + TimescaleDB          Benthos
        ^                   |
        |                   v
        +------------- Kafka worker
                         fusion / derived processing

FastAPI <---- Redis ----> realtime fanout / auth freshness
   |
   +---- MinIO / model artifacts
   +---- Ollama (optional local LLM)
   |
   v
React/Vite PWA -- MapLibre/deck.gl
   |
 encrypted IndexedDB offline outbox
```

## Major components and why they exist

### FastAPI backend — `backend/app/`
Owns authenticated HTTP APIs, authorization dependencies, application orchestration, canonical ingress boundaries, domain queries/commands, capability reporting, and realtime endpoints.

Why: central application boundary for user/system actions while retaining explicit modules for domain logic and worker processing.

Important constraints:
- route DB access is synchronous SQLAlchemy unless explicitly isolated from async execution;
- tenant scope is derived from authenticated context;
- state changes must preserve audit/provenance requirements;
- ML/LLM results cannot directly create unauthorized high-consequence effects.

### PostgreSQL/PostGIS/AGE/TimescaleDB — primary system of record
Owns durable application state, tenant-scoped records, canonical projections, spatial queries, graph/time-series extensions, credential state, audit checkpoints, and other authoritative records defined by migrations/models.

Why: one durable authority simplifies consistency and replay compared with splitting critical state across multiple stores.

Schema authority: Alembic migrations only. Runtime table creation is not an accepted production mechanism.

### Redpanda/Kafka + Benthos + worker
Redpanda provides durable event-stream transport; Benthos provides configured normalization/routing where active; `backend/app/worker/main.py` runs the aiokafka consumer manager and processes normalized events into durable/derived state.

Why: decouples ingest acknowledgement and asynchronous processing, supports retries/replay, and allows consumer concurrency/partition scaling.

Delivery semantics: transport is at-least-once; application effects depend on tenant-scoped idempotency.

### Redis
Current responsibilities include shared ephemeral coordination such as realtime Pub/Sub/counters and credential/refresh freshness paths. Durable authorization state also exists in PostgreSQL where required by the later hardening work.

Why: fast shared coordination, not primary durable authority.

Failure rule: inability to verify protected credential validity fails closed in current auth code. Historical documentation describing general token fail-open behavior is stale.

### MinIO
S3-compatible local object storage for model artifacts and related object data.

Why: preserves self-hosted deployment and an S3-compatible replacement boundary.

### Ollama
Optional local LLM runtime for language-dependent features.

Why: enables local inference without mandatory cloud APIs. LLM absence degrades to non-LLM workflows; it must not become a safety authority.

### React/Vite PWA — `frontend/`
Owns role-appropriate operational UI, map rendering, API client behavior, visible freshness/degradation state, and offline-first field workflows.

Map stack: MapLibre + deck.gl.

Offline state: encrypted IndexedDB outbox; reconnect replay uses idempotency/conflict policy rather than silent last-write-wins.

### Sensor integration boundary
`SensorSource` plus MQTT/serial adapters provides the software seam between simulator and future physical rescue-ball/sensor implementations.

Why: keeps hardware-specific I/O outside operational domain logic and preserves provenance/calibration distinction between simulated and real sources.

## Representative workflow: observation to task

1. A simulator, source adapter, or authenticated API actor produces an observation/event.
2. Ingest validates identity, tenant/incident scope, timestamps, geometry/payload, and canonical/idempotency data.
3. Durable input is written and/or published to Redpanda according to the active path.
4. Benthos/worker processing normalizes and applies confidence/fusion logic; database effects use explicit transaction boundaries.
5. ML inference resolves the registered contract. Missing/incompatible inputs fail closed; calibration/domain limitations can force abstention.
6. Derived hypotheses/alerts/recommendations remain non-authoritative until human review.
7. If a high-consequence effect is requested, the command authorization path checks role, distinct approvers, signatures/freshness/nonce as required by the active policy.
8. State transition and approvals are committed with audit/provenance evidence.
9. Authorized clients receive updates over realtime or polling; offline clients reconcile later through the outbox policy.

## Failure path: Redis outage during protected access

1. A protected request or realtime revalidation attempts credential verification.
2. Durable revocation/quarantine state is checked where applicable.
3. If Redis cannot verify the shared credential state, current `is_token_revoked()` returns true.
4. Authorization is denied rather than silently treating the credential as valid.
5. Refresh validation/consumption also fails closed when Redis is unavailable.
6. System health/capability surfaces should report Redis degradation without converting that dependency failure into an authorization bypass.

This current behavior supersedes the older fail-open narrative still present in historical limitation text.

## Consistency and concurrency boundaries

- PostgreSQL transactions own durable relational consistency.
- Idempotency guards duplicate external/queue deliveries within their defined scope.
- High-consequence approval + effect must be atomic under the active command contract.
- Realtime delivery is not durable state authority.
- Offline outbox replay is application-level eventual synchronization and must recheck authorization/conflicts.
- Derived ML/fusion projections do not replace canonical raw/audit authority.

## Deployment topology

`docker-compose.yml` is the primary local integrated topology and includes:
- PostgreSQL database;
- Redis;
- Redpanda;
- MinIO;
- backend;
- worker;
- frontend;
- optional/profiled Benthos, Ollama, Prometheus, and Grafana depending on the selected profile.

The backend startup command runs `alembic upgrade head` before Uvicorn. The worker runs `python -m app.worker.main`.

`docker-compose.production-parity.yml` and the production-parity scripts define a stricter validation surface; passing local Compose does not by itself prove production deployment state.

## Performance architecture

Current code configures SQLAlchemy with `pool_size=20`, `max_overflow=30`, and `pool_timeout=10`. Kafka partitioning and worker concurrency were increased during throughput work, and batch ingest was added so the measured load harness could exceed 100 observations/sec.

Do not reintroduce per-observation synchronous work into the request path without measuring its effect on pool pressure, acknowledgement latency, and worker throughput.

## ML architecture and readiness boundary

The model registry/manifests pin model artifact, checksum, input/output schema, preprocessing and calibration versions. The serving contract resolves states including `available`, `abstain`, `unavailable`, and `incompatible`.

Current architectural mismatch: generic `/api/capabilities` reports model weights/ONNX runtime as `available` when manifests are validated/signed, even though the serving contract can correctly resolve the same models to `abstain` because calibration is unavailable. This is a reporting-contract gap, not evidence that serving safety checks are absent.

Target: capability reporting should expose runtime/artifact readiness separately from effective safety inference and production approval state.

## Boundaries that must not be crossed casually

- Do not move primary durable state from PostgreSQL without an accepted architecture decision and migration plan.
- Do not make Redis the only durable authority for safety-critical state.
- Do not let realtime delivery become authorization authority.
- Do not couple physical rescue-ball firmware assumptions directly into core domain workflows.
- Do not make a cloud API mandatory for a workflow that currently supports local/offline operation without a requirement forcing it.
- Do not reintroduce the removed Cloudflare runtime as a parallel implementation.

## Related canonical material

- `AGENTS.md`, `backend/AGENTS.md`, `frontend/AGENTS.md`
- [`../domain/rules-and-invariants.md`](../domain/rules-and-invariants.md)
- [`../contracts/contract-map.md`](../contracts/contract-map.md)
- [`../execution/current-state.md`](../execution/current-state.md)
- `docs/SECURITY_MODEL.md`
- `docs/OFFLINE_OPERATION.md`
- `docs/OBSERVABILITY.md`

## Update triggers

Update this document when component responsibilities, trust boundaries, durability authority, deployment topology, primary dataflow, asynchronous handoffs, or major degradation behavior changes.