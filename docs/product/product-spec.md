# ResQNet-SAGE Product Specification

## Purpose and status

**Status:** canonical product-intent document for the current production-readiness phase.

**Describes:** target behavior and accepted constraints. Implementation status belongs in [`../execution/current-state.md`](../execution/current-state.md).

ResQNet-SAGE is a software-first disaster situational-awareness and response-support platform for emergency managers, incident commanders, responder coordinators, field responders, and supporting disaster-response agencies. It combines simulated and real-device observations, public/geospatial/event feeds, confidence and fusion processing, human-reviewed alerts and recommendations, task coordination, mapping, offline synchronization, scenario/digital-twin analysis, optimization, provenance, and evidence-backed verification.

The present objective is to harden the existing system, not redesign it. Production-readiness claims must be narrower than software correctness claims, and field-readiness claims must remain separate from both.

## Accepted product boundaries

- The canonical runtime remains Python/FastAPI + PostgreSQL/PostGIS + React/Vite, with Redpanda/Kafka, Redis, MinIO, local Ollama support, and the existing Docker-based deployment model.
- PostgreSQL is the primary system of record.
- The removed Cloudflare `platform/` implementation is not an active architecture and must not be reintroduced without a new accepted architecture decision.
- Physical rescue-ball hardware is outside software-only scope until real devices exist.
- The platform is decision support, not autonomous emergency command authority, medical authority, or certification evidence.
- All safety-relevant AI output remains subject to human review and the applicable dual-control/authorization policy before high-consequence effects.
- Offline and degraded operation are product requirements, not optional enhancements.
- Simulation, machine fixtures, shadow exercises, and physical/field observations must remain distinguishable in data and claims.

## Actors

| Actor | Product responsibility |
|---|---|
| Administrator | tenant/system administration within authorized scope; cannot bypass tenant isolation, audit, or high-consequence controls |
| Emergency manager | reviews situational evidence, approves appropriate alerts/decisions, participates in high-consequence dual control |
| Responder coordinator | coordinates assignments/resources and participates in high-consequence dual control |
| Field responder | receives/updates authorized tasks, contributes field observations, works under degraded/offline conditions |
| Shelter manager | manages shelter-operational information within role scope |
| Viewer | receives only authorized public/aggregated information |
| Sensor/source adapter | produces observations with source/provenance identity; cannot become operational authority |
| ML/LLM component | produces evidence, predictions, drafts, or explanations; never independently dispatches or authorizes emergency action |
| External agency/system | exchanges data/contracts according to explicit integration and authorization boundaries |

## Requirements

### REQ-001 — Human authority for consequential action
AI-generated alerts, recommendations, predictions, optimizations, and summaries must not directly dispatch responders, issue public warnings, commit resources, or otherwise create high-consequence operational effects without the required authorized human approval.

Acceptance:
- machine-generated operational content is distinguishable from approved/official content;
- prohibited transitions cannot be triggered by an ML/LLM principal alone;
- high-consequence commands exercise the current authorization/dual-control policy;
- audit records identify the human actors and evidence lineage.

### REQ-002 — Tenant isolation
Every tenant-scoped read, write, realtime delivery, background operation, replay, and audit query must preserve `org_id` isolation. Client-supplied organization identity must not override the authenticated server-side tenant context.

Acceptance:
- cross-tenant authorization tests fail closed;
- realtime and offline replay preserve tenant scope;
- idempotency scope includes tenant identity where applicable.

### REQ-003 — Provenance and auditability
Operationally meaningful facts, predictions, decisions, and state changes must retain sufficient provenance to reconstruct what input, model/configuration, actor, and decision path produced them. Audit history is tamper-evident and must not be silently rewritten.

### REQ-004 — Honest capability/readiness reporting
Runtime presence, trained-model availability, calibration, regional validation, and production approval are distinct states. A component must not report a stronger capability state than its evidence supports.

For ML, the product must be able to distinguish at least:
1. runtime unavailable/available;
2. placeholder/synthetic vs trained weights;
3. calibrated vs uncalibrated;
4. regionally validated vs not regionally validated;
5. production-approved vs not production-approved.

Successful ONNX execution alone is not production-readiness evidence.

### REQ-005 — Safety abstention
When a safety-relevant model lacks a valid contract, required artifact, calibration, modality, or supported-domain evidence, the system must abstain or report unavailability according to the canonical inference contract rather than fabricate a result or silently fall back to a mock.

### REQ-006 — Deterministic, idempotent ingestion
Observation/event ingestion must tolerate at-least-once delivery while applying each logical external event at most once within its defined idempotency scope. Replaying equivalent input must not duplicate effects; conflicting payloads for an existing idempotency key must be detectable.

### REQ-007 — Observation throughput
The defined load harness must sustain at least 100 observations/events per second for the production-readiness bounded-load profile without evidence of loss, duplicate application, tenant leakage, or data corruption.

Performance evidence must state the workload, duration, revision, environment/profile, measurement method, and limitations.

