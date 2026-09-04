# ResQNet-SAGE Implementation Plan

## Scope

This plan covers the remaining production-readiness gaps identified at baseline `8ab15daf5c2a42f407b6d0ed75c3a8762fa13a3c`. It does not reopen already-closed historical work unless current verification reproduces a regression.

Tasks are dependency ordered. Paths under “affected paths” are current or proposed and should be rechecked before implementation.

## TASK-PR-001 — Make ML capability reporting readiness-aware

**Objective.** Prevent `/api/capabilities` from implying operational ML readiness when only runtime/artifact presence is proven.

**Links.** REQ-004, REQ-005, RULE-008, INV-010, GAP-001.

**Prerequisites.** None blocking. First inspect all consumers of `/api/capabilities` and current response tests.

**Affected paths.**
- `backend/app/api/routes/capabilities.py`
- `backend/app/perception/serving*` only if a reusable readiness resolver is needed
- `backend/data/models/manifests.json` only if schema extension is required and justified
- backend capability/manifest tests
- frontend capability consumers, if any
- docs describing ML readiness

**Intended behavior.**
- preserve generic runtime/dependency health for compatibility;
- add explicit model readiness dimensions for trained/placeholder, validation, calibration, regional validation, production approval, and effective inference state;
- derive effective inference state from canonical serving/manifest logic, not duplicated ad-hoc conditions;
- current uncalibrated registered models must not surface as production-approved or safety-ready;
- placeholder/synthetic fixtures remain blocked.

**Compatibility.** Prefer an additive response shape. Before changing or removing existing `status`, locate frontend/scripts/tests consuming it. If removal is needed later, use a documented staged transition.

**Verification.**
- trained + uncalibrated => runtime/artifact available, effective state `abstain`, production approval false;
- missing weights => unavailable;
- placeholder/synthetic fixture => not trained/operationally blocked;
- incompatible contract => incompatible;
- calibrated test fixture => effective state reflects calibrated contract;
- unknown/malformed readiness data fails conservatively;
- existing non-ML capability entries remain compatible.

**Acceptance criteria.** A caller cannot reasonably infer “production-ready disaster model” solely from installed validated weights; tests encode the distinction.

**Documentation updates.** Product spec if field names become accepted contract, contract map, current state, known limitations, API docs if present.

**Completion evidence.** Exact test commands/results, response examples for each readiness case, revision hash.

**Why this is next.** It is the clearest remaining implementation defect, is bounded, and improves safety/claim integrity without requiring external datasets.

## TASK-PR-002 — Repair active documentation drift

**Objective.** Make active entry-point documentation agree with current code while preserving historical evidence.

**Links.** GAP-002.

**Prerequisites.** TASK-PR-001 is not required, but if it changes capability semantics, update docs after that change to avoid duplicate churn.

**Affected paths.**
- `README.md`
- `docs/KNOWN_LIMITATIONS.md`
- `AGENTS.md` if command/status guidance changes
- `DESIGN.md` only by adding clear supersession notes; do not rewrite historical decision content wholesale
- Makefile comment only if a task explicitly authorizes touching executable build/config files; otherwise leave runtime file unchanged and keep drift noted in docs

**Intended behavior.**
- worker documented as aiokafka worker, not APScheduler;
- old fixed test counts removed or labeled as dated evidence rather than living guarantees;
- Redis degradation description updated to current fail-closed protected authorization;
- old UUID/early-layout sections clearly marked superseded by canonical contract/current code.

**Verification.** Spot-check each corrected claim against current source and ensure links resolve.

**Acceptance criteria.** A fresh agent reading README/AGENTS/INDEX/current-state is not directed toward obsolete worker, IDs, or fail-open auth behavior.

## TASK-PR-003 — Bind future release claims to exact-revision verification

**Objective.** Ensure implementation changes produce evidence tied to the exact revision being claimed.

**Links.** REQ-013, GAP-006.

**Prerequisites.** A concrete implementation change to verify.

**Affected paths.** Existing verifier/evidence scripts where necessary; avoid inventing a second evidence framework.

**Intended behavior.**
- relevant checks record command, cwd/environment, revision, outcome, and limitations;
- release-level claims use existing final verification/release-gate machinery;
- a historical PASS does not automatically apply to a later unverified HEAD.

**Verification.** Deliberately compare evidence revision with current HEAD and fail/defer when claim-binding rules require exact match.

**Acceptance criteria.** A reviewer can identify exactly which revision each release/capability claim supports.

## TASK-ML-001 — Acquire valid calibration evidence per model

**Objective.** Move eligible models from safety abstention to calibrated status only when valid calibration evidence exists.

**Links.** REQ-004, REQ-005, GAP-004.

**Blocking decisions/prerequisites.** Appropriate licensed datasets, split policy, minimum sample counts, model-output calibration method, immutable artifact registration. External data may keep this `DEFERRED_EXTERNAL`.

**Affected paths.** Model/evaluation scripts, dataset registry, manifests, serving contracts, evidence; exact paths depend on acquired datasets.

**Intended behavior.**
- calibrate the actual deployed output contract, not a proxy feature model;
- record calibration artifact hash/version, dataset/split, metrics, subgroup/hazard coverage, and failure/abstention thresholds;
- final-test tuning prohibited;
- insufficient data remains `DEFERRED_EXTERNAL`/`abstain`.

**Verification.** Canonical calibration policy checks, contract tests, held-out evaluation, artifact hash verification.

**Acceptance criteria.** Each promoted model meets the accepted calibration policy; otherwise no promotion occurs.

## TASK-ML-002 — Regional/domain validation

**Objective.** Establish whether calibrated models generalize to the intended deployment region/hazard conditions.

**Blocked by.** Licensed regional data, adjudicated labels, privacy/ethics constraints where applicable.

**Intended behavior.** Evaluate event/geography/time-disjoint regional data under the accepted benchmark protocol; record limitations and subgroup/hazard results.

**Acceptance criteria.** Regional readiness remains false unless the explicit regional gate passes. A global/public benchmark result is insufficient.

## TASK-OPS-001 — Execute production-parity external validation

**Objective.** Move the production claim from `DEFERRED_EXTERNAL` only when external runtime prerequisites and observation window are satisfied.

**Links.** GAP-003.

**Prerequisites.** External driver/environment, production-grade secret/key custody, TLS/configuration prerequisites, monitoring window required by the active policy, owner/operational responsibility.

**Method.** Use the existing production-parity/release-gate scripts and their prerequisite registry. Do not shorten a required window to fit an agent session and relabel it equivalent.

**Verification.** Exact active production SLO formulas, zero acknowledged-event loss requirement, latency/ingest thresholds, external prerequisite validation, release attestation/gate result.

**Acceptance criteria.** Production claim changes only through the canonical gate. Missing prerequisites produce `DEFERRED_EXTERNAL`, not PASS.

## TASK-HW-001 — Physical rescue-ball integration validation

**Objective.** Validate the existing software/device boundary against real hardware when hardware becomes available.

**Links.** REQ-014, GAP-005.

**Prerequisites.** Real device, calibrated sensors, safe test environment, hardware specification acceptance.

**Method.** Implement device-specific `SensorSource`/MQTT/serial behavior without bypassing provenance/calibration; execute `docs/PHYSICAL_TEST_PLAN.md`.

**Acceptance criteria.** Real observations remain distinguishable from simulator data; calibration/provenance is recorded; no field-readiness claim yet unless field protocol is separately completed.

## TASK-FIELD-001 — Authorized field trial

**Objective.** Establish field effectiveness and human/agency workflow evidence.

**Blocked by.** Agency authorization, ethics/IRB where required, safety review, trained participants, consent/data governance, device inventory, real regional incidents/scenarios, stop authority.

**Method.** Follow `docs/FIELD_TRIAL_PROTOCOL.md` and prerequisite register. Machine harness results may validate tooling only.

**Acceptance criteria.** Field claim remains `DEFERRED_EXTERNAL` until the field gate's external evidence requirements are satisfied.

## Independent work

- TASK-PR-002 can proceed independently from external ML/ops/hardware tasks.
- TASK-ML-001 and TASK-OPS-001 can proceed independently when their separate prerequisites exist.
- TASK-HW-001 can begin before field-trial execution but does not unblock a field claim by itself.

## Completion rule

A task is complete only when its intended behavior exists, required verification was actually executed, evidence is bound to the relevant revision/environment, affected canonical docs are updated, and no blocking decision is hidden as an assumption.