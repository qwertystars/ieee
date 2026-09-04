# ResQNet-SAGE Gap Analysis

## Purpose

This document owns meaningful current-to-target differences at the documentation baseline. Closed historical gaps remain in `docs/FINAL_REPORT.md` and evidence records; they are not repeated here unless they still constrain the next change.

Evidence baseline: `main` at `8ab15daf5c2a42f407b6d0ed75c3a8762fa13a3c`.

## GAP-001 — ML capability status is semantically too coarse

**Priority:** high

**Current state.** `GET /api/capabilities` exposes generic `available/degraded/unavailable` states. For ONNX/models it reports `available` when all manifests are `validated` and signed and weights exist. Current manifests nevertheless record calibration unavailable/`DEFERRED_EXTERNAL`, and the serving contract can resolve an uncalibrated model to `abstain`.

**Target.** Capability reporting must distinguish runtime/artifact availability from trained/calibrated/regionally validated/production-approved readiness and expose effective inference state.

**Why it matters.** “Available” can be interpreted as usable for disaster operations even though the model is not calibrated or approved. This violates REQ-004 if the endpoint is used as a readiness surface.

**Affected components/consumers.** `backend/app/api/routes/capabilities.py`, manifest/serving contracts, backend tests, any frontend/diagnostic consumer of `/api/capabilities`, relevant documentation.

**Compatibility consequence.** Existing consumers may depend on the current top-level `status`. Prefer additive structured fields first; do not silently change current enum meaning without consumer discovery.

**Recommended resolution.** Add explicit readiness dimensions and an effective inference state derived from the same canonical serving/manifest logic. Retain generic runtime health during a compatibility window if needed.

**Verification.** Contract/API tests covering trained+uncalibrated, missing weights, placeholder/synthetic fixture, incompatible contract, calibrated fixture, and production-approval false state.

## GAP-002 — Documentation contains known behavior drift

**Priority:** high for agent reliability; low runtime risk.

**Current state.** `README.md` still says APScheduler worker and older test counts. `docs/KNOWN_LIMITATIONS.md` still says Redis token revocation fails open, contradicting current `backend/app/deps.py`. Makefile comments describe an old 15-connection DB pool despite current 50-total engine configuration. Early `DESIGN.md` sections retain superseded UUID/worker/layout assumptions.

**Target.** Entry-point and active operational documentation must reflect current behavior or clearly mark historical sections as superseded.

**Why it matters.** Agents can make incorrect changes by following stale documentation rather than code.

**Recommended resolution.** Correct README and known-limitations narrative; keep historical records but link to the new index/current-state layer. Do not modify executable Makefile merely to fix a comment in this documentation-only task; record it for the next code/config-maintenance change or a separately authorized documentation comment edit.

**Verification.** Documentation link/reference review and code-to-doc spot checks.

## GAP-003 — Production readiness remains externally unproven

**Priority:** high for claims; not an immediate code defect.

**Current state.** Bounded local load/soak/chaos evidence is strong and older performance targets are closed. Later SOTA policy explicitly states that a 3,600-second bounded run cannot produce a full production PASS. The production-parity script can return `DEFERRED_EXTERNAL` when external driver, secret custody/TLS material, or long-window prerequisites are absent.

**Target.** Production claim only after the active production policy's external prerequisites and observation window are satisfied.

**Why it matters.** A local one-hour pass is not evidence of monthly availability, real infrastructure operations, or external key/validator custody.

**Recommended resolution.** Keep production claim `DEFERRED_EXTERNAL` until the exact prerequisite register is satisfied; run bounded parity as engineering evidence without relabeling it as production certification.

**Blocked by.** External environment/telemetry/operational prerequisites.

## GAP-004 — Model calibration and regional validation are incomplete

**Priority:** high for safety/ML claims.

**Current state.** Real pretrained model artifacts are registered, but the inspected current manifests mark calibration unavailable/`DEFERRED_EXTERNAL` and safety abstention. Regional deployment validation is not established. Incident NLP lacks published accuracy metrics in the current manifest rather than fabricating them.

**Target.** For any model intended to produce safety-relevant output: valid calibration artifact and metrics under the canonical policy, supported regional/domain evidence, and explicit production approval before operational readiness is reported.

**Why it matters.** Trained weights and inference plumbing do not establish calibrated or regionally reliable disaster-response behavior.

**Recommended resolution.** Treat model acquisition as complete but calibration/validation as separate external-data tasks. Do not weaken abstention to make demos look complete.

**Blocked by.** Licensed/appropriate calibration and regional datasets, evaluation work, and production approval authority.

## GAP-005 — Physical rescue-ball and field effectiveness remain unvalidated

**Priority:** external milestone.

**Current state.** Software adapters, simulator, hardware specification, physical plan, field protocol, and machine harness exist. Field evidence explicitly marks hardware/agency/human claims `DEFERRED_EXTERNAL`.

**Target.** Real device implementation, calibration, communications testing, deployment/recovery, thermal evaluation, responder workflow testing, and field SLO evidence under authorized protocols.

**Why it matters.** Software correctness cannot prove physical survivability or life-safety sensing.

**Recommended resolution.** Preserve software integration boundary only until real hardware is available; execute physical/field protocols later without altering software claim classes prematurely.

**Blocked by.** Hardware, agency, ethics/safety, operators, real field environment.

## GAP-006 — Verification baseline is evidence-rich but not automatically current at HEAD

**Priority:** medium.

**Current state.** The repository contains detailed evidence and recent commit messages recording green suites. The baseline commit had no GitHub Actions workflow runs visible through the connected GitHub action. Historical evidence can lag source changes.

**Target.** For release/capability claims, verification artifacts should bind to the exact revision being claimed and be easy to regenerate.

**Recommended resolution.** Before merging implementation changes, execute the minimum relevant local/container gates and write revision-bound evidence. For release-level claims, use the existing final verification/release gate machinery rather than relying on commit-message assertions.

## Closed or materially superseded old gaps

The following old requested outcomes are not current open gaps based on inspected source/evidence:
- old Playwright 20/21 failure;
- six older environment-dependent backend failures as originally described;
- placeholder-only ONNX artifacts;
- 6.32 obs/s throughput result;
- absence of a roughly one-hour soak;
- the specific frontend `Date.now()`/set-state-in-effect warnings;
- general protected-token fail-open behavior during Redis outage.

Do not re-plan these from the old prompt without first reproducing a current failure.

## Prioritization

1. GAP-001 — misleading/coarse ML capability state.
2. GAP-002 — stale active documentation that can misdirect agents/operators.
3. GAP-006 — ensure exact-revision verification for future changes.
4. GAP-004 — calibration/regional validation when valid datasets become available.
5. GAP-003 — external production-parity/long-window validation.
6. GAP-005 — physical and field validation when hardware/agency prerequisites exist.

## Update triggers

Add a gap only for a real requirement/contract difference, material risk, or blocked claim. Close it only when current implementation and verification evidence support closure.