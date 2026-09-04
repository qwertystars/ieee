# ResQNet-SAGE Documentation Index

## Purpose

This is the context router for work on ResQNet-SAGE. Start here, then load only the documents needed for the task.

**Project mode:** BROWNFIELD.

Evidence baseline for the current documentation layer: `main` at `8ab15daf5c2a42f407b6d0ed75c3a8762fa13a3c` (2026-08-04). The active runtime is the FastAPI/PostgreSQL/React system under `backend/`, `frontend/`, `docker-compose.yml`, `scripts/`, and related configuration. The historical Cloudflare `platform/` implementation was removed and is not a valid target for new work.

## Authority by subject

Do not use one global ranking for every question.

| Subject | Canonical starting point | Secondary evidence |
|---|---|---|
| Current implemented behavior | current code, migrations, runtime configuration | executed tests and evidence |
| Product intent and non-negotiables | [`product/product-spec.md`](product/product-spec.md) | accepted project requirements |
| Business rules and invariants | [`domain/rules-and-invariants.md`](domain/rules-and-invariants.md) | executable enforcement in code/tests |
| Architecture and responsibility boundaries | [`architecture/system-architecture.md`](architecture/system-architecture.md) | `docker-compose.yml`, `backend/AGENTS.md`, `frontend/AGENTS.md` |
| API/data/event/inference contract ownership | [`contracts/contract-map.md`](contracts/contract-map.md) | `DESIGN.md`, Pydantic models, Alembic migrations, route schemas/tests |
| What is implemented now | [`execution/current-state.md`](execution/current-state.md) | `docs/FINAL_REPORT.md`, evidence artifacts, current code |
| Current-to-target differences | [`execution/gap-analysis.md`](execution/gap-analysis.md) | current state + target requirements |
| What to do next | [`execution/implementation-plan.md`](execution/implementation-plan.md) | gap analysis |
| How to prove a change | [`quality/verification-strategy.md`](quality/verification-strategy.md) | Makefile, test suites, evidence scripts |
| Security details | `docs/SECURITY_MODEL.md` | current auth code/tests; current code wins on drift |
| Offline behavior | `docs/OFFLINE_OPERATION.md` | frontend outbox/service-worker code/tests |
| ML/data licensing | `docs/MODEL_DATA_LICENSING.md` | model manifests and pinned benchmark artifacts |
| Hardware boundary | `docs/HARDWARE_SPECIFICATION.md` | `docs/PHYSICAL_TEST_PLAN.md`, sensor adapter code |
| Field validation | `docs/FIELD_TRIAL_PROTOCOL.md` | `docs/FIELD_EXERCISE_HARNESS.md`, field evidence |
| Observability/operations | `docs/OBSERVABILITY.md` | Prometheus/Grafana config and scripts |
| Historical gap-closure record | `docs/FINAL_REPORT.md`, `docs/GAP_CLOSURE_AUDIT.md` | `.omo/plans/`, `.omo/evidence/`, `evidence/` |

`DESIGN.md` contains an older frozen interface contract plus later canonical-contract amendments. Treat its old sections as historical when they conflict with current code or later sections. In particular, current durable IDs are ULIDs, not UUIDs, and the active worker is the aiokafka worker at `backend/app/worker/main.py`, not APScheduler.

## Task-to-context map

| Task | Read first | Add only when needed |
|---|---|---|
| Understand current implementation | `AGENTS.md`, `execution/current-state.md`, `architecture/system-architecture.md` | subsystem `AGENTS.md`, relevant code and evidence |
| Add or change a capability | product spec, rules/invariants, implementation plan | architecture, contract map, security/offline docs if affected |
| Change an API | contract map, rules/invariants | route/schema/tests, compatibility notes, product spec if semantics change |
| Change event/streaming behavior | architecture, contract map, rules/invariants | canonical event models, consumer/producer code, replay/idempotency tests |
| Change schema/data ownership | contract map, rules/invariants | Alembic history, ORM models, migration/backup evidence |
| Change authorization | rules/invariants, `docs/SECURITY_MODEL.md`, current state | auth code/tests, realtime authorization paths, audit rules |
| Change ML/model behavior | product spec, rules/invariants, gap analysis | model manifests, serving contracts, licensing, benchmark/calibration evidence |
| Replace a component | architecture, current state, gap analysis | compatibility obligations, deployment and failure-mode docs |
| Fix a defect | current state, relevant subsystem `AGENTS.md` | failing test/evidence, rule/contract governing intended behavior |
| Performance work | current state, gap analysis, verification strategy | load harness, DB/streaming paths, evidence/load/ |
| Deploy or diagnose an incident | `AGENTS.md`, `docs/OBSERVABILITY.md`, current state | Docker/production-parity config, backup/restore and runbooks |
| Hardware integration | product spec, hardware specification, contract map | sensor source/adapters, physical test plan |
| Field-readiness claim | current state, field protocol, verification strategy | prerequisite register and field evidence; never infer field readiness from software tests |

## Evidence labels used in this documentation

- **Requirement** — required product/system behavior.
- **Accepted decision** — a design choice already established by current requirements or implementation authority.
- **Proposed decision** — recommendation awaiting implementation/acceptance.
- **Observation** — what inspected repository evidence shows.
- **Inference** — conclusion drawn from observations; reasoning is stated.
- **Assumption** — working premise requiring validation.
- **Unknown** — cannot be established from inspected repository evidence.

## Documentation update map

| Change type | Canonical docs to update |
|---|---|
| Product behavior or scope | product spec; rules/invariants; affected acceptance criteria |
| Business rule or state transition | rules/invariants; affected contract and tests |
| API/event/inference semantics | executable schema/source; contract map; compatibility notes |
| Database schema/data ownership | Alembic migration; ORM/schema source; contract map; migration evidence |
| Architecture boundary | system architecture; ADR if consequential; current state |
| Authorization/privacy | rules/invariants; `docs/SECURITY_MODEL.md`; relevant contracts/tests |
| Deployment/operations | operations docs/runbooks; current state if deployed behavior changed |
| Completed implementation task | current state; implementation plan; supporting evidence |
| New or closed gap | gap analysis; implementation plan; current state when resolved |
| Performance/reliability result | `evidence/`; current state; verification strategy if methodology changes |
| ML model/readiness change | manifests; model licensing; current state; product/gap docs if claim status changes |

## Known documentation drift to account for

The repository contains historical evidence and reports from several implementation waves. They are valuable audit records but are not always descriptions of the latest code. Current known examples:

1. `README.md` still describes the worker as APScheduler and lists older test counts.
2. `docs/KNOWN_LIMITATIONS.md` contains an older Redis fail-open description; current `backend/app/deps.py` fails protected authorization closed when revocation cannot be verified.
3. `Makefile` load-test comments still mention a 15-connection DB pool; current `backend/app/db.py` configures `pool_size=20`, `max_overflow=30` (50 total possible connections).
4. Older gap-closure evidence reports 556 backend tests / 21 Playwright tests; later SOTA work added tests and the 2026-08-04 commit history records 688 backend tests, 52 frontend tests, and 32 Playwright tests at its prior verification point. These are recorded evidence, not a claim that they were rerun during this documentation task.

When a historical document conflicts with current code, record the conflict and use current code as evidence of implemented behavior.