# ResQNet-SAGE Business Rules and Invariants

## Purpose and status

This document owns implementation-relevant business rules and invariants for the active ResQNet-SAGE runtime. It describes both accepted target rules and, where material, their current enforcement status.

Evidence baseline: `main` at `8ab15daf5c2a42f407b6d0ed75c3a8762fa13a3c`.

## Safety and authority

### RULE-001 — AI output starts non-authoritative
**Requirement.** AI/ML/optimization outputs that can influence operational action must begin in a non-authoritative state and require the applicable human review before becoming operationally actionable.

Preconditions:
- an inference/recommendation result exists;
- source and model provenance are attached;
- the effective inference contract permits output rather than `abstain`/`unavailable`.

Normal behavior:
- output is persisted/exposed as draft or equivalent;
- a qualified user reviews the output;
- approval is separately audited.

Failure outcome:
- if the model contract does not permit safety output, no operational alert/recommendation is emitted from that model result.

### RULE-002 — High-consequence effects require human dual control
**Accepted decision.** Any task/resource/public-warning/high-consequence command follows the active dual-control policy defined in the later canonical security/contract work: two distinct active users from the required authorized roles, valid signatures/nonce/freshness, and an atomic commit of approval records plus the effect.

No emergency override may silently bypass the required control. Any break-glass mechanism must be explicit, scoped, and audited.

### INV-001 — No autonomous emergency dispatch
**Statement.** No ML model, LLM, optimizer, simulator, or source adapter can independently dispatch responders or commit a high-consequence emergency action.

**Rationale.** The platform is decision support and has no independent emergency authority.

**Enforcement.** Role/command authorization plus approval state transitions.

**Verification.** Authorization tests, high-consequence command tests, and field-machine no-actuation assertions.

## Tenant and privacy boundaries

### INV-002 — Tenant isolation
**Statement.** A request, event, realtime message, offline replay, query, or side effect scoped to one `org_id` must never expose or mutate another tenant's protected state.

**Enforcement.** Authenticated tenant context, tenant-scoped queries, event/idempotency scope, realtime filtering, and role/visibility controls.

**Verification.** Cross-tenant request/realtime tests and replay/idempotency tests.

### RULE-003 — Organization identity is server-authoritative
Client body/query values must not be able to override the authenticated organization for tenant-scoped operations. Where an external contract includes organization identity, it must be validated against the authenticated/integration trust context.

### INV-003 — Progressive visibility cannot increase without authority
Public/viewer serialization must never include fields classified as internal/sensitive merely because the underlying record contains them. Visibility filtering applies to REST, realtime, exports, and offline state.

## Identity, time, and geometry

### INV-004 — Durable IDs are ULIDs
Durable domain identifiers use uppercase 26-character ULIDs unless a future explicit migration changes the contract. Do not copy older UUID language from the pre-canonical portions of `DESIGN.md` into new code.

### INV-005 — Durable times use UTC epoch milliseconds
Canonical event/decision/provenance timestamps use UTC epoch milliseconds. External adapters may parse other formats only at the boundary and must normalize before canonical persistence.

### INV-006 — External geometry is GeoJSON
External geometry responses remain GeoJSON. Canonical spatial storage uses SRID 4326 where applicable. Do not leak database-specific geometry representations into public contracts.

## Ingestion, replay, and consistency

### RULE-004 — At-least-once transport, idempotent application
External/stream delivery may be at least once. Application effects are idempotent within the canonical scope `(org_id, source, external_id)`.

Same key + same canonical payload: no duplicate effect.

Same key + different canonical payload: conflict, not silent overwrite.

### INV-007 — Acknowledged canonical input is not silently lost
Once an input is acknowledged under the durable ingestion contract, it must remain reconstructable or otherwise accounted for according to the active durability policy. Derived projections may be rebuilt; raw/audit authority must not be rewritten in place to hide loss.

### RULE-005 — Raw authority precedes derived state
Raw canonical events are the rebuild authority for normalized observations/predictions where the contract says reconstruction is supported. Derived state is not allowed to replace or mutate historical raw evidence.

### RULE-006 — Transaction boundaries must not create partial high-consequence state
Where a command requires multiple approvals and an operational effect, the durable approval records and the effect must commit atomically according to the canonical command policy. Failed authorization/signature/freshness checks produce no effect.

## Audit and provenance

### INV-008 — Audit history is append-only and tamper-evident
New audit entries participate in the canonical hash chain. Historical rows are not “fixed” by rewriting hashes or payloads when verification fails.

**Verification.** Audit-chain verification recomputes canonical hashes, checks predecessor continuity and chain head, and fails on tampering/deletion/reordering/fork evidence.

### RULE-007 — Every meaningful state change records actor and rationale context
State changes that affect operational coordination, authorization, approval, tasking, alert status, credential state, or equivalent consequential behavior must emit the appropriate audit/provenance record.

## ML and decision support

### INV-009 — Placeholder/synthetic weights cannot produce operational safety output
A placeholder, dummy, synthetic, unregistered, incompatible, or missing model artifact must not be represented as a trained operational model and must not contribute an operational safety output.

### RULE-008 — ML readiness is multidimensional
The following are distinct facts and must not be conflated:
- runtime availability;
- artifact/weights present;
- trained vs placeholder/synthetic;
- manifest/contract validation;
- calibration availability and quality;
- regional/domain validation;
- production approval/certification status.

The strongest user-visible capability label must be bounded by the weakest required safety dimension.

### INV-010 — Missing calibration forces safety abstention where required
If the canonical inference contract requires calibration and no valid calibration artifact exists, effective inference state is `abstain`, not operationally `available`.

Current evidence: `backend/data/models/manifests.json` records `calibration.status=DEFERRED_EXTERNAL` and `abstention.status=abstain` for all three listed models at the documentation baseline.

### RULE-009 — Successful inference is not proof of model quality
ONNX session creation, output shape, non-zero values, or endpoint success proves plumbing only. Accuracy, calibration, regional robustness, research superiority, and operational fitness require their own evidence.

## Authentication and degraded behavior

### INV-011 — Protected authorization fails closed on unverifiable revocation
Current `backend/app/deps.py` treats inability to verify revocation as revoked/denied. Redis or DB errors must not turn a protected operation into implicit authorization.

### RULE-010 — Refresh credentials fail closed when Redis authority is unavailable
Refresh validation/consumption returns failure when the shared refresh authority is unavailable. Replay/quarantine semantics remain distinct from access-token expiration.

### RULE-011 — Realtime authorization is continuously revalidated
Long-lived realtime channels must not retain protected access indefinitely after credential revocation or tenant/authorization change. The active policy bounds revalidation and uses a protected close path when authorization is lost.

## Offline operation

### INV-012 — Offline replay preserves identity, authorization, and idempotency
Queued offline mutations must carry enough metadata to replay without changing tenant identity or creating duplicate effects. Reconnect is not permission to bypass current authorization.

### INV-013 — Safety-critical conflicts do not use silent last-write-wins
Conflicts involving safety-relevant task/command state require the defined human/coordinator resolution path. They are not silently overwritten by offline replay.

### RULE-012 — Staleness is visible
The UI must surface stale/offline/error state rather than presenting old information as current. Freshness thresholds are defined in frontend canonical code and should remain synchronized with product expectations.

## Schema and compatibility

### INV-014 — Production schema authority is Alembic
Database schema changes are forward Alembic migrations. Runtime table creation helpers are not accepted schema mechanisms.

### RULE-013 — Forward-only migrations need recovery plans
A forward-only migration does not imply rollback is safe. For changes affecting irreversible data or canonical hashes, plan forward recovery and verify backups/preflight rather than assuming `downgrade` restores the previous world.

### RULE-014 — Contract changes account for consumers
A new requirement may intentionally change an old API/event/field contract, but the implementation plan must identify affected consumers, coexistence needs, and transition semantics. Do not silently redefine an established contract.

## Simulation and hardware

### INV-015 — Simulation is explicitly labeled
Simulator-generated observations and machine fixtures remain distinguishable from physical sensor/field observations in provenance and claims.

### INV-016 — Software tests cannot certify physical capability
No software test, synthetic replay, digital twin, or machine fixture can establish floodwater mobility, landing/recovery, thermal human detection, sensor calibration, radio performance, or real field effectiveness.

### RULE-015 — Physical adapters implement the existing boundary
Future hardware should integrate through `SensorSource` and supported MQTT/serial/provenance/calibration interfaces. Domain logic should not be rewritten around one prototype device unless an explicit requirement justifies it.

## Claim integrity

### INV-017 — Claim classes remain independent
A PASS for software tests, a local bounded load test, or a machine field harness does not automatically produce production, research/SOTA, shadow, or field readiness.

### RULE-016 — DEFERRED_EXTERNAL is not failure and not success
When a claim requires unavailable agency, licensed dataset, IRB/ethics, physical hardware, calibration, human study, or external validator evidence, record `DEFERRED_EXTERNAL` with the missing prerequisite. Do not replace it with a fabricated PASS or an unrelated local substitute.

## Update triggers

Update this document when a product rule, trust boundary, authorization rule, state transition, invariant, idempotency scope, compatibility obligation, or readiness/claim policy changes. Implementation status changes belong in `docs/execution/current-state.md` unless the underlying rule itself changes.