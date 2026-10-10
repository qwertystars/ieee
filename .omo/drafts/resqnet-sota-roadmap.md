---
slug: resqnet-sota-roadmap
status: review_requested
intent: unclear
review_required: true
plan_path: .omo/plans/resqnet-sota-roadmap.md
plan_sha256: 541d2d525dd9c6c19ef51c0064b4c44e7fedfe159ae8b2d22bdfdd2ca76ee986
review_round_id: resqnet-sota-roadmap-20260801T030500Z
pending-action: write and review .omo/plans/resqnet-sota-roadmap.md
review:
  momus:
    status: pending
    workspace_root: null
    runtime_home: null
    target: .omo/plans/resqnet-sota-roadmap.md
    round_id: null
    plan_sha256: 541d2d525dd9c6c19ef51c0064b4c44e7fedfe159ae8b2d22bdfdd2ca76ee986
    launch_id: pending
    session: null
    result: null
  independent:
    status: pending
    workspace_root: null
    runtime_home: null
    target: .omo/plans/resqnet-sota-roadmap.md
    round_id: null
    plan_sha256: 541d2d525dd9c6c19ef51c0064b4c44e7fedfe159ae8b2d22bdfdd2ca76ee986
    launch_id: pending
    session: null
    result: null
approach: Build a staged SOTA-readiness program: first make every safety-critical path correct, authenticated, durable, and reproducible; then replace synthetic-only ML evidence with leakage-safe regional benchmarks, calibrated models, and strong published baselines; finally execute controlled human-factors and multi-agency field validation. Keep physical hardware and agency execution as explicit external prerequisites rather than claiming them as software work.
---

# Draft: resqnet-sota-roadmap

## Components (topology ledger)
<!-- Lock the SHAPE before depth. One row per top-level component that can succeed or fail independently. -->
<!-- id | outcome (one line) | status: active|deferred | evidence path -->
1 | Correct and secure all realtime, ML-serving, tenancy, approval, and ingestion paths | active | backend/app/realtime/manager.py; backend/app/api/routes/scenarios.py; backend/app/api/routes/sensing.py; backend/app/api/routes/alerts.py
2 | Durable, horizontally scalable production platform with verified recovery | active | backend/app/streaming/consumer.py; docker-compose.yml; scripts/backup.sh; scripts/restore.sh
3 | Reproducible, region-specific ML benchmark and calibration program | active | backend/app/eval; backend/app/fusion/calibration.py; backend/data/models/manifests.json
4 | Human-centered, interoperable, offline-capable operational workflows | active | frontend/public/sw.js; frontend/src/lib/outbox.ts; backend/app/realtime/edge_sync.py; docs/FIELD_TRIAL_PROTOCOL.md
5 | Physical sensor/hardware and multi-agency field validation | deferred | docs/HARDWARE_SPECIFICATION.md; docs/PHYSICAL_TEST_PLAN.md; docs/FIELD_TRIAL_PROTOCOL.md

## Open assumptions (announced defaults)
<!-- Intent is UNCLEAR: research resolves ambiguity, defaults are adopted (not asked), and each is surfaced in the plan's human TL;DR for veto. -->
<!-- assumption | adopted default | rationale | reversible? -->
SOTA definition | Use three gates: research SOTA evidence, production safety readiness, and field effectiveness; do not treat one as a substitute for another | The audit shows current software gates do not establish model or field superiority | yes
Primary deployment | Keep FastAPI/PostgreSQL as the canonical runtime and harden it before considering a platform rewrite | Existing implementation and evidence are concentrated there; rewriting would add risk without improving evidence | yes
Data policy | Use licensed/public datasets plus agency-owned regional data with explicit provenance and consent/IRB controls | Safety-critical evaluation requires lawful, reproducible data | yes
Benchmark policy | Use temporal and geographic holdouts, multiple seeds, confidence intervals, published baselines, and blinded human/operator studies | Prevents synthetic or single-split improvements from being called SOTA | yes
Safety policy | Fail closed for access control and stale/uncalibrated safety outputs; degrade availability only after explicit operator-visible status | Emergency systems must not silently authorize or overstate confidence | no for safety behavior
Execution boundary | Software plan may define hardware and field-trial work packages, but cannot claim them complete | Those activities require external teams, equipment, agencies, and approvals | no

## Findings (cited - path:lines)

- ML route/artifact mismatch: deployed manifests are v2.0.0 while route checks reference v1.0.0; see backend/data/models/manifests.json:3-6 and backend/app/api/routes/scenarios.py, backend/app/api/routes/sensing.py.
- Realtime access control is incomplete: polling and WebSocket paths require tenancy, incident authorization, revocation, and sensitivity filtering; see backend/app/realtime/manager.py.
- Ingestion/fusion is not durable or horizontally consistent: HTTP/batch/background paths can persist before downstream enrichment, and process-local state exists in realtime/evaluation/ABAC; see backend/app/api/routes/observations_batch.py, backend/app/streaming/consumer.py, backend/app/auth/abac.py.
- Approval loop is incomplete: approved alerts still contain a TODO for task creation; see backend/app/api/routes/alerts.py.
- ML evidence is not system-level SOTA: SAR has 0.9412 coverage on 55 samples; damage and NLP have no calibration; the testbed and most evaluation metrics are synthetic/proxy; see docs/KNOWN_LIMITATIONS.md:54-66 and backend/app/eval/{testbed.py,baselines.py,metrics.py}.
- Operational validation is lab-only: no physical device, calibrated sensors, regional validation, or executed field trial; see docs/KNOWN_LIMITATIONS.md:266-320 and docs/FINAL_REPORT.md:596-643.
- Controlled load/chaos evidence is useful but limited: one-hour soak included 933 ingest failures and backend restart behavior; see evidence/load/2026-07-29-full.json:20-31 and docs/KNOWN_LIMITATIONS.md:400-418.
- Offline and deployment posture need hardening: cache-first API behavior, localStorage JWTs, stranded outbox states, development compose defaults, and non-encrypted/local backup assumptions; see frontend/public/sw.js, frontend/src/api/token.ts, frontend/src/lib/outbox.ts, docker-compose.yml, scripts/backup.sh, scripts/restore.sh.
- External SOTA research: Sen1Floods11/FloodNet require geospatially explicit splits and per-class IoU/mIoU; xBD requires localization F1, damage F1, and event/geography-disjoint evaluation; uncertainty claims require untouched-test ECE/Brier/NLL/reliability or coverage/width; multimodal claims require modality ablations and missing-modality tests; NIST AI RMF recommends deployment-like evaluation, independent assessors, domain experts, and monitoring. Sources: Sen1Floods11 CVPRW 2020, FloodNet repository, xBD/xView2 baseline, NIST AI RMF Measure.
- External interoperability research: CAP 1.2/profile validation, ISO 22320 incident concepts, OGC API Features, SensorThings 1.1, signed high-consequence messages, store-and-forward with deterministic conflict rules, and staged tabletop-to-field exercises are the standards anchors. Sources: OASIS CAP 1.2, ISO 22320:2018, OGC API Features, OGC SensorThings 1.1, NIST SP 800-207/800-53, CISA SAFECOM Interoperability Continuum.

## Decisions (with rationale)

- Sequence correctness and safety before optimization: no benchmark or field claim is credible while serving, authorization, or alert dispatch can be wrong.
- Preserve the existing root FastAPI runtime as the source of truth; treat platform/ as a separate future migration, not as deployed functionality.
- Require model-specific evidence and confidence intervals; a manifest flag or nonzero ONNX output is never sufficient validation.
- Make every SOTA claim traceable to a versioned dataset, code revision, evaluation artifact, and independent reproduction.
- Define SOTA as a gated system claim: secure boundaries -> canonical contracts -> durable replay -> real-data evaluation -> calibration/abstention -> production-parity deployment -> shadow field trial. Do not wait until the end to involve operators, but do not automate actuation before field validation.
- Treat CAP/OGC/SensorThings conformance and ISO 22320 mapping as interoperability contracts where selected by the deployment profile; do not mistake standards adoption for agency governance.

## Scope IN

- Source-level fixes, schema/API contracts, durable queues/workflows, authenticated realtime, tenancy/privacy enforcement, offline conflict correctness, deployment hardening, observability, backup/restore, ML data/evaluation/calibration pipelines, benchmark reports, human-factors protocols, standards conformance, and field-trial readiness.

## Scope OUT (Must NOT have)

- No fabricated accuracy, calibration, benchmark, field, hardware, safety, or certification claims.
- No physical hardware procurement/manufacture, real floodwater testing, agency trial execution, medical authority, or regulatory approval represented as completed by software work.
- No wholesale rewrite to Cloudflare/platform/ or a new stack without measured evidence that the canonical runtime cannot meet requirements.
- No weakening of auth, privacy, audit, stale-data labeling, human approval, or graceful-degradation tests to make gates pass.

## Open questions

- None blocking at planning stage; the plan will present adopted defaults for owner veto at the approval gate. External hardware, data-access, agency, and IRB commitments will be explicit prerequisites in the execution plan.

## Approval gate
status: awaiting-approval
approach: Execute the five-component roadmap in dependency order, with each wave producing code, tests, evidence, and a go/no-go gate. The final claim is limited to whichever of research, production, and field gates are actually passed.
next-action: Run one Momus review and one independent Oracle review against the complete plan; fix every cited issue and resubmit both reviewers until approved.
<!-- When exploration is exhausted and unknowns are answered, set status: awaiting-approval. -->
<!-- That durable record is the loop guard: on a later turn read it and resume at the gate instead of re-running exploration. -->