### REQ-008 — Operator responsiveness
For the bounded production-readiness profile:
- 50 concurrent operators;
- dashboard p95 <= 2 seconds;
- API read p95 <= 500 ms;
- request success/availability threshold defined by the active verification policy;
- measured failover/recovery behavior, not an assumed constant.

Longer-term production SLO claims require the observation window defined by the production-parity policy and cannot be inferred from a one-hour local test.

### REQ-009 — Degraded/offline operation
Loss of non-critical dependencies must degrade explicitly and preserve safe core behavior where possible. Any fallback that weakens authorization, freshness, provenance, or safety semantics is prohibited unless an explicit approved break-glass rule exists and is audited.

### REQ-010 — Authentication and revocation safety
Protected authorization must fail closed when current credential validity/revocation cannot be verified. Refresh credential replay must not silently restore access. Active realtime delivery must revalidate authorization within the accepted policy window.

### REQ-011 — Forward database evolution
Schema changes use forward Alembic migrations. Runtime `create_all()`/`ensure_table()` mechanisms must not become production schema authorities. Historical destructive rollback is not assumed safe.

### REQ-012 — External geometry and durable identity
External geometry remains GeoJSON with canonical spatial storage using SRID 4326 where applicable. Durable domain identifiers remain uppercase 26-character ULIDs unless an explicitly accepted migration changes the contract.

### REQ-013 — Reproducible verification
Every meaningful behavior change must have relevant automated tests and reproducible verification. Passing claims must identify executed evidence; proposed checks must not be described as passed.

### REQ-014 — Hardware boundary
Software must preserve the `SensorSource`/adapter/provenance/calibration boundary so simulated sources can be replaced by physical MQTT/serial sources without embedding device-specific assumptions into operational domain logic.

### REQ-015 — Claim-class separation
Software correctness, bounded production-parity, research/ML quality, shadow readiness, and field readiness are separate claim classes. A PASS in one class must never automatically promote another class.

Physical hardware, regional validation, agency authorization, IRB/ethics prerequisites, human workload evidence, and actual field trials remain external prerequisites when not present.

## Core product workflows

### Observation-to-human-response
1. An authenticated API/source adapter or simulator emits an observation/event with source, incident, organization, time, and provenance.
2. The ingest boundary validates/canonicalizes it and establishes idempotency.
3. Streaming/normalization/fusion updates derived situational state under deterministic/replayable rules.
4. ML/LLM components may produce draft predictions, summaries, or recommendations only when their contract permits; unsupported safety outputs abstain.
5. Alerts/recommendations remain draft until authorized human review.
6. A high-consequence action requires the applicable human authorization/dual-control policy.
7. Resulting state changes and decisions are audited and delivered through authorized realtime/polling/offline paths.

### Offline field update and reconnect
1. A field user operates with cached authorized state.
2. Eligible mutations are queued in the encrypted offline outbox with identity/idempotency metadata.
3. Safety-critical conflicts are not silently resolved last-write-wins.
4. On reconnect, authorization/freshness is re-established and queued work is replayed under current tenant/credential rules.
5. Conflicts requiring human resolution remain visible and auditable.

### ML inference readiness
1. Runtime and registered model artifact are checked.
2. Exact model/feature/preprocessing/calibration/output contract versions are resolved.
3. Missing/incompatible artifacts fail to `unavailable`/`incompatible` as defined by the serving contract.
4. Missing required calibration/domain evidence produces `abstain` for safety output.
5. Capability reporting exposes the readiness dimensions instead of flattening them to “available.”

## Non-goals for the current phase

- Rewriting the stack or moving to a different primary database/framework.
- Recreating the removed Cloudflare implementation.
- Building or certifying physical rescue-ball hardware.
- Claiming thermal human detection from simulation.
- Claiming field reliability, regional ML validity, agency acceptance, or certification without corresponding external evidence.
- Autonomous dispatch, autonomous public warning, or removal of human safety gates.
- Unrelated visual redesign or feature expansion ahead of measurable production-readiness gaps.
- Mandatory cloud dependencies where local/self-hosted operation already satisfies the requirement.

## Current unresolved product decisions

### PD-001 — ML capability response shape
**Status:** proposed decision; implementation-ready.

Current `/api/capabilities` uses generic `available/degraded/unavailable` values and marks validated/signed model weights as `available` even when calibration is unavailable. The recommended contract is to retain generic runtime health while adding explicit ML readiness dimensions (`artifact_kind`, `training_state`, `calibration_state`, `regional_validation_state`, `production_approval_state`, and effective `inference_state`).

Impact: API compatibility must be designed so existing consumers are not silently broken. See the gap analysis and implementation plan.

### PD-002 — Production claim window
**Status:** accepted by the later SOTA plan, not proven by local evidence.

The bounded 3,600-second load/soak gate can support a bounded-parity claim but not a full production-readiness PASS. Production availability requires the longer observation window and external prerequisites defined by the active production-parity policy.

## Update triggers

Update this document when product scope, safety authority, accepted SLO definitions, actor semantics, readiness claim classes, or non-negotiable constraints change. Implementation completion alone belongs in current state unless it changes the product contract.