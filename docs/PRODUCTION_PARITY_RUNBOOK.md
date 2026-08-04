# Production-Parity Deployment and Horizontal Recovery

This runbook is the Task 12 software gate. It proves a bounded, production-like
deployment contract only. It does not claim field readiness, production SLO
success, or 30-day operational evidence.

## Locked policy

`config/production-parity.json` is normative. The finite run is exactly 3,600
seconds (`BOUNDED_PARITY`), with 50 concurrent operators and 100 acknowledged
ingest events per second. A run must report p50, p95, and p99 for API reads and
dashboard reads, CPU/memory/database/queue saturation, availability, failure
budget, queue age, failover time, and acknowledged-effect reconciliation.

The gate requires availability >=99.9%, failure budget <=0.1%, API-read p95
<=500 ms, dashboard p95 <=2 s, CPU <=70%, memory <=75%, database connections
<=80%, queue-age p95 <=60 s, failover <=30 s, zero acknowledged-event loss,
zero duplicate acknowledged effects, and identical reconciliation hashes from
both backend instances. The 3,600-second policy is never reduced to make a
local run pass.

`PASS` is evidence that the declared fixture or external run met its own gate;
it is not a production or field claim. A missing external driver, secret
custody, TLS material, or one-hour runtime is `DEFERRED_EXTERNAL` (exit 2).

## Topology and release ordering

`docker-compose.production-parity.yml` has one `migrate` job, two stateless
backend instances (`backend_a` and `backend_b`), a TLS-terminating HAProxy
entrypoint, a shared PostgreSQL/Redis/Redpanda/MinIO authority, and a shared
consumer group. Backend instances never run migrations on startup. Traffic is
admitted only after `/healthz/deep` returns HTTP 200; `/healthz` remains the
process liveness probe. An unknown dependency is not ready.

The local Compose dependency containers are single-host fixtures. Production
HA requires managed PostgreSQL quorum, Redis Sentinel or Cluster, Redpanda
replication factor 3, and four-node MinIO erasure coding. Those dependency
replicas are an external attestation prerequisite and are never inferred from
the local fixture.

Production image variables must resolve to attested `@sha256:` references. The
version references in `production-parity.json` are development documentation,
not release artifacts. The local `docker-compose.yml` is a development stack;
its explicitly documented dev server/profile behavior must not be promoted as
the parity deployment.

Migrations follow expand, migrate, backfill, contract ordering. An interrupted
migration removes the release from service, preserves the durable ledger, and
fails the release. Rollback is to the previous attested application image only
after the forward-compatible schema check. Destructive schema downgrade is
forbidden because canonical events, idempotency rows, audit heads, and tenant
data cannot be removed by release rollback.

## Secrets and TLS

The secret manager injects `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, MinIO
credentials, explicit HTTPS `CORS_ORIGINS`, all image digests, and
`TLS_BUNDLE_FILE`. The Compose `jwt_secret` and `tls_bundle` secrets are never
committed, logged, or placed in an image. Rotate by replacing the external
secret and performing a rolling restart; verify readiness before draining the
old instance. Internal database, cache, broker, object-store, and metrics
ports remain private to the Compose network.

## Queue backpressure and reconciliation

The durable acknowledgement boundary is the raw-event ledger commit or an
acknowledged DLQ handoff. Consumers do not commit offsets for buffered,
unflushed, or unacknowledged work. The parity policy caps in-memory buffering at
100 messages, retries transient errors three times, bounds queue age at 60 s,
and rejects or retries admission without acknowledging when saturated.

The traffic driver records every acknowledged input and computes an ordered
SHA-256 over `(org_id, source_id, external_id, raw canonical hash,
observation payload hash)`. It compares the two instance observations after
rolling restart and duplicate delivery. Duplicate delivery must produce one
durable effect, not one effect per delivery; altered payloads for the same key
must be a conflict. Audit-chain verification is separate from effect
cardinality so harmless duplicate delivery cannot be mistaken for duplicate
acknowledged effects.

## Commands

Static contract and fixture scenarios:

```bash
scripts/run_production_parity.sh --mode fixture --scenario rolling-restart --report evidence/sota/task-12-rolling.json
scripts/run_production_parity.sh --mode fixture --scenario queue-saturation --report evidence/sota/task-12-queue.json
scripts/run_production_parity.sh --mode fixture --scenario dependency-loss --report evidence/sota/task-12-dependency.json
scripts/run_production_parity.sh --mode fixture --scenario migration-interrupt-rollback --report evidence/sota/task-12-failure.json
```

The required one-hour external command is:

```bash
scripts/run_production_parity.sh --instances 2 --operators 50 --ingest-rate 100 --duration 3600 --report evidence/sota/task-12-happy.json
```

An externally supplied driver is required for the real path:

```bash
RESQNET_PARITY_EXECUTE=true \
RESQNET_PARITY_DRIVER='/opt/resqnet/bin/task12-driver' \
scripts/run_production_parity.sh --instances 2 --operators 50 --ingest-rate 100 --duration 3600 --report evidence/sota/task-12-happy.json
```

The driver must emit JSON with `latency`, `saturation`, `availability`,
`failure_budget`, `queue_age_p95_seconds`, `failover_seconds`, and
`reconciliation` containing identical backend hashes and zero acknowledged
loss/duplicate effects. The script starts the parity Compose project, waits for
all health gates, invokes the driver, records evidence, and always tears down
the temporary project.

## Adversarial release checks

The focused tests execute rolling restart, migration interruption/rollback,
capacity, readiness/liveness, queue saturation, dependency loss, partial
instance failure, and acknowledged-event-loss fixtures. The migration failure
must exit nonzero with `release_status=UNSAFE_RELEASE` and
`acknowledged_event_loss=0`. The acknowledged-loss fixture must fail the gate;
it is never hidden by a successful API or broker response.

## External boundary

The existing `evidence/load/2026-07-29-full.json` is single-machine and uses
the older 99% target. It remains supporting load evidence only. It is not
reused as horizontal recovery, production SLO, 30-day telemetry, or field
readiness evidence. External production traffic, secret-manager custody,
TLS/certificate rotation, multi-node broker/database durability, and the
required one-hour driver execution remain independently attestable prerequisites.
