---
slug: disaster-cf-replatform
status: approved
intent: clear
pending-action: writing .omo/plans/disaster-cf-replatform.md (approved by user "write the plan")
approach: Ground-up re-platform of the entire disaster-response SaaS onto the Cloudflare Workers stack (Hono + D1 + Drizzle + DO + R2 + Vectorize + Queues + Workflows + Pages), implementing EVERY feature in FEATURES.md (~1000 checkboxes, 30+ sections) in full decision-complete detail, sequenced by FEATURES.md's own P0→P14 Build Phase order.
---

# Draft: disaster-cf-replatform

## Components (topology ledger)
- C1 platform-skeleton | wrangler.jsonc + Hono app boots with all bindings wired + Drizzle config + Pages web shell | active | (to be created)
- C2 core-platform | auth/RBAC/orgs/settings/audit/API skeleton (P0) | active | (to be created)
- C3 incident-command | IncidentRoom DO + incident CRUD + command center panels (P1) | active
- C4 map-system | MapLibre + PMTiles + terra-draw + H3 geo index (P2) | active
- C5 tasks-field-requests | task engine + field PWA + help requests (P3) | active
- C6 shelters-missing-popimpact (P4) | active
- C7 ingestion-weather (P5) | active
- C8 comms-public-portal (P6) | active
- C9 ai-reports (P7) | active
- C10 evac-med-logistics-infra (P8) | active
- C11 predsim-drone-damage (P9) | active
- C12 analytics-decision-search (P10) | active
- C13 security-compliance-admin-devplatform-offline (P11) | active
- C14 multiagency-drills-earlywarning-recovery-finance (P12) | active
- C15 observability-deploy-a11y (P13) | active
- C16 scifi (P14) | active
- C17 integrations (cross-cutting, threaded through all phases) | active

## Open assumptions (announced defaults)
- test-strategy | vitest + @cloudflare/vitest-pool-workers (Miniflare, real D1/DO/Queue bindings) + Playwright e2e + k6 hot routes + axe-core a11y + screenshot diff; TDD for engines/scoring/routing, tests-after for CRUD | FEATURES.md Observability section mandates exactly this stack | yes
- repo-structure | new platform/worker + platform/web + platform/packages; existing backend/ + frontend/ kept as v1 reference until parity, removed in final phase | clean re-platform, preserves reference | yes
- todo-granularity | one decision-complete todo per distinct mechanism; acceptance criteria enumerate every FEATURES.md checkbox (section+line) it satisfies for 100% traceable coverage; sibling variations of one engine batched (e.g. 19 incident types = 1 type enum + seed; 12 draw-zone lines = 1 zone_type enum) because FEATURES.md Build blocks define one shared engine per family | avoids ~700 duplicate todos; honors "every feature covered" | yes (user may veto at gate)
- binding-names | wrangler.jsonc per env; D1 `db`; R2 `media`+`exports`; Queues `ingestQ`/`alertQ`/`aiQ`/`webhookQ`+DLQs; DOs `IncidentRoom`/`RateLimiter`/`TaskTimer`/`ShelterCounter`; Vectorize `embeddings`; KV `cache`+`locales` | stable refs for all todos | yes
- provider-adapters | every external provider behind thin adapter + integrations table + env secrets; stubbed in dev; .env.example entry each | no provider blocks a feature | yes
- phase-order | FEATURES.md P0→P14; Observability/Deploy/A11y wired from P0 onward (parallel), finished P13 | FEATURES.md Build Phases | yes

## Findings (cited - path:lines)
- FEATURES.md:1-1904 — full Cloudflare-stack spec, ~1000 checkboxes ALL pre-marked [x] (aspirational; nothing built). Per-section `> Build:` blocks. P0→P14 order at FEATURES.md:45-62.
- FEATURES.md:35-43 — global Conventions (tenancy org_id; ULIDs; UTC ms; visibility {public,internal,sensitive} + review_status {draft,reviewed,official}; hash-chained audit events; idempotency; JSON-Schema forms; AI logging + injection firewall).
- DESIGN.md:1-235 — frozen v1 FastAPI+PostgreSQL/PostGIS contract (urban flood Rivertown demo). Reference only, NOT target runtime.
- README.md — confirms v1 stack (FastAPI/PostgreSQL/APScheduler/React). Demo logins at <role>@demo.disaster.
- git log — 3 commits; last commit `7fae78a docs: add FEATURES.md from p4` added FEATURES.md as docs only.
- repo state — backend/ ~2930 LOC (14 models, 14 routes), frontend/ ~9866 LOC (12 pages). No wrangler.* / no Cloudflare config anywhere.
- v1 domain logic to port conceptually: analysis/scoring.py (7-component area priority), ingestion/pipeline.py (normalize→dedup→verify→store), recommend/routing.py (Dijkstra safe-route), recommend/shelter_alloc.py, reports_gen/situation.py.

## Decisions (with rationale)
- Re-platform (not extend FastAPI) — user decision; FEATURES.md is explicitly a Cloudflare spec and user chose fidelity to it.
- Full detail every phase — user decision; no phased deferral.
- Batch sibling-checkbox todos per shared engine — FEATURES.md Build blocks define one engine per family; avoids duplicate slop; 100% coverage via enumerated acceptance criteria.

## Scope IN
- New Cloudflare Workers platform implementing every FEATURES.md checkbox.
- Shared infra per FEATURES.md Conventions + each section's `> Build:` block.
- All 30+ sections (Core→SciFi) + Integrations cross-cutting.
- Observability/Deploy/A11y wired from P0, finished P13.

## Scope OUT (Must NOT have)
- Keep FastAPI/PostgreSQL as runtime (reference only; removed at final phase).
- Pick/buy provider vendors (adapters only, stubbed in dev).
- Implement during planning (planner only; execution via $start-work).
- Hand-built per-form UIs (use one Form Builder engine per Conventions).
- Auto-publish AI artifacts (always draft → human approve per Conventions).
- Non-idempotent webhook/queue/cron paths.

## Open questions
- (none blocking — gate approved)

## Approval gate
status: approved (user reply: "write the plan")
Plan written: `.omo/plans/disaster-cf-replatform.md` (180 todos T1-T180 + F1-F4 final wave, 14 phases P0-P14 + Integrations cross-cut + final v1-removal).
Metis gap analysis: run (bg_42e93bf7) + tail extracted (bg_ff5254e1); findings B1-B9, C1-C7, D1-D6 folded into plan.
High-accuracy review (user opted in):
- Pass 1 (native Momus subagent): **OKAY — NO BLOCKING ISSUES** (fresh disk re-read on v5; bg_66e31087 round1 + bg_ba1aeaa1 round2). Confirmed all fixes landed; 2 trivial non-blocking items polished (T6 enqueue helpers, T174 range).
- Pass 2 (external, substitute for quota-blocked Codex CLI): ran via `claude` CLI (opus, read-only) — single run, OKAY. Codex account quota exhausted until Jun 25, so Claude substituted (user-approved). 5 rounds total; every cited P1 fixed iteratively; final run returned **VERDICT: OKAY — NO BLOCKING ISSUES** with 5 trivial P2 polish items, all folded in (matrix P6 label T89-T99, T80 stray .py, T10 dashboard count 12→11, T105 enumeration, T174 L1683 explicit).
Both passes OKAY on the current plan. No further interview needed.
Next: hand off to $start-work at T1 (platform skeleton).
