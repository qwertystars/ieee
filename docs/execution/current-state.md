# ResQNet-SAGE Current State

## Evidence baseline

**Project mode:** BROWNFIELD.

**Repository:** `qwertystars/ieee`

**Baseline revision:** `8ab15daf5c2a42f407b6d0ed75c3a8762fa13a3c` on `main`.

This document separates implementation state from verification state. It does not claim that a capability is deployed in production merely because source code or tests exist.

Discovery performed for this documentation pass included the repository root, `AGENTS.md`, `README.md`, `backend/AGENTS.md`, `frontend/AGENTS.md`, `DESIGN.md`, `docker-compose.yml`, Makefile verification targets, model manifests/capability code, auth dependencies/tests, current gap/verification evidence, and representative SOTA/field evidence. The repository was sampled risk-first rather than file-by-file.

## Active architecture

Verified present:
- FastAPI backend under `backend/`;
- React/Vite PWA under `frontend/`;
- PostgreSQL 16 with PostGIS/AGE/TimescaleDB/h3 extensions in the integrated Docker topology;
- Redpanda/Kafka streaming and a dedicated aiokafka worker (`python -m app.worker.main`);
- Redis;
- MinIO;
- optional/profiled Ollama;
- MapLibre/deck.gl mapping and offline PWA/outbox behavior;
- Prometheus/Grafana configuration;
- sensor-source/MQTT/serial integration boundaries;
- ML serving/registry/contracts;
- fusion, scenario/digital-twin, optimization, audit/provenance, and evidence-gate machinery.

Confirmed absent from the active tree: the historical Cloudflare `platform/` implementation was removed in baseline commit `8ab15da` and must not be treated as an alternate current runtime.

## Verification status

### Automated software gates

Recorded evidence before the baseline commit shows later SOTA verification beyond the older Phase 1 counts. The commit history for the preceding SOTA completion records:
- backend: 688 passed;
- frontend: 52 passed;
- Playwright: 32 passed;
- final SOTA gates F1/F3/F4 approved at that verification point.

These are historical executed results associated with the prior SOTA completion, not reruns performed during this documentation task. No GitHub Actions workflow runs were attached to the baseline commit through the available connector, so this documentation pass does not claim CI verification at `8ab15da`.

Older evidence under `evidence/final-verification/` records earlier milestones such as 556 backend tests and 21 Playwright tests. Those artifacts remain useful history but are not the latest known suite size.

### Throughput

Closed relative to the old 6.32 obs/s gap.

Recorded load evidence from 2026-07-29 shows the full profile above the 100 observations/sec target (e.g. 162.79 obs/s in one final compliance artifact; later report excerpts also record >180 obs/s depending on run/profile) and the reduced profile above target. The load harness defines 100 obs/s as the threshold.

Important limitation: these are bounded test-profile results, not proof of indefinite production capacity or field-network performance.

### One-hour soak and failover

Closed for the bounded local load/chaos milestone, not for unrestricted production readiness.

Recorded evidence:
- soak duration ~3599.77 seconds;
- request success ~99.26% in the referenced full soak;
- ingest above 100 obs/s;
- measured Redis/Redpanda/MinIO and restart recovery examples under the then-active <30 s bounded target;
- backend restarted twice during the soak under host-level resource pressure, recorded rather than hidden.

The later SOTA production-parity policy is stricter: a bounded 3,600-second run cannot by itself produce `production=PASS`; longer external telemetry and prerequisites remain necessary.

### Frontend quality

The old warnings targeted in the earlier remaining-work plan were recorded as fixed: the repository contains a clock hook/state refactor path and final evidence recorded ESLint/TypeScript gates clean at that milestone. Current `frontend/AGENTS.md` keeps no-set-state-in-effect and no-`Date.now()`-during-render as active conventions.

### Authentication/Redis degradation

The prompt's older fail-open concern has been superseded by current code.

Current `backend/app/deps.py` behavior:
- `is_token_revoked()` returns true when Redis is unavailable or revocation verification errors;
- protected requests therefore fail closed;
- refresh validation/consumption fails when Redis is unavailable;
- durable credential state is queried in PostgreSQL when a DB session is supplied.

Historical `docs/KNOWN_LIMITATIONS.md` still describes Redis token validation as fail-open. That documentation is stale and should be corrected; it is not current behavioral authority.

### ML models

Partially closed.

Verified present in the current manifest:
- three named trained/pretrained model registrations for SAR flood mapping, building damage, and incident NLP;
- artifact checksums, source URLs, versions, training dataset metadata, schemas and notes;
- `validation_status="validated"` and signed manifests;
- no fabricated NLP accuracy values when unavailable.

Still not production-ready:
- all three current manifests record calibration as `DEFERRED_EXTERNAL`/unavailable and an abstention reason for safety use;
- regional deployment validation is not established by the inspected model evidence;
- no production approval/certification is established.

The serving contract is stronger than the generic capability endpoint: tests verify an uncalibrated building-damage contract resolves to `abstain`.

### ML capability reporting

Open gap.

`backend/app/api/routes/capabilities.py` currently maps validated/signed manifests with installed weights to `onnx_models: available` and `model_weights: available`. That label describes runtime/artifact availability but does not expose calibration, regional validation, or production approval. This can mislead consumers if interpreted as operational model readiness.

### Physical rescue-ball / field validation

Deferred external.

Software integration boundaries, simulator, machine field harness, hardware specification, physical test plan, and field protocol exist. The inspected field evidence explicitly records external field/hardware/agency/human claims as `DEFERRED_EXTERNAL` and states that machine PASS does not satisfy external field readiness.

No physical rescue-ball build, calibrated thermal human-detection evidence, agency field execution, or real deployment claim was established by this documentation pass.

## Known documentation/configuration drift

1. `README.md` describes the worker as APScheduler; active Compose/agent instructions use the aiokafka worker.
2. `README.md` contains old test counts.
3. `docs/KNOWN_LIMITATIONS.md` contains stale Redis fail-open text.
4. Makefile comments in the load-test section still mention a 15-connection backend DB pool; current `backend/app/db.py` configures a 20 + 30 overflow pool.
5. `DESIGN.md` contains early UUID/APScheduler/layout assumptions that are superseded by later canonical contract sections and current code.

These are documentation drift items, not reasons to revert current implementation.

## Significant current limitations

- Generic ML capability reporting does not encode production-readiness dimensions.
- Calibration datasets/artifacts remain unavailable for the current registered models under the inspected manifests, so safety inference remains abstain-bound where the serving contract requires calibration.
- Regional ML validation and real regional disaster-data evidence remain external/missing.
- Full production claim prerequisites/long observation window are not established by the bounded local evidence.
- Physical hardware and actual field validation remain external.
- The documentation corpus is large and historical; this new index/current-state layer is required so agents do not treat old milestones as present truth.

## Next safe change

`TASK-PR-001`: extend ML capability reporting to distinguish runtime/artifact availability from effective inference/readiness state while preserving existing consumers. This is bounded, directly addresses a still-open user-facing semantics gap, and can be verified without changing the broader architecture.

See [`implementation-plan.md`](implementation-plan.md) for prerequisites and acceptance criteria.

## Update triggers

Update this document after any material gap is closed/reopened, test or evidence baseline changes, architecture/deployment behavior changes, model/readiness evidence changes, or field/production claim status changes.