# disaster-cf-replatform - Work Plan

## TL;DR (For humans)
<!-- Fill this LAST, after the detailed plan below is written, so it summarizes the REAL plan. -->
<!-- Plain English for a non-engineer: NO file paths, NO todo numbers, NO wave/agent/tool names. -->

**What you'll get:** A complete disaster-response command platform rebuilt on Cloudflare's edge stack (Workers + D1 + Durable Objects + R2 + Queues + AI) that implements every feature in the FEATURES.md catalog — roughly 1,631 capabilities across incident command, live maps, field response, shelters, medical, logistics, weather, AI copilots, simulations, drones, analytics, public portal, security, compliance, multi-agency coordination, drills, early warning, recovery, finance, and accessibility. It replaces the existing FastAPI/PostgreSQL demo (kept only as a reference for domain logic, then removed).

**Why this approach:** You chose full fidelity to FEATURES.md's mandated Cloudflare stack and full detail for every feature. The plan follows FEATURES.md's own build-phase order (P0→P14) because its dependency chain is already correct, and it batches sibling variations of one shared engine (e.g., 19 disaster types → one type enum + seed; 12 draw-zone kinds → one drawing engine) so coverage is 100% traceable without ~700 duplicate tasks. A gap-analysis pass caught and folded in real risks: the original fixed Durable-Object list would have silently dropped the shelter/ambulance/agency rooms (fixed); inbound-webhook dedupe and outbound-webhook delivery were conflated (split); population-impact was scheduled before the census data it needs (reordered); the "until parity" v1-removal trigger was undefined (replaced with a concrete P0-P13 gate).

**What it will NOT do:** It will not keep the FastAPI/PostgreSQL app as the runtime — it's reference-only and removed once the new platform's own acceptance gates pass. It will not pick or hard-bind vendor providers — every provider sits behind a thin adapter, stubbed in dev, so no provider can block a feature. It will not auto-publish anything an AI generates — all AI output lands as a draft needing human approval. It will not build per-form UIs by hand (one form engine) or scatter redaction (one serializer layer). It will not treat the Sci-Fi section as production-grade simulation — those are composition-only drafts over real data, human-approved. And this plan does not implement anything — execution starts only when you run `$start-work`.

**Effort:** XL — a ground-up re-platform of a ~1,631-feature system (180 tracked work units across 14 phases + final cleanup).
**Risk:** High — driven by four unvalidated platform assumptions the plan flags as must-verify early (each with a stated concrete cap/escape-hatch or external-router fallback): D1 FTS5 support (blocks the search section — fallback LIKE search in T139), D1 row/size budget for the population H3 dataset (≤5M rows/region, >50k-cell AOI splits/downsamples in T85), single-threaded IncidentRoom Durable Object fanout scale (256-socket cap + sharding/polling fallback in T21), and in-Worker Dijkstra/A* CPU cap (>50k edges delegates to external Valhalla/OSRM in T112).
**Decisions to sanity-check:** (1) re-platform vs extend — you chose re-platform, which is the larger effort; (2) one-work-unit-per-distinct-mechanism with enumerated checkbox coverage rather than literally one task per ~1,631 checkboxes; (3) heavy compute via an external job-runner adapter by default (Cloudflare Containers optional); (4) Sci-Fi features are in-scope but draft-only.

Your next move: approve the plan, or run a high-accuracy review first. Full execution detail follows below.

## Scope
### Must have
- A new Cloudflare Workers platform under `platform/` (worker + web + packages) that implements EVERY checkbox in `FEATURES.md` (30+ sections, ~1,631 checkboxes, all currently aspirational `[x]` with nothing built).
- The exact stack named in `FEATURES.md:18-33`: Hono + TypeScript on Workers; D1 + Drizzle ORM (+ FTS5); Durable Objects (`IncidentRoom` per incident, token-bucket `RateLimiter`, `TaskTimer`, `ShelterCounter`); Queues + DLQ + Workflows + Cron Triggers + DO alarms; R2 (media/exports, COG rasters, PMTiles); Vectorize; H3 (`h3-js`) + `turf.js` geo (no PostGIS — D1 has none); MapLibre GL JS + Protomaps PMTiles + terra-draw + deck.gl/CesiumJS; React+Vite on Pages + Tailwind + TanStack Query/Router + ECharts + PWA Workbox; Clerk/better-auth + WebAuthn; BYO OpenAI-compatible AI; MSG91/Twilio/WhatsApp/Resend/FCM/Telegram comms; CAP v1.2 interop; Cloudflare Containers for heavy compute; Browser Rendering for PDF.
- Global invariants from `FEATURES.md:35-43` enforced everywhere: `org_id` tenancy (+ `incident_id` on incident tables); ULID IDs; UTC epoch ms; `visibility ∈ {public,internal,sensitive}` + `review_status ∈ {draft,reviewed,official}`; hash-chained append-only audit `events(prev_hash,hash)`; idempotency keys on all external/queue/webhook paths; one JSON-Schema Form Builder engine (no hand-built forms); all AI calls logged + injection-fenced + zod-validated + draft→approve.
- Stable binding names fixed in one `wrangler.jsonc` per env: D1 `db`; R2 `media`+`exports`; Queues `ingestQ`/`alertQ`/`aiQ`/`droneQ`/`geocodeQ`/`webhookIngestQ`/`webhookDeliveryQ` (+ matching `*Dlq`); DO classes `IncidentRoom`/`RateLimiter`/`TaskTimer`/`ShelterCounter`/`AmbulanceQueue`/`AgencyRoom`; Vectorize `embeddings`; KV `cache`+`locales`; Analytics Engine `metrics`. (Metis B1/B2: Shelter counter L590, ambulance queue L836, agency room L1748 are distinct DOs; inbound-webhook-dedupe ≠ outbound-webhook-delivery-retry, split queues.)
- Phased P0→P14 per `FEATURES.md:45-62`; Observability/QA + Deployment + Accessibility/Localization wired from P0 onward (parallel), finished at P13.
- Every FEATURES.md checkbox traceable to a todo (enumerated by section+line in that todo's acceptance criteria) — zero orphan boxes.

### Must NOT have (guardrails, anti-slop, scope boundaries)
- Do NOT retain the FastAPI/PostgreSQL app as the runtime — it is reference only (domain logic to port conceptually) and is removed in the final parity-cleanup phase. No new v1 features.
- Do NOT pick or hard-bind vendor providers — every provider behind a thin adapter + `integrations` table row + env secret; stubbed in dev. No provider may block a feature.
- Do NOT hand-build per-form UIs — one Form Builder engine (JSON-Schema + react-jsonschema-form) renders all forms (`FEATURES.md:42`).
- Do NOT auto-publish AI artifacts — always `review_status=draft` until human approval (`FEATURES.md:16,43`).
- Do NOT build non-idempotent webhook/queue/cron paths — unique key + upsert or dedupe table on every one (`FEATURES.md:14`).
- Do NOT use PostGIS patterns — D1 has none; geometry is GeoJSON TEXT + H3 `geo_index(entity_type,entity_id,h3)` rows + turf refine (`FEATURES.md:26`).
- Do NOT scatter redaction — one serializer layer whitelists public fields (`FEATURES.md:39`).
- Do NOT implement during planning (planner only; execution starts only on `$start-work`).
- Do NOT add scope beyond FEATURES.md sections (no new products). Sci-Fi (P14) is composition of earlier primitives only — no new infra (`FEATURES.md:1664`).

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD for logic-bearing engines (scoring, routing, ingest normalize/dedup/verify, AI zod schemas, H3 covers, sims) + tests-after for CRUD/plumbing/routes/UI. Framework = `vitest` + `@cloudflare/vitest-pool-workers` (Miniflare with real D1/DO/Queue/R2/Vectorize bindings); Playwright e2e on preview deploys; `k6` on hot routes (ingest, map vectors, alert fanout); `axe-core` a11y in CI; screenshot diff for map regressions. (Mandated by `FEATURES.md:1835-1856`.)
- **Per-binding test approach (Metis C6):** vitest-pool-workers covers D1/DO/R2 cleanly; for Queues test the consumer handler as a plain function + integration-test via preview deploy; for Workflows test step functions directly + a preview-deploy integration test; for DO alarms test the alarm handler fn; for Vectorize use a real index in a preview env (mocks only for unit). State this per async todo.
- **Acceptance-criteria categories (Metis D1) — enforced per-todo where applicable AND swept globally in F2/F3/F4:** every todo carries References + an agent-executable Acceptance + happy QA + failure QA + Commit + a FEATURES.md checkbox enumeration. The cross-cutting categories below are enforced per-todo where the todo touches that concern, and otherwise guaranteed by the final sweeps (F2 tenancy isolation, F3 degraded-mode, F4 conventions-invariants):
  1. References = exact FEATURES.md section + line(s) satisfied (traceability) + exact files/bindings/tables.
  2. Agent-executable acceptance = a runnable command (curl/wrangler/vitest/playwright) with exact expected output.
  3. QA-happy = specific data + steps + assertion + evidence path.
  4. QA-failure = specific failure input + expected error/status + evidence path.
  5. **Checkbox enumeration** = the exact FEATURES.md line numbers this todo satisfies (so the F1 coverage ledger can prove 100% mapped, zero orphans).
  6. **Conventions-invariants assertions** (executable, not prose; enforced per-todo on state-changing todos, swept in F4): org_id middleware-enforced + never client-trusted (L37); ULID not UUID (L38); visibility+review_status enums + single-serializer redaction (L39); audit hash-chain append verifies (L40); idempotency key / HMAC dedupe (L41).
  7. **Cross-tenant isolation test** (enforced per-todo on data-touching routes, swept in F2) = a test that org A cannot read org B's data.
  8. **Degraded-mode check** where an Offline/low-bandwidth twin exists (L1626; enforced per-todo where a twin exists, swept in F3): assert the degraded behavior (e.g., "map flag off → table twin").
  9. **AI draft→approve gate** for every AI todo (L15, L445; enforced per-todo on all AI todos): assert output lands as `review_status=draft` and cannot publish without approval.
  10. Commit line = `feat(section): name` per Agent Protocol (L11).
- **Orphan guard (Metis D3):** "distinct mechanism" = the backtick-annotated behavior, NOT the section. Traps: incident merge/split/clone (L180-182) ≠ enum-only; Auto-* AI calls (L187-192) need AI Config (P7) or stub; cross-section triggers (shelter→logistics L615, damage→recovery L1149, shelter→missing L610) owned by the mechanism-owning section, trigger-only here; predicted-spread-zone draw (L270) = enum here / data in P9.
- **Wave-size rule (Metis D4):** the 5-8-per-wave target yields to "every distinct mechanism gets a todo" for mechanism-dense sections (Communications L1035, Logistics L857) — raise the cap there, batch only true enum-siblings (e.g., the 8 comms channel adapters are one todo since they share the fanout Workflow; but CAP import vs export are distinct → separate todos).
- **Drizzle/D1 escape hatches (Metis D6):** FTS5 virtual tables (L21, L1353) and generated/JSON columns use raw-SQL migrations where Drizzle lacks support; Vectorize is a binding, never a SQL table; H3 `geo_index` rows are plain indexed text columns.
- Evidence: `.omo/evidence/task-<N>-disaster-cf-replatform.<ext>` (test stdout, Playwright trace, screenshot, k6 summary).

## Execution strategy
### Parallel execution waves
> Target 5-8 todos per wave. The plan is organized by FEATURES.md Build Phase (P0→P14). Each phase = a named sub-region below with its waves. Within a phase, the shared-infra todo (the section's `> Build:` block) runs FIRST and blocks that section's feature todos; feature todos within a wave parallelize. Cross-phase hard deps are listed in the dependency matrix. Observability/Deploy/A11y (P13) are threaded as cross-cutting todos marked [P13-thread] inside earlier phases, not deferred.

### Dependency matrix (phase-level; todo-level deps inline per todo)
> Metis-folded: B3 Population Impact depends on Data Ingestion census imports (reordered below P5); B4 Command Center (P1) panels forward-depend on P4–P8 data (panels skeletoned in P1, data-wired in owning phase); B5 Volunteer Mgmt placed at P3; B6 Integrations distributed across owning phases (adapter-interface todo in P0).
| Phase / Todo block | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| Platform skeleton (T1-T6) | — | everything | Observability-thread seeding |
| P0 Core Platform (T7-T20) | skeleton | all consumers | P13-thread observability; Integrations adapter-interface (part of T6) |
| P1 Incident + Command (T21-T34) | P0 | P2 overlays, P3+ | P2 map core. NOTE: Command Center panels skeletoned here, data-wired in owning phase (B4) |
| P2 Map System (T35-T48) | P0 | all map overlays everywhere | P1 incident. NOTE: hazard plume overlay (L298) data-wires in P9 |
| P3 Tasks/Field/Requests/Volunteer (T49-T66) | P1, P2 | P4, P8 | P4 pop-impact prep (B5: Volunteer lives here) |
| P4 Shelters/Missing (T67-T78) | P2, P3 | P6 public | P5 ingestion. NOTE: Pop Impact MOVED to P5 (B3) |
| P5 Ingestion/Weather + Population Impact (T79-T94) | P0, P4 | P6 alerts, P9 sims, P10 analytics | P4. NOTE: Pop Impact (L489) now here, after census imports (B3) |
| P6 Comms/PublicPortal (T89-T99) | P4, P5 | P12 early warning | P7 AI. NOTE: Public Portal evac-route-finder (L1201) data-wires in P8 |
| P7 AI/Reports (T100-T111) | P0, P5 | P9 copilots, P11 devplatform AI API, P14 scifi | (parallel to P6 — P7 serializes after P5, not after P6 public gate). NOTE: Reports that reference P8/P9/P12 data stub now, wire later |
| P8 Evac/Med/Logistics/Infra (T112-T125) | P3, P4, P5 | P9 sims, P12 recovery/finance, P6 public-portal evac-finder | P9 |
| P9 PredSim/Drone/Damage (T126-T134) | P2, P5, P7, P8 | P10 analytics, P14 scifi, P2 plume overlay | P10 |
| P10 Analytics/Decision/Search (T135-T142) | P5, P7, P9 | P14 decision scifi | P11 |
| P11 Security/Compliance/Admin/DevPlatform/Offline (T143-T155) | P0 + threaded | hardens everything | P12 |
| P12 MultiAgency/Drills/EarlyWarning/Recovery/Finance (T156-T162) | P6, P8, P11 | P14 | P13 |
| Cross-cutting Integrations consolidation (T171) | T6,T151 | — | P13 |
| P13 Observability/Deploy/A11y (T163-T170) | threaded from P0 | ship readiness | — |
| P14 Sci-Fi (T172-T179) | all | — | — |
| Final parity-cleanup + v1 removal (T180 + F1-F4) | all | — | — |

### v2-parity gate (Metis B7: "parity" must be defined, else v1 removal never triggers)
v1 (`backend/`+`frontend/`) is **reference-only**, removed in the final phase regardless of parity — it lacks every FEATURES.md global invariant (UUID4 not ULID L86 vs L38; no org_id tenancy L37; no visibility/review_status L39; no hash-chain audit L40; no idempotency L41; no JSON-Schema forms L42; no AI logging L43). Parity is NOT a gate; the final phase removes v1 once the Cloudflare platform's own P0–P13 acceptance gates are green.

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
<!-- Each todo enumerates the FEATURES.md checkboxes it satisfies (section+line) for 100% traceable coverage. -->

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- PHASE: PLATFORM SKELETON (pre-P0; boots before any feature) — FEATURES.md:18-33,35-43,45-47 -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 1. Platform monorepo + tooling skeleton
  What to do / Must NOT do: Create `platform/worker/` (Hono + TypeScript), `platform/web/` (React+Vite+Pages), `platform/packages/shared` (zod schemas + types). Root `package.json` workspace + `pnpm` + `turbo` (or `pnpm -r`). Add `biome`/`tsc`, `.editorconfig`, `.gitignore` entries. TS config `strict`, `noUncheckedIndexedAccess`. Must NOT carry over any FastAPI/Postgres files into `platform/` — v1 `backend/`+`frontend/` stay untouched as reference.
  Parallelization: Wave 1 | Blocked by: — | Blocks: T2-T6, all
  References (executor has NO interview context): FEATURES.md:18-33 (stack), FEATURES.md:38 (IDs=ULID), README.md (existing layout to leave alone). New paths: `platform/worker/tsconfig.json`, `platform/web/tsconfig.json`, `platform/package.json`, `platform/turbo.json`.
  Acceptance criteria (agent-executable): `pnpm -w install` exits 0; `pnpm -w exec tsc -b` exits 0 with zero hand-added files in `backend/` or `frontend/` (`git status backend/ frontend/` clean).
  QA scenarios: happy = install+tsc green; failure = delete a tsconfig → tsc fails non-zero. Evidence `.omo/evidence/task-1-disaster-cf-replatform.txt`.
  Commit: Y | chore(platform): monorepo skeleton (worker/web/packages)

- [ ] 2. wrangler.jsonc + all bindings (one per env) wired and booting
  What to do / Must NOT do: Create `platform/worker/wrangler.jsonc` with dev/staging/prod envs. Bindings exactly (frozen here, verbatim-match Scope; Metis B1/B2): D1 `db`; R2 `media`+`exports`; Queues `ingestQ`/`alertQ`/`aiQ`/`droneQ`/`geocodeQ`/`webhookIngestQ`/`webhookDeliveryQ` (+ matching `*Dlq`: `ingestQDlq`/`alertQDlq`/`aiQDlq`/`droneQDlq`/`geocodeQDlq`/`webhookIngestQDlq`/`webhookDeliveryQDlq`); DO classes `IncidentRoom`/`RateLimiter`/`TaskTimer`/`ShelterCounter`/`AmbulanceQueue`/`AgencyRoom`; Vectorize `embeddings` (dim 1024, bge-m3 fallback); KV `cache`+`locales`; Analytics Engine `metrics`; `ai` binding (Workers AI fallback). `main.ts` exports default Hono app. Must NOT use placeholder binding names that drift later — names are frozen here and verbatim-match the Scope binding list.
  Parallelization: Wave 1 | Blocked by: T1 | Blocks: T3-T6
  References: FEATURES.md:22-25 (DO/Queues/Workflows/Cron), FEATURES.md:398 (Workers AI fallback), FEATURES.md:1444-1498 (Security needs Secrets Store). `platform/worker/wrangler.jsonc`, `platform/worker/src/index.ts`.
  Acceptance: `pnpm --filter worker exec wrangler types` generates `worker-configuration.d.ts` with all bindings typed; `wrangler dev --local` boots and `GET /healthz` returns `{ok:true,bindings:{db,media,exports,...}}`.
  QA: happy = healthz lists all bindings; failure = rename a binding in wrangler → tsc error in code referencing old name. Evidence `.omo/evidence/task-2-*.txt`.
  Commit: Y | chore(platform): wrangler bindings + booting worker

- [ ] 3. Drizzle config + D1 migration scaffold + ULID + timestamp helpers
  What to do / Must NOT do: `platform/worker/drizzle.config.ts` (D1 dialect). `platform/worker/src/db/schema/` dir. Helpers: `ulid()` (crockford base32, monotonic), `nowMs()` UTC epoch ms, `createdAt/updatedAt` column helpers, `orgId` column (text, indexed), `incidentId` (nullable). `geo_index` table skeleton. `pnpm drizzle-kit generate` produces migration SQL. Must NOT use autoincrement ints as PKs anywhere — ULIDs only (FEATURES.md:38).
  Parallelization: Wave 1 | Blocked by: T2 | Blocks: T4, all schema todos
  References: FEATURES.md:38 (IDs ULIDs, UTC ms), FEATURES.md:26 (`geo_index(entity_type,entity_id,h3)`). Paths: `platform/worker/src/db/schema/_helpers.ts`, `platform/worker/src/lib/ulid.ts`.
  Acceptance: `pnpm --filter worker exec drizzle-kit generate` emits `0000_init.sql`; `wrangler d1 migrations apply db --local` exits 0; a unit test inserts a row and asserts 26-char ULID + integer ms timestamp.
  QA: happy = migrate + insert + read; failure = drop a required column → migrate fails. Evidence `.omo/evidence/task-3-*.txt`.
  Commit: Y | chore(platform): drizzle + D1 + ULID/timestamp helpers

- [ ] 4. Hono app skeleton: route groups, error model, request_id middleware, OpenAPI via chanfana
  What to do / Must NOT do: `platform/worker/src/index.ts` default Hono app. Middleware: `requestId` (crypto.randomUUID, header `X-Request-Id` propagate), `orgContext` (resolves org_id from auth, NEVER trusted from client body), structured JSON logger (`{ts,level,request_id,org_id,incident_id,msg,fields}`), global error handler returning `{error:{code,message,request_id}}`. Route groups: `/api`, `/api/auth`, `/api/orgs`, `/api/incidents`, `/api/admin`, `/openapi.json`, `/healthz`, `/healthz/deep`. OpenAPI via `chanfana` over all routes. Must NOT scatter auth/org resolution — one middleware layer.
  Parallelization: Wave 2 | Blocked by: T2 | Blocks: T5-T6, P0
  References: FEATURES.md:20 (Hono+chanfana), FEATURES.md:37 (tenancy enforced by middleware), FEATURES.md:39-40 (audit/serializer layer), FEATURES.md:1839-1840 (request_id). `platform/worker/src/app.ts`, `src/middleware/{requestId,orgContext,logger,error}.ts`.
  Acceptance: `GET /openapi.json` returns valid OpenAPI 3 doc listing all groups; `GET /healthz` 200; `GET /healthz/deep` checks D1/R2/Queues and returns per-binding status; a failing route returns `{error}` with `request_id` matching response header.
  QA: happy = openapi+healthz+error shape; failure = throw in a route → global handler returns structured error with request_id. Evidence `.omo/evidence/task-4-*.txt`.
  Commit: Y | feat(platform): hono app skeleton + request_id + chanfana OpenAPI

- [ ] 5. Audit hash-chain engine + idempotency primitives
  What to do / Must NOT do: `events` table `events(actor,action,entity,before,after,ts,prev_hash,hash)` append-only; `hash=sha256(prev_hash‖payload)` (FEATURES.md:40). `writeAudit(db,actor,action,entity,before,after)` helper. `idempotency` dedupe helper (unique `(source,external_id)` + message-id dedupe table). Queue producer helpers — one per frozen queue (T2): `enqueueIngest`/`enqueueAlert`/`enqueueAi`/`enqueueDrone`/`enqueueGeocode`/`enqueueWebhookIngest`/`enqueueWebhookDelivery`, all carrying idempotency keys. Must NOT allow mutating `events` rows (append-only enforced at app layer + documented).
  Parallelization: Wave 2 | Blocked by: T3 | Blocks: all state-changing todos
  References: FEATURES.md:40 (hash-chained audit), FEATURES.md:41 (idempotency). `platform/worker/src/db/schema/events.ts`, `src/lib/audit.ts`, `src/lib/idempotency.ts`.
  Acceptance: unit test inserts 3 events, recomputes each hash from prev and asserts chain validity; tamper middle row → `verifyChain()` returns false at that index. Idempotency test: insert same `(source,external_id)` twice → second is no-op, returns existing id.
  QA: happy = chain verifies; failure = mutation → verify fails. Evidence `.omo/evidence/task-5-*.txt`.
  Commit: Y | feat(platform): hash-chained audit + idempotency primitives

- [ ] 6. Visibility/review_status serializer layer + R2 presign + Queue/Workflow/Cron registries
  What to do / Must NOT do: One serializer module that whitelists fields by `visibility ∈ {public,internal,sensitive}` + `review_status ∈ {draft,reviewed,official}` (FEATURES.md:39) — all public routes MUST go through it. R2 presigned-upload helper (PUT URL, expiry). Queue producer helpers (`enqueueIngest`, `enqueueAlert`, `enqueueAi`, `enqueueWebhook`) carrying idempotency keys. Workflow base class + Cron registry (named crons in `wrangler.jsonc` `[[triggers.crons]]`). Must NOT redact in routes ad hoc.
  Parallelization: Wave 2 | Blocked by: T2,T5 | Blocks: P0+
  References: FEATURES.md:39 (one serializer layer), FEATURES.md:23-24 (Queues/Cron/Workflows), FEATURES.md:171 (R2 presigned). `platform/worker/src/lib/{serialize,presign,queues,workflows,cron}.ts`.
  Acceptance: unit test serializes a `sensitive`+`draft` entity through `publicSerialize()` and asserts PII fields absent, draft-only fields absent; R2 presign returns a URL that accepts a PUT and reads back; a test enqueue produces a queue message with idempotency key; cron registry lists all named crons.
  QA: happy = redaction + presign + enqueue; failure = call publicSerialize on null → throws typed error. Evidence `.omo/evidence/task-6-*.txt`.
  Commit: Y | feat(platform): visibility serializer + R2 presign + queue/workflow/cron registries

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- PHASE P0: CORE PLATFORM — FEATURES.md:65-134 (Core Platform section) -->
<!-- Build block: FEATURES.md:66 (orgs/users/memberships/roles/role_permissions/settings/api_keys/sessions/devices; RBAC policy middleware can(actor,action,subject) CASL-style; token-bucket DO rate limits) -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 7. Core schema: orgs/users/memberships/roles/role_permissions/settings/api_keys/sessions/devices
  What to do / Must NOT do: Drizzle tables per FEATURES.md:66. `orgs(id,name,slug,kind,branding json,settings json,data_region,created_at)`. `users(id,org_id,email,name,...)`. `memberships(user_id,org_id,role_id)`. `roles(id,org_id,name,system bool)` + `role_permissions(role_id,action,subject)`. `settings(scope,key,json)` scope ∈ org/incident/user. `api_keys(id,org_id,prefix,hash,scopes[],last_used_at)`. `sessions(id,user_id,device_id,expires_at)`. `devices(id,user_id,user_agent,last_ip,last_seen)`. All org-scoped tables carry `org_id`. Must NOT trust role from client — roles are rows, resolved server-side.
  Satisfies FEATURES.md checkboxes: Core Platform schema foundation for lines 69-134.
  Parallelization: Wave 3 | Blocked by: T3,T5 | Blocks: T8-T20
  References: FEATURES.md:66 (Build block), FEATURES.md:37 (org_id everywhere). `platform/worker/src/db/schema/{orgs,users,memberships,roles,settings,api_keys,sessions,devices}.ts`.
  Acceptance: `drizzle-kit generate` migration applies to D1 local; a test inserts a full org→user→membership→role→permission chain and reads it back; `org_id` present on every org-scoped table (grep asserts no org-scoped table missing it).
  QA: happy = full chain round-trips; failure = insert membership with nonexistent role_id → FK error. Evidence `.omo/evidence/task-7-*.txt`.
  Commit: Y | feat(core): orgs/users/memberships/roles/settings/api_keys/sessions/devices schema

- [ ] 8. Auth: Clerk/better-auth + WebAuthn passkeys + sessions + device login tracking + emergency lockout
  What to do / Must NOT do: Auth provider adapter (Clerk primary, better-auth fallback) behind interface; WebAuthn passkey registration/login; JWT/session in httpOnly cookies; `devices` row written on login; `emergency_lockout_mode` org-wide kill switch (revokes all sessions, sets `orgs.locked=true`) gated to admin. **Anomalous login detection (L1454): on each login, compare device fingerprint + geo (approx IP→region) against the user's `devices` history; a new-device OR new-geo login fires an in-app + email alert to the user (and to security inbox), logged to the audit chain — NOT a block, a detect-and-alert.** Satisfies: Secure session management (L1452), Device management (L1453), Anomalous login detection (L1454), Secure authentication, MFA, Passkey support, SSO, Emergency lockout mode (FEATURES.md:98,99,100,1451,1452,1453,1454,1448,1449,1450).
  Parallelization: Wave 3 | Blocked by: T7 | Blocks: T9, T14
  References: FEATURES.md:29 (auth stack), FEATURES.md:1444-1454 (security build). `platform/worker/src/auth/{provider,passkey,session,lockout,anomaly}.ts`, `src/api/routes/auth.ts`.
  Acceptance: `POST /api/auth/login` returns token + sets cookie + writes `devices` row; passkey enroll+assert flow passes in a vitest-pool-workers test; lockout revokes sessions (assert `sessions` rows expired); **a login from a new device fingerprint OR new geo (vs history) emits an anomalous-login alert to the user's inbox + security inbox + appends an audit event (assert the alert + audit row exist).**
  QA: happy = login + passkey + lockout; failure = wrong password → 401 + audit event. Evidence `.omo/evidence/task-8-*.txt`.
  Commit: Y | feat(core): auth provider + passkeys + sessions + device tracking + lockout

- [ ] 9. RBAC policy middleware `can(actor,action,subject)` + custom roles + permission groups + scopes
  What to do / Must NOT do: CASL-style policy middleware reading `role_permissions` rows (custom roles = rows not code). `requirePermission(action,subject)` dep. Field-level serializer hooks. API key scopes array checked in middleware. Satisfies: Role-based access control, Permission groups, Custom roles, Attribute-based permissions, Field-level permissions, API key management (scoped), Service account support (FEATURES.md:73,74,75,1455,1456,1457,116,117).
  Parallelization: Wave 3 | Blocked by: T7,T8 | Blocks: T10-T20, all protected routes
  References: FEATURES.md:66 (RBAC), FEATURES.md:1455-1457. `platform/worker/src/auth/policy.ts`, `src/middleware/rbac.ts`.
  Acceptance: a test seeds role+permission, a route guarded by `can('read','incident')` returns 200 for permitted, 403 for a role lacking it; custom role created via API works without code change; API key with scope `incidents:read` can GET but not POST.
  QA: happy = permit + deny + custom-role + scoped-key; failure = missing permission → 403 + audit. Evidence `.omo/evidence/task-9-*.txt`.
  Commit: Y | feat(core): RBAC policy middleware + custom roles + scoped API keys

- [ ] 10. Role dashboards (11 role dashboards per FEATURES.md:76-86) + org switcher + invite links + domain allowlist + observer
  What to do / Must NOT do: One Hono route group per role-dashboard returning role-scoped summary over shared components; React pages for each of the 11 dashboards (admin/operator/field responder/public information/volunteer/shelter manager/medical/logistics/command center/liaison/donor read-only). `org switcher` (membership list → set active org in session). Invite links with preset role (signed token). Email-domain auto-join allowlist. Read-only observer role. Satisfies FEATURES.md:76-86,121,122,123,124 (all 11 dashboards + org switcher + invite + domain allowlist + observer).
  Parallelization: Wave 4 | Blocked by: T7,T9 | Blocks: T11
  References: FEATURES.md:66 (route groups), FEATURES.md:76-86. `platform/web/src/pages/dashboards/*.tsx`, `platform/worker/src/api/routes/dashboards.ts`.
  Acceptance: each of 11 dashboards renders for its role and 403s for others (Playwright per role); invite link with preset role creates membership on accept; domain allowlist auto-joins a user with matching email.
  QA: happy = 11 dashboards render + invite + auto-join; failure = wrong role → 403. Evidence `.omo/evidence/task-10-disaster-cf-replatform.txt` + screenshots.
  Commit: Y | feat(core): 11 role dashboards + org switcher + invites + domain allowlist

- [ ] 11. Multi-tenant + agency/workspace/incident workspaces + multi-region + data residency
  What to do / Must NOT do: `orgs.kind ∈ {tenant,agency,workspace}`; per-tenant D1 pattern sketched (config flag, not built for all); `incident_id` scoping helper; Smart Placement note; `data_region` jurisdiction pin per tenant. Satisfies FEATURES.md:69,70,71,72,87,133 (multi-tenant, agency/workspace/incident workspaces, multi-region, data residency pin).
  Parallelization: Wave 4 | Blocked by: T7 | Blocks: all incident-scoped
  References: FEATURES.md:69-72,87. `platform/worker/src/lib/tenancy.ts`.
  Acceptance: a test creates tenant+agency+workspace+incident and asserts scoping (cross-org query returns nothing); `data_region` surfaced in org settings.
  QA: happy = scoping isolates; failure = cross-org access → empty/403. Evidence `.omo/evidence/task-11-*.txt`.
  Commit: Y | feat(core): multi-tenant workspaces + data residency pin

- [ ] 12. Settings (workspace/incident level) + configurable severity/types/workflows/statuses/labels/layers/alert templates + branding
  What to do / Must NOT do: `settings(scope,key,json)` seeded config tables (severity levels, disaster types, response workflows, status labels, map layers, alert templates) with tenant overrides; custom agency branding (logo/colors) via CSS vars. Satisfies FEATURES.md:101,102,103,104,105,106,107,108,109 (workspace+incident settings, configurable severity/types/workflows/statuses/labels/layers/alerts, branding).
  Parallelization: Wave 4 | Blocked by: T7 | Blocks: P1+ (consumes config)
  References: FEATURES.md:101-109. `platform/worker/src/db/schema/seeded_config.ts`, `src/api/routes/settings.ts`.
  Acceptance: seed defaults present; tenant override changes a severity label and a test reads the override not the default; branding CSS vars render in a Playwright screenshot.
  QA: happy = override wins; failure = invalid key → 400. Evidence `.omo/evidence/task-12-*.txt`.
  Commit: Y | feat(core): settings + seeded configurable tables + branding

- [ ] 13. Public/internal status pages + API-only mode + webhook-first + REST API + OpenAPI docs
  What to do / Must NOT do: Public status page Worker route (KV-cached 60s); internal status page; API-only mode flag (disables UI routes, API still works); webhook-first architecture (event→queue→webhook subscriptions); full REST API = same Hono routes with key auth; OpenAPI docs via chanfana at `/openapi.json` + Scalar UI. Satisfies FEATURES.md:110,111,112,113,114,115 (status pages, API-only, webhook-first, REST API, OpenAPI).
  Parallelization: Wave 5 | Blocked by: T4,T6,T9 | Blocks: P11 devplatform
  References: FEATURES.md:110-115,1581-1624. `platform/worker/src/api/routes/{status,docs}.ts`.
  Acceptance: `GET /status` public route cached in KV (second call hits cache); Scalar UI loads `/openapi.json`; API-only mode returns 404 on UI HTML routes.
  QA: happy = status cache + docs + API-only; failure = KV miss → recompute. Evidence `.omo/evidence/task-13-*.txt`.
  Commit: Y | feat(core): status pages + REST/OpenAPI docs + webhook-first + API-only mode

- [ ] 14. Rate limits (token-bucket DO) + usage analytics (Analytics Engine) + system health dashboard
  What to do / Must NOT do: `RateLimiter` DO (token-bucket per org/key), middleware checks it; 429 + Retry-After; per-org rate limits. Usage analytics via Analytics Engine writes (`route,status,ms,org_id`). System health dashboard reads `/healthz/deep` + Analytics. Satisfies FEATURES.md:118,119,120 (rate limits per org, usage analytics, system health dashboard).
  Parallelization: Wave 5 | Blocked by: T2,T4 | Blocks: P11 monitors
  References: FEATURES.md:66,118-120. `platform/worker/src/do/RateLimiter.ts`, `src/middleware/ratelimit.ts`, `src/api/routes/health.ts`.
  Acceptance: hammering a route beyond limit returns 429 with Retry-After; Analytics Engine receives a write (assert via `ctx.env.metrics.write` mock); health dashboard renders component statuses.
  QA: happy = 429 + analytics + dashboard; failure = DO unavailable → fail-open logged. Evidence `.omo/evidence/task-14-*.txt`.
  Commit: Y | feat(core): token-bucket rate limit DO + usage analytics + health dashboard

- [ ] 15. Global notification center / in-app inbox + command palette (cmdk) + keyboard shortcuts
  What to do / Must NOT do: `notifications` table (user_id, kind, payload, read_at); inbox API + UI dropdown; `cmdk` command palette wired to routes; keyboard shortcuts registry. Satisfies FEATURES.md:125,126,127 (in-app inbox, command palette, keyboard shortcuts).
  Parallelization: Wave 5 | Blocked by: T7,T9 | Blocks: —
  References: FEATURES.md:125-127. `platform/worker/src/api/routes/notifications.ts`, `platform/web/src/components/{Inbox,CommandPalette}.tsx`.
  Acceptance: a notification enqueued appears in inbox; cmdk opens palette and navigates; shortcut fires action.
  QA: happy = inbox + palette + shortcut; failure = empty inbox renders empty state. Evidence `.omo/evidence/task-15-*.txt`.
  Commit: Y | feat(core): in-app inbox + command palette + keyboard shortcuts

- [ ] 16. i18n (i18next+ICU) + mobile-first responsive + dark mode + timezone-aware render + unit toggle + onboarding tour + demo sandbox
  What to do / Must NOT do: i18next + ICU, locale files in KV/R2; mobile-first Tailwind; dark mode (CSS vars); `Intl` date/number/units in incident-local TZ; metric/imperial toggle; guided onboarding tour (driver.js or custom); demo sandbox org with seeded incident. Satisfies FEATURES.md:88,89,90,128,129,130,131 (multi-language, mobile-first, dark mode, TZ render, unit toggle, onboarding, demo sandbox).
  Parallelization: Wave 6 | Blocked by: T1 | Blocks: — (cross-cutting UI)
  References: FEATURES.md:88-90,128-131,1879-1904. `platform/web/src/i18n.ts`, `src/lib/{tz,units}.ts`, `src/pages/Onboarding.tsx`.
  Acceptance: locale switch renders translated strings + RTL layout for an ar locale; TZ render shows incident-local time; dark mode toggles; demo sandbox org auto-seeds on first boot.
  QA: happy = i18n+TZ+dark+demo; failure = missing locale key → falls back to en. Evidence `.omo/evidence/task-16-*.txt` + screenshot.
  Commit: Y | feat(core): i18n + responsive + dark mode + TZ + units + onboarding + demo sandbox

- [ ] 17. Offline-first field mode + low-bandwidth mode foundations (Workbox PWA shell)
  What to do / Must NOT do: Workbox precache shell + runtime SW; low-bandwidth mode flag (no map tiles, text lists, tiny payloads). NOTE: full offline features (Dexie outbox, PMTiles packs, sync) come in P11 Offline section — this todo only lays the PWA shell + low-bandwidth flag used by field dashboards now. Satisfies FEATURES.md:91,92 (offline-first field mode, low-bandwidth mode) at foundation level; full offline in T153/T154.
  Parallelization: Wave 6 | Blocked by: T1 | Blocks: P3 field app
  References: FEATURES.md:91-92,1626-1662. `platform/web/vite-plugin-pwa` config, `src/lib/lowband.ts`.
  Acceptance: Lighthouse PWA installable; low-bandwidth flag swaps map for a list and shrinks payload >50%.
  QA: happy = installable + low-band payload; failure = SW registration fails → graceful no-op. Evidence `.omo/evidence/task-17-*.txt`.
  Commit: Y | feat(core): Workbox PWA shell + low-bandwidth mode foundation

- [ ] 18. Full audit trail + activity timeline + incident history archive + scheduled data export + printable reports
  What to do / Must NOT do: Audit viewer UI over `events` (hash chain verify badge); activity timeline (events filtered by entity); incident history archive (tombstoned/merged incidents read-only); scheduled full-org data export (cron → R2 zip); printable reports (print CSS). Satisfies FEATURES.md:95,96,97,132,93 (audit trail, activity timeline, incident history, scheduled export, printable reports).
  Parallelization: Wave 6 | Blocked by: T5,T7 | Blocks: P11 compliance
  References: FEATURES.md:93,95-97,132. `platform/worker/src/api/routes/{audit,export}.ts`, `src/cron/exportOrg.ts`.
  Acceptance: audit viewer renders chain with verify=true; timeline filters by entity; scheduled export produces an R2 zip and a download link; print CSS renders a clean PDF via Browser Rendering.
  QA: happy = audit+timeline+archive+export+print; failure = tampered chain → verify=false badge. Evidence `.omo/evidence/task-18-*.txt`.
  Commit: Y | feat(core): audit viewer + activity timeline + history archive + scheduled export + print

- [ ] 19. Guided onboarding + API key vault + AI key vault + secret storage
  What to do / Must NOT do: Secrets via `wrangler secret` / Secrets Store; `api_keys` hashed (sha256) + prefix lookup; AI key vault (encrypted at rest, Secrets-wrapped); key rotation schedule (cron check). Satisfies FEATURES.md:116,1478,1479,1480,1481 (API key mgmt, secret storage, API/AI key vaults, key rotation).
  Parallelization: Wave 6 | Blocked by: T7,T9 | Blocks: P7 AI, P11 security
  References: FEATURES.md:116,1478-1481. `platform/worker/src/lib/secrets.ts`, `src/api/routes/apiKeys.ts`.
  Acceptance: create API key returns full key once, stores hash+prefix; lookup by prefix works; rotation cron flags near-expiry; AI key round-trips encrypted.
  QA: happy = create+lookup+rotate; failure = wrong key prefix → 401. Evidence `.omo/evidence/task-19-*.txt`.
  Commit: Y | feat(core): API/AI key vaults + secret storage + rotation

- [ ] 20. Core Platform integration test (seeded demo org + end-to-end RBAC flow)
  What to do / Must NOT do: A `vitest-pool-workers` integration test that seeds a demo org + users (one per role), exercises login→RBAC→dashboard→audit→export, and asserts the whole P0 loop. This is the P0 acceptance gate. Must NOT mark P0 done without this green.
  Parallelization: Wave 7 (P0 gate) | Blocked by: T7-T19 | Blocks: P1+
  References: FEATURES.md:131 (demo sandbox), DESIGN.md:186 (seed users pattern to mirror). `platform/worker/test/p0_integration.test.ts`.
  Acceptance: test green; coverage: every role dashboard reachable by its role, 403 for others, audit chain verifies, export produces a zip.
  QA: happy = full P0 loop green; failure = any role mis-permissioned → test fails with which role. Evidence `.omo/evidence/task-20-*.txt`.
  Commit: Y | test(core): P0 integration gate (seeded org + RBAC + audit + export)

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- PHASE P1: INCIDENT CREATION + COMMAND CENTER — FEATURES.md:135-246 -->
<!-- Build blocks: FEATURES.md:136 (incidents table + IncidentRoom DO + auto-seeds), :195 (panels + IncidentRoom WS + Yjs + ICS forms) -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 21. Incident schema + IncidentRoom DO + H3 geo_index + all 19 incident types (seeded enum)
  What to do / Must NOT do: `incidents(org_id,type,severity,status,escalation,title,desc,geometry GeoJSON TEXT,starts_at,expected_end,config json,declaration_level,command_owner_id,created_at,updated_at)`. `geo_index(entity_type,entity_id,h3)` rows (H3 res 8-10 cover of incident geometry). `IncidentRoom` DO (`idFromName(incidentId)`) holding live state: WebSocket fanout (Hibernatable WebSockets API), presence, live panel deltas, atomic counters, geofence checks. **Fanout cap (Metis C5, concrete): use Hibernatable WebSockets; cap 256 concurrent sockets per IncidentRoom DO; above 256 shard by `incidentId:partition` (partition = floor(connectionIdx/256)) routing clients via a `partitionOf(userId)` lookup, OR fall back to 15s polling for overflow clients.** Persist live positions to DO storage on each update (survives hibernation). `type` enum seeded with all 19 disaster types (wildfire,flood,cyclone,earthquake,landslide,chemical spill,heatwave,power outage,civil emergency,disease outbreak,tsunami,tornado,avalanche,drought,building collapse,crowd-crush,industrial fire,oil spill,radiological) + `custom`. Tenant-overridable type list. Must NOT store geometry as anything but GeoJSON TEXT + H3 rows (no PostGIS).
  Satisfies FEATURES.md:139-163 (Create X incident ×19 + custom), 164-177 (title/desc/type/severity/location/boundary/start/duration/radius/command owner/status/escalation/declaration).
  Parallelization: Wave 8 | Blocked by: T20 | Blocks: T22-T34, P2+ incident-scoped
  References: FEATURES.md:136 (Build), :26 (H3), :158 (complex incident=parent+sub-incidents). `platform/worker/src/db/schema/incidents.ts`, `src/do/IncidentRoom.ts`, `src/lib/geo/h3.ts`, `src/api/routes/incidents.ts`.
  Acceptance: create each of 19 types via `POST /api/incidents` → returns ULID + spawns IncidentRoom DO + writes H3 cover rows; `polygonToH3(geom,res8)` covers asserted; IncidentRoom WS connect returns presence. Complex incident creates parent + linked sub-incidents.
  QA: happy = 19 types create + DO + H3; failure = invalid geometry → 400; duplicate create with idempotency key → same id. Evidence `.omo/evidence/task-21-*.txt`.
  Commit: Y | feat(incidents): schema + IncidentRoom DO + H3 geo_index + 19 disaster types

- [ ] 22. Incident fields + attachments(R2) + notes + source links + tags + teams + radius buffer
  What to do / Must NOT do: `incident_attachments(incident_id,r2_key,name,kind)` via presigned upload; `incident_notes`, `incident_source_links`, `incident_tags`, `incident_teams(incident_id,team_id)`. Affected radius = `turf.buffer(geometry,radius)`. Satisfies FEATURES.md:164-176 (location, boundary, start, duration, radius, command owner, response teams, attachments, notes, source links, tags, status, escalation).
  Parallelization: Wave 8 | Blocked by: T21 | Blocks: T23
  References: FEATURES.md:136,171 (R2 presigned). `src/db/schema/incident_*.ts`, `src/api/routes/incidents.ts`.
  Acceptance: attach a file via presign → appears in incident; note/link/tag CRUD; `turf.buffer` produces a buffer polygon stored + H3-covered.
  QA: happy = full incident detail round-trips; failure = presign expiry → 410 on PUT. Evidence `.omo/evidence/task-22-*.txt`.
  Commit: Y | feat(incidents): attachments + notes + links + tags + teams + radius buffer

- [ ] 23. Sub-incidents + linking + merge + split + clone + from-template + import (file/API) + feed-triggered draft
  What to do / Must NOT do: `incident_links(parent_id,child_id,kind)`; merge = move children + tombstone redirect (`incidents.merged_into_id`); split = clone geometry subset; clone previous incident; `incident_templates` table; import from zod-validated JSON/CSV; import from API; feed-triggered auto-draft incident (USGS quake >M5 in AOI → draft). Satisfies FEATURES.md:178-186 (sub-incidents, linking, merge, split, clone, template, import file, import API, feed-triggered draft).
  Parallelization: Wave 9 | Blocked by: T21,T22 | Blocks: T24
  References: FEATURES.md:158,178-186. `src/api/routes/incidents.ts`, `src/workflows/mergeIncident.ts`.
  Acceptance: merge A→B: A gets tombstone, children reparent to B, `GET /incidents/A` redirects to B; split creates two from one; clone copies a prior incident; import CSV creates N incidents (zod-validated, invalid rows quarantined); a simulated USGS feed tick creates a draft incident.
  QA: happy = merge+split+clone+import+feed-draft; failure = invalid CSV row → quarantined not inserted. Evidence `.omo/evidence/task-23-*.txt`.
  Commit: Y | feat(incidents): sub-incidents + merge + split + clone + template + import + feed-triggered draft

- [ ] 24. Auto-seeds on incident create (summary, checklist, op period #1, default map layers, public alert draft, ICS-201 briefing) via Workflow
  What to do / Must NOT do: On incident create, a Workflow runs: AI summary (draft), response checklist (template by type), operational period #1, default map layers, public alert draft, ICS-201 briefing draft. All land as `review_status=draft`. Satisfies FEATURES.md:187-193 (auto-generate summary/checklist/op period/map layers/public alert/ICS-201).
  Parallelization: Wave 9 | Blocked by: T21,T22 | Blocks: T25 (AI section stubs called; full AI in P7)
  References: FEATURES.md:136,187-193. `src/workflows/onIncidentCreate.ts`. NOTE: AI calls here use the P7 AI wrapper (stubbed if P7 not yet built — workflow must still complete with placeholder drafts).
  Acceptance: create incident → all 6 draft artifacts exist with `review_status=draft`; workflow idempotent (re-run doesn't duplicate — keyed by incident_id).
  QA: happy = 6 drafts created; failure = AI provider down → fallback draft + logged. Evidence `.omo/evidence/task-24-*.txt`.
  Commit: Y | feat(incidents): on-create Workflow seeds summary/checklist/op-period/layers/alert/ICS-201 drafts

- [ ] 25. Command Center: live operational dashboard + 18 panels (reads summary aggregate + IncidentRoom WS deltas)
  What to do / Must NOT do: `GET /api/incidents/:id/summary` D1 aggregates; React panels subscribe to IncidentRoom WS for `{panel,delta}` patches. Panels: overview, current threat, population impact, evacuation, shelter, resource, field team, weather, infrastructure, communications, road access, medical needs, timeline, open task, critical alerts, decision log, pinned priorities, cross-incident regional overview. Satisfies FEATURES.md:198-216,244,245 (live dashboard + 18 panels + pinned priorities + cross-incident overview).
  Parallelization: Wave 10 | Blocked by: T21 | Blocks: T26-T30
  References: FEATURES.md:195. `platform/web/src/pages/CommandCenter.tsx`, `src/components/panels/*.tsx`.
  Acceptance: open command center → all panels render from summary + live WS push updates a panel (test pushes a delta, panel reflects it within 1s). **Fanout cap assertion (Metis C5): a test opening >256 concurrent sockets to one IncidentRoom triggers sharding (overflow clients routed to `incidentId:partition` DOs) or polling fallback — no single DO exceeds 256 sockets.**
  QA: happy = 18 panels + live delta; failure = WS drop → polling fallback (15s) keeps data fresh. Evidence `.omo/evidence/task-25-*.txt` + screenshot.
  Commit: Y | feat(command): live dashboard + 18 panels + IncidentRoom WS deltas

- [ ] 26. Map-first / table-first / kanban views + priority queue + decision log panel
  What to do / Must NOT do: Map-first command view (MapLibre full-bleed), table-first view, kanban response board (`@dnd-kit`), priority queue, decision log panel (append-only, hash-chained). Satisfies FEATURES.md:215,216,217,218,214 (map-first, table-first, kanban, priority queue, decision log panel).
  Parallelization: Wave 10 | Blocked by: T25 | Blocks: —
  References: FEATURES.md:195,215-218. `platform/web/src/pages/CommandCenter*.tsx`.
  Acceptance: toggle between 3 views persists; drag a card in kanban → status updates via API; decision log entries verify hash chain.
  QA: happy = 3 views + kanban drag + decision log; failure = drag without permission → 403 toast. Evidence `.omo/evidence/task-26-*.txt`.
  Commit: Y | feat(command): map/table/kanban views + priority queue + decision log

- [ ] 27. Situation report generator + operational period planning + IAP builder (ICS-202/204) + commander approval + escalation
  What to do / Must NOT do: Sitrep generator (AI draft → human edit → approve); operational period planning (periods with objectives); IAP builder composes ICS-202 (objectives) + ICS-204 (assignments); commander approval flow (review_status draft→approved); escalation workflow. Satisfies FEATURES.md:219,220,221,222,223 (sitrep, op period, IAP builder, approval, escalation).
  Parallelization: Wave 11 | Blocked by: T25 | Blocks: P7 reports
  References: FEATURES.md:195,219-223. `src/api/routes/iap.ts`, `src/workflows/escalation.ts`.
  Acceptance: generate sitrep draft → edit → approve → version pinned; create op period with objectives; build IAP → exports ICS-202+204 pack; approve flow moves review_status.
  QA: happy = sitrep+opperiod+IAP+approve+escalate; failure = approve without permission → 403. Evidence `.omo/evidence/task-27-*.txt`.
  Commit: Y | feat(command): sitrep + op-period + IAP(202/204) + approval + escalation

- [ ] 28. Shift handoff + briefing mode + war-room + TV display (kiosk signed-URL) modes
  What to do / Must NOT do: Shift handoff notes (period→period); briefing mode (fullscreen, big type, auto-cycle panels); war-room screen; TV display mode (unauthenticated signed-URL kiosk route, separate Worker route). Satisfies FEATURES.md:224,225,226,227 (shift handoff, briefing, war-room, TV mode).
  Parallelization: Wave 11 | Blocked by: T25 | Blocks: —
  References: FEATURES.md:195,224-227. `platform/web/src/pages/modes/*.tsx`, `src/api/routes/kiosk.ts`.
  Acceptance: handoff creates a notes doc; briefing mode cycles panels every Ns; kiosk route accessible via signed URL (expires), rejects unsigned.
  QA: happy = 4 modes; failure = expired kiosk URL → 403. Evidence `.omo/evidence/task-28-*.txt`.
  Commit: Y | feat(command): shift handoff + briefing + war-room + TV kiosk modes

- [ ] 29. Real-time collaboration + multi-user cursor presence + shared annotations (Yjs in DO storage)
  What to do / Must NOT do: IncidentRoom DO broadcasts `{userId,pos}` cursor presence; shared annotations = Yjs doc persisted in DO storage; broadcast on change. Satisfies FEATURES.md:228,229,230 (real-time collab, cursor presence, shared annotations).
  Parallelization: Wave 12 | Blocked by: T21,T25 | Blocks: —
  References: FEATURES.md:195,228-230. `src/do/IncidentRoom.ts` (Yjs integration), `platform/web/src/lib/yjs.ts`.
  Acceptance: two browser sessions see each other's cursors; an annotation added in one appears in the other; Yjs doc persists across DO eviction.
  QA: happy = cursors+annotations sync; failure = one client disconnects → presence removed. Evidence `.omo/evidence/task-29-*.txt`.
  Commit: Y | feat(command): realtime collab + cursor presence + Yjs annotations in IncidentRoom

- [ ] 30. Layer trust states (locked official / draft / reviewed / public-safe / sensitive)
  What to do / Must NOT do: `map_layers` carry `visibility` + `review_status` (Conventions); locked official layers immutable except via review; sensitive layers hidden from public serializer. Satisfies FEATURES.md:231,232,233,234,235 (locked/draft/reviewed/public/sensitive layers).
  Parallelization: Wave 12 | Blocked by: T21,T6(serializer) | Blocks: P2 map layers
  References: FEATURES.md:39,195,231-235. `src/db/schema/map_layers.ts`.
  Acceptance: a sensitive layer is omitted from public serializer; promoting draft→reviewed→official works; locked official layer rejects direct edit.
  QA: happy = trust states enforced; failure = public route leaking sensitive → test fails. Evidence `.omo/evidence/task-30-*.txt`.
  Commit: Y | feat(command): layer trust states (locked/draft/reviewed/public/sensitive)

- [ ] 31. ICS org chart (203/207) + objectives tracker (202) + T-card resource board + comms plan (205) + medical plan (206) + check-in (211) + unit log (214)
  What to do / Must NOT do: ICS-203/207 org chart builder; ICS-202 objectives tracker; T-card resource status board; ICS-205 comms plan (radio channels); ICS-206 medical plan; ICS-211 personnel check-in list; ICS-214 unit activity log (feeds Finance time capture in P12). Satisfies FEATURES.md:236,237,238,239,240,241,242 (ICS 203/202/T-cards/205/206/211/214).
  Parallelization: Wave 13 | Blocked by: T25 | Blocks: P7 ICS pack export, P12 finance
  References: FEATURES.md:195,236-242. `src/api/routes/ics/*.ts`.
  Acceptance: each ICS form builds + saves + exports; ICS-214 entries feed a time-capture table (read by Finance later).
  QA: happy = 7 ICS builders; failure = invalid radio channel → 400. Evidence `.omo/evidence/task-31-*.txt`.
  Commit: Y | feat(command): ICS 203/202/T-cards/205/206/211/214 builders

- [ ] 32. Briefing/meeting scheduler (planning P cycle) + pinned command priorities strip
  What to do / Must NOT do: Briefing/meeting scheduler around the ICS planning P cycle; pinned command priorities strip (top-of-dashboard, ordered). Satisfies FEATURES.md:243,244 (briefing scheduler, pinned priorities).
  Parallelization: Wave 13 | Blocked by: T25 | Blocks: —
  References: FEATURES.md:195,243-244. `src/api/routes/briefings.ts`.
  Acceptance: schedule a briefing with agenda + attendees; pin/unpin/reorder priorities.
  QA: happy = scheduler + pinned strip; failure = double-book → warning. Evidence `.omo/evidence/task-32-*.txt`.
  Commit: Y | feat(command): briefing scheduler (P-cycle) + pinned priorities strip

- [ ] 33. [P13-thread] Structured logging + request_id propagation + Sentry (toucan-js) on command center routes
  What to do / Must NOT do: Wire `toucan-js` Sentry on all P1 routes; structured JSON logs with request_id + org_id + incident_id propagated. This is the P13 observability thread landing in P1 (not deferred). Satisfies partial FEATURES.md:1839-1842 (logging, request_id, error tracking).
  Parallelization: Wave 13 (parallel with T31,T32) | Blocked by: T4 | Blocks: —
  References: FEATURES.md:1835-1842. `src/middleware/sentry.ts`.
  Acceptance: an intentional error in a command route reaches Sentry (assert via mock DSN) + log line carries request_id matching header.
  QA: happy = sentry+log; failure = Sentry unreachable → log-only graceful. Evidence `.omo/evidence/task-33-*.txt`.
  Commit: Y | feat(command): [P13-thread] sentry + structured logging + request_id

- [ ] 34. P1 integration gate: create incident → command center live → IAP → audit
  What to do / Must NOT do: Integration test: create a flood incident → auto-seeds fire → command center renders 18 panels → WS push → build IAP (202/204) → approve → audit chain verifies. P1 acceptance gate.
  Parallelization: Wave 14 (P1 gate) | Blocked by: T21-T33 | Blocks: P2+
  References: FEATURES.md:135-246. `platform/worker/test/p1_integration.test.ts`.
  Acceptance: test green; covers all 19 incident types parametrically + IAP + audit + WS.
  QA: happy = full P1 loop; failure = any panel/ICS missing → fails with name. Evidence `.omo/evidence/task-34-*.txt`.
  Commit: Y | test(incidents): P1 integration gate (create→command→IAP→audit)

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- PHASE P2: MAP SYSTEM — FEATURES.md:247-324 -->
<!-- Build block: FEATURES.md:248 (MapLibre + Protomaps PMTiles on R2 + terra-draw zone_type enum + turf + h3-js geo_index + map_layers table) -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 35. MapLibre core + Protomaps PMTiles basemap on R2 (Worker range reads) + 6 base layers
  What to do / Must NOT do: MapLibre GL JS; basemap = Protomaps PMTiles on R2 served via Worker range reads (`pmtiles` js protocol). Base layers: satellite (ESRI World Imagery / Sentinel-2 cloudless), street (PMTiles), terrain (terrain-RGB), dark, offline PMTiles region packs (full packs in P11 T153/T154), custom XYZ/WMS URL. `map_layers(incident_id,name,kind,source(geojson|tile|wms),style json,visibility,review_status,sort,version)`. Must NOT use raster tile servers when PMTiles suffices.
  Satisfies FEATURES.md:251,252,253,254,255,256,257 (interactive map + satellite/street/terrain/dark/offline/custom tile provider).
  Parallelization: Wave 15 | Blocked by: T21 | Blocks: T36-T48
  References: FEATURES.md:248,251-257. `platform/web/src/components/Map/MapView.tsx`, `src/lib/pmtiles-protocol.ts`, `src/api/routes/tiles.ts`.
  Acceptance: map renders PMTiles basemap from R2 via range reads; switch between 6 base layers; custom XYZ URL renders.
  QA: happy = 6 layers render; failure = R2 PMTiles missing → graceful empty basemap + log. Evidence `.omo/evidence/task-35-*.txt` + screenshot.
  Commit: Y | feat(map): MapLibre + PMTiles-on-R2 basemap + 6 base layers + map_layers schema

- [ ] 36. Draw polygon zones engine (terra-draw → GeoJSON, one zone_type enum for all 12 zone kinds)
  What to do / Must NOT do: ONE terra-draw engine producing GeoJSON zones with `zone_type ∈ {evacuation, shelter_catchment, road_closure, danger, safe, search, responder_staging, medical_triage, no_entry, supply_drop, drone_survey, predicted_spread}`. Persisted to `map_zones(incident_id,zone_type,geometry,style,review_status)`. Must NOT hand-build per-zone UIs — one engine, enum-driven.
  Satisfies FEATURES.md:258-270 (draw polygon zones + 12 zone kinds).
  Parallelization: Wave 15 | Blocked by: T35 | Blocks: T37
  References: FEATURES.md:248,258-270. `platform/web/src/components/Map/MapDraw.tsx`, `src/db/schema/map_zones.ts`.
  Acceptance: draw each of 12 zone types → stored with correct `zone_type`; edit/move zone updates geometry; delete removes.
  QA: happy = 12 zone types drawable; failure = invalid geometry (self-intersect) → rejects with message. Evidence `.omo/evidence/task-36-*.txt` + screenshot.
  Commit: Y | feat(map): terra-draw zone engine + zone_type enum (12 zone kinds)

- [ ] 37. Layer controls (opacity/ordering/grouping/permissions) + version history + comparison + time slider
  What to do / Must NOT do: Layer opacity/order/group toggles; layer permissions (RBAC on layer); `layer_versions` table (diff = GeoJSON compare); layer comparison (side-by-side or swipe); time slider over versioned snapshots by ts. Satisfies FEATURES.md:271,272,273,274,275,276,277 (opacity, ordering, grouping, permissions, version history, comparison, time slider).
  Parallelization: Wave 16 | Blocked by: T35 | Blocks: T38
  References: FEATURES.md:248,271-277. `src/api/routes/layers.ts`.
  Acceptance: reorder layers → render order changes; version history diff shows added/removed geometries; swipe compares two versions; time slider scrubs snapshots.
  QA: happy = controls+version+compare+slider; failure = no permission → layer hidden. Evidence `.omo/evidence/task-37-*.txt`.
  Commit: Y | feat(map): layer controls + version history + comparison + time slider

- [ ] 38. Static dataset overlays (heatmap, population density, building footprints, road network, POIs, utilities, floodplain, elevation, wind/rain/temp/air quality)
  What to do / Must NOT do: Imported datasets as map layers: heatmap (maplibre/deck.gl), population density (Kontur H3 hexes), building footprints (Overture/MS), road network (OSM), POIs (hospital/school/shelter/police/fire station), power grid, water supply, railway, bridge, floodplain, elevation (Copernicus GLO-30 DEM hillshade), wind/rain/temp (Open-Meteo grid), air quality (OpenAQ). Sourced via Data Ingestion (P5) imports; rendered as MapLibre layers. Satisfies FEATURES.md:278-297 (heatmap + 18 static overlays).
  Parallelization: Wave 16 | Blocked by: T35 | Blocks: T39
  References: FEATURES.md:248,278-297. `platform/web/src/components/Map/MapOverlays.tsx`.
  Acceptance: each overlay renders from imported data; toggling works; heatmap density correct.
  QA: happy = 18 overlays; failure = missing dataset → "not yet imported" empty state. Evidence `.omo/evidence/task-38-*.txt` + screenshot.
  Commit: Y | feat(map): 18 static dataset overlays (heatmap/POIs/utilities/weather)

- [ ] 39. Live overlays (responder/vehicle/drone/request/shelter/hospital capacity) via IncidentRoom WS
  What to do / Must NOT do: Live overlays sourced from IncidentRoom DO WebSocket: responder location, vehicle, drone, request-for-help, shelter capacity, hospital capacity. Marker clustering (`supercluster`). Satisfies FEATURES.md:299,300,301,302,303,304,305 (6 live overlays + clustering).
  Parallelization: Wave 17 | Blocked by: T21,T35 | Blocks: T40
  References: FEATURES.md:248,299-305. `platform/web/src/components/Map/LiveOverlays.tsx`.
  Acceptance: push a responder position to IncidentRoom → pin appears within 1s; clustering merges dense markers on zoom-out.
  QA: happy = 6 live overlays + clustering; failure = WS drop → stale markers + reconnect. Evidence `.omo/evidence/task-39-*.txt`.
  Commit: Y | feat(map): 6 live overlays via IncidentRoom WS + supercluster

- [ ] 40. Isochrone overlay + 3D terrain + geofence alert zones + geotagged photos (EXIF) + USNG/MGRS grid
  What to do / Must NOT do: Isochrone (openrouteservice); 3D terrain (maplibre terrain); geofence alert zones (zone + rule → IncidentRoom DO checks `turf.booleanPointInPolygon`); geotagged photos (EXIF GPS pins via `exifr`); USNG/MGRS grid (`mgrs` npm). Satisfies FEATURES.md:306,307,308,309,310 (isochrone, 3D terrain, geofence, geotagged photos, MGRS).
  Parallelization: Wave 17 | Blocked by: T35,T39 | Blocks: —
  References: FEATURES.md:248,306-310. `platform/web/src/components/Map/*.tsx`.
  Acceptance: isochrone renders from ORS; 3D terrain renders; crossing a geofence zone triggers an alert (test pushes a position inside → alert); EXIF photo pins at GPS; MGRS grid overlay.
  QA: happy = 5 features; failure = ORS down → isochrone disabled gracefully. Evidence `.omo/evidence/task-40-*.txt`.
  Commit: Y | feat(map): isochrone + 3D terrain + geofence alerts + EXIF photos + MGRS grid

- [ ] 41. Map search (coordinate lat-lng/MGRS/what3words + address Nominatim/Photon + reverse geocoding)
  What to do / Must NOT do: Map search box: lat-lng, MGRS, what3words (API), address (Nominatim/Photon geocoder + cache table), reverse geocoding (click map → address). Satisfies FEATURES.md:311,312,313,314 (map search, coordinate search, address search, reverse geocoding).
  Parallelization: Wave 18 | Blocked by: T35 | Blocks: —
  References: FEATURES.md:248,311-314. `src/api/routes/geocode.ts`, `platform/web/src/components/Map/Search.tsx`.
  Acceptance: search lat-lng/MGRS/w3w/address → flies to location; click map → reverse geocode.
  QA: happy = 4 search modes; failure = geocoder down → cached result or error toast. Evidence `.omo/evidence/task-41-*.txt`.
  Commit: Y | feat(map): search (lat-lng/MGRS/w3w/address) + reverse geocode

- [ ] 42. Measurement tools (distance/area/route + saved annotations) + legend builder
  What to do / Must NOT do: Distance (`turf.length`), area (`turf.area`), route measurement, saved measurement annotations; legend builder. Satisfies FEATURES.md:315,316,317,318,319 (distance, area, route, saved annotations, legend).
  Parallelization: Wave 18 | Blocked by: T35 | Blocks: —
  References: FEATURES.md:248,315-319. `platform/web/src/components/Map/Measure.tsx`.
  Acceptance: measure distance/area/route → values shown; save annotation → persists; legend builder renders a legend.
  QA: happy = 5 tools; failure = zero-length route → 0 displayed. Evidence `.omo/evidence/task-42-*.txt`.
  Commit: Y | feat(map): measurement (distance/area/route) + saved annotations + legend builder

- [ ] 43. Print composer + screenshot export + PDF export + public-safe export + embeddable public map (Browser Rendering)
  What to do / Must NOT do: Print layout composer (title block, scale bar, north arrow); map screenshot/PDF export via Cloudflare Browser Rendering; public-safe export (serializer strips sensitive); embeddable public map (iframe, public layers only, separate route). Satisfies FEATURES.md:320,321,322,323,324 (print composer, screenshot, PDF, public-safe export, embeddable map).
  Parallelization: Wave 19 | Blocked by: T6,T35 | Blocks: P6 public portal
  References: FEATURES.md:248,320-324,33 (Browser Rendering). `src/api/routes/mapExport.ts`.
  Acceptance: compose print → PDF has title/scale/north; screenshot PNG produced; public-safe export omits sensitive layers; iframe embed renders public map only.
  QA: happy = 5 exports; failure = Browser Rendering timeout → fallback PNG. Evidence `.omo/evidence/task-43-*.txt`.
  Commit: Y | feat(map): print composer + screenshot/PDF export + public-safe export + embed

- [ ] 44. [P13-thread] axe-core a11y on map + screenshot diff regression for map
  What to do / Must NOT do: axe-core CI check on map views (keyboard pan/zoom, screen reader); screenshot diff on map regressions (basin baseline). P13 thread in P2. Satisfies partial FEATURES.md:1852,1853 (a11y tests, visual regression).
  Parallelization: Wave 19 (parallel) | Blocked by: T35 | Blocks: —
  References: FEATURES.md:1852-1853,1883-1887. `platform/web/test/map.a11y.test.ts`.
  Acceptance: axe-core finds 0 violations on map page; screenshot diff catches a deliberately shifted layer.
  QA: happy = 0 a11y violations + diff catches regression; failure = violation → CI red. Evidence `.omo/evidence/task-44-*.txt`.
  Commit: Y | feat(map): [P13-thread] axe-core a11y + screenshot diff regression

- [ ] 45. Hazard plume overlay (Gaussian plume, Prediction-fed) + wind direction particle layer
  What to do / Must NOT do: Hazard plume overlay (Gaussian plume output from Prediction P9, rendered as layer); wind direction particle/arrow layer from Open-Meteo grid. NOTE: plume computation lives in P9; this todo renders the P9-produced raster/GeoJSON. Satisfies FEATURES.md:294,298 (wind direction overlay, hazard plume overlay).
  Parallelization: Wave 19 | Blocked by: T35 | Blocks: P9 plume sim
  References: FEATURES.md:248,294,298. `platform/web/src/components/Map/PlumeOverlay.tsx`.
  Acceptance: given a P9 plume GeoJSON, renders overlay; wind particles animate from Open-Meteo grid.
  QA: happy = plume + wind render; failure = no plume data → hidden. Evidence `.omo/evidence/task-45-*.txt`.
  Commit: Y | feat(map): hazard plume overlay (P9-fed) + wind direction particle layer

- [ ] 46. Cell tower overlay (OpenCelliD) + power grid + road closure + railway + bridge layers
  What to do / Must NOT do: Cell tower (OpenCelliD keyword), power grid, road closure, railway, bridge overlays (some overlap with T38 POIs but these are infrastructure-specific layers from P8 imports; here we ensure the map renders them). Satisfies FEATURES.md:287,288,290,291,942,943,944 (cell tower, power grid, railway, bridge, road closure map).
  Parallelization: Wave 20 | Blocked by: T35 | Blocks: —
  References: FEATURES.md:248,287-291,942-944. `platform/web/src/components/Map/InfraOverlays.tsx`.
  Acceptance: each infra layer renders from imported data.
  QA: happy = 5 infra layers; failure = empty dataset → empty state. Evidence `.omo/evidence/task-46-*.txt`.
  Commit: Y | feat(map): cell tower + power grid + road closure + railway + bridge layers

- [ ] 47. Layer comparison swipe + time slider versioned snapshots (integration with T37)
  What to do / Must NOT do: Consolidate the swipe-compare + time-slider UX with real incident zone versions; ensure snapshots are keyed by ts and replayable. (Deepens T37 with incident data.) Satisfies FEATURES.md:276,277 (layer comparison, time slider) at integration level.
  Parallelization: Wave 20 | Blocked by: T36,T37 | Blocks: —
  References: FEATURES.md:276-277. `platform/web/src/components/Map/VersionSlider.tsx`.
  Acceptance: scrub time slider → zones appear/disappear per their version ts; swipe compares two snapshots.
  QA: happy = scrub + swipe; failure = no versions → slider disabled. Evidence `.omo/evidence/task-47-*.txt`.
  Commit: Y | feat(map): versioned swipe-compare + time slider integration

- [ ] 48. P2 integration gate: draw zones → overlay → export → a11y
  What to do / Must NOT do: Integration test: render map → draw 3 zone types → toggle overlays → measure → export PDF → axe-core clean. P2 gate.
  Parallelization: Wave 21 (P2 gate) | Blocked by: T35-T47 | Blocks: P3+
  References: FEATURES.md:247-324. `platform/web/test/p2_integration.test.ts`.
  Acceptance: test green; Playwright screenshot attached.
  QA: happy = full P2 loop; failure = any overlay missing → fails with name. Evidence `.omo/evidence/task-48-*.txt`.
  Commit: Y | test(map): P2 integration gate (draw→overlay→measure→export→a11y)

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- PHASE P3: EMERGENCY TASKS + FIELD RESPONDER + REQUESTS FOR HELP + VOLUNTEER -->
<!-- Build blocks: FEATURES.md:693 (tasks+TaskTimer DO+auto-priority/assign), :638 (field PWA+watchPosition→DO+Dexie outbox), :739 (help_requests+Turnstile+dedupe), :1087 (volunteer extends responder) -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 49. Tasks schema + TaskTimer DO + SLA/escalation alarm + auto-priority/assign
  What to do / Must NOT do: `tasks(incident_id,kind,priority,status,geo,assignee_team_id,assignee_user_id,sla_at,parent_id,deps[],risk_score,impact_score,urgency_score,public_visible)`. `TaskTimer` DO per-task alarm firing escalation chain. Auto-priority = deterministic score (severity×vulnerability×age decay×proximity). Auto-assign = nearest available responder with matching skill (H3 distance+status). Satisfies FEATURES.md:696-700,708,709,722-724.
  Parallelization: Wave 22 | Blocked by: T34 | Blocks: T50-T52
  References: FEATURES.md:693. `src/db/schema/tasks.ts`, `src/do/TaskTimer.ts`, `src/lib/scoring/taskPriority.ts`.
  Acceptance: create task → auto-priority computed; TaskTimer alarm fires escalation at SLA; auto-assign picks nearest matching-skill responder; idempotent re-run no dup.
  QA: happy = create+prioritize+escalate+assign; failure = SLA miss → escalation fires + audit. Evidence `.omo/evidence/task-49-disaster-cf-replatform.txt`.
  Commit: Y | feat(tasks): schema + TaskTimer DO + SLA escalation + auto-priority/assign

- [ ] 50. Task linking + comments + attachments + status + checklist + templates + recurring + batch
  What to do / Must NOT do: Link tasks to map/people/teams/shelters/resources (polymorphic `task_links`); comments; attachments (R2); status; checklist; `task_templates`; recurring (cron-spawned); batch (one per street segment). Satisfies FEATURES.md:701-707,710-715.
  Parallelization: Wave 22 | Blocked by: T49 | Blocks: T51
  References: FEATURES.md:693. `src/api/routes/tasks.ts`.
  Acceptance: link task to shelter+team+person; comment/attach; template spawns recurring via cron; batch creates N tasks for N segments.
  QA: happy = links+recurring+batch; failure = link to nonexistent → FK error. Evidence `.omo/evidence/task-50-disaster-cf-replatform.txt`.
  Commit: Y | feat(tasks): linking + comments + attachments + checklist + templates + recurring + batch

- [ ] 51. Task import/export + timeline + audit + conflict/dup + load-balance + swimlanes + WIP
  What to do / Must NOT do: Import/export (CSV); timeline; audit; conflict detection (same H3 cell+kind+window); duplicate detection; load balancing; swimlanes per team; WIP limits per team. Satisfies FEATURES.md:716-721,725-727.
  Parallelization: Wave 23 | Blocked by: T49,T50 | Blocks: T52
  References: FEATURES.md:693. `src/lib/dedupe/tasks.ts`.
  Acceptance: import CSV (invalid quarantined); conflict flagged; WIP blocks assignment beyond cap.
  QA: happy = import+conflict+WIP; failure = WIP exceeded → assign blocked. Evidence `.omo/evidence/task-51-disaster-cf-replatform.txt`.
  Commit: Y | feat(tasks): import/export + timeline + conflict/dup + load-balance + swimlanes + WIP

- [ ] 52. Task scores + command approval + completion proof + verification + geofence auto-complete + voice-to-task + public visibility
  What to do / Must NOT do: risk/impact/urgency scores; command approval; completion proof (attachment+verifier); verification; geofence auto-completion (arrival closes "reach X" via IncidentRoom position check); voice-to-task (AI extract, P7 wrapper); public visibility. Satisfies FEATURES.md:728-737.
  Parallelization: Wave 23 | Blocked by: T49,T50 | Blocks: T53
  References: FEATURES.md:693. `src/api/routes/tasks.ts`.
  Acceptance: scores computed; approval moves status; completion requires attachment+verifier; geofence arrival auto-closes a "reach X" task; voice note creates draft task.
  QA: happy = scores+proof+geofence+voice; failure = no proof → complete rejected. Evidence `.omo/evidence/task-52-disaster-cf-replatform.txt`.
  Commit: Y | feat(tasks): scores + approval + proof + verification + geofence auto-complete + voice-to-task

- [ ] 53. Field responder PWA: registries + skills/certs + availability + live location (watchPosition→DO) + breadcrumb trail
  What to do / Must NOT do: Responder/team/unit/vehicle/equipment registries; role assignment; skill taxonomy; certification tracking (expiry, doc upload); availability; location = watchPosition → buffered POST/WS → IncidentRoom DO holds live positions + broadcasts; snapshot to D1 every Ns for breadcrumb history. Satisfies FEATURES.md:641-654.
  Parallelization: Wave 24 | Blocked by: T34, T48 (field PWA consumes Map System: PMTiles pack download T55, geofence alerts) | Blocks: T54-T58
  References: FEATURES.md:638. `platform/web/src/pages/FieldResponder.tsx`, `src/do/IncidentRoom.ts`.
  Acceptance: registries CRUD; cert expiry flagged; watchPosition → DO → broadcast to consoles; breadcrumb trail replays on time slider.
  QA: happy = registries+cert+location+breadcrumb; failure = GPS denied → manual entry. Evidence `.omo/evidence/task-53-disaster-cf-replatform.txt`.
  Commit: Y | feat(field): registries + skills/certs + availability + live location + breadcrumb trail

- [ ] 54. Field check-in/out + shifts + fatigue + dead-man timer + buddy + safety + mayday/panic
  What to do / Must NOT do: Check-in/out (ICS-211); shift assignment + handoff; fatigue (hours since check-in); dead-man timer (DO alarm; missed = alert chain); buddy/pair; safety reminders; mayday (priority WS broadcast + SMS fallback via Queue); panic. Satisfies FEATURES.md:655-664.
  Parallelization: Wave 24 | Blocked by: T53 | Blocks: T55
  References: FEATURES.md:638. `src/do/TaskTimer.ts` (dead-man reuse).
  Acceptance: check-in/out round-trips; dead-man missed → alert chain; mayday broadcasts priority + enqueues SMS.
  QA: happy = check-in+dead-man+mayday; failure = mayday SMS provider down → queued + logged. Evidence `.omo/evidence/task-54-disaster-cf-replatform.txt`.
  Commit: Y | feat(field): check-in/out + shifts + fatigue + dead-man + buddy + mayday/panic

- [ ] 55. Field task flow + evidence + voice/photo/video + offline outbox (Dexie) + map/route download
  What to do / Must NOT do: Field task assign/accept/complete; evidence upload (R2 presigned, EXIF kept); notes; voice notes (MediaRecorder→R2, transcript via AI); photo/video; offline cache (IndexedDB Dexie); sync queue (Dexie outbox → Background Sync flush with idempotency keys); field map download (PMTiles pack); route download. Satisfies FEATURES.md:665-676.
  Parallelization: Wave 25 | Blocked by: T53 | Blocks: T56
  References: FEATURES.md:638. `platform/web/src/components/field/*.tsx`, `src/lib/offline-db.ts`.
  Acceptance: accept task offline → outbox → sync on reconnect (idempotent); voice note → R2 + transcript; PMTiles pack downloads.
  QA: happy = offline→sync + voice + map pack; failure = sync conflict → LWW + per-field merge UI. Evidence `.omo/evidence/task-55-disaster-cf-replatform.txt`.
  Commit: Y | feat(field): task flow + evidence + voice/photo/video + offline outbox + map/route download

- [ ] 56. Field forms (checklist/triage/damage/trapped/road-blockage/infra) + equipment checkout + exposure/dosimeter + K9 + heat/air/hazard/geofence alerts + PAR
  What to do / Must NOT do: Field checklist, triage, damage, trapped-person, road-blockage, infrastructure reports (all via ONE Form Builder engine, JSON-Schema); equipment checkout (movements ledger reuse); exposure/dosimeter log (radiological/chemical); K9/specialist tracking; heat-stress alerts (heat index threshold); air-quality alerts (OpenAQ threshold); hazard proximity alerts; geofence alerts; accountability report (PAR). Satisfies FEATURES.md:677-691.
  Parallelization: Wave 25 | Blocked by: T55 | Blocks: T57
  References: FEATURES.md:638,677-691. `src/lib/forms/builder.ts` (engine), `src/api/routes/fieldReports.ts`.
  Acceptance: each form renders via Form Builder + submits; dosimeter log tracked; heat/air/hazard/geofence alerts fire on threshold; PAR report generates.
  QA: happy = 6 forms + alerts + PAR; failure = threshold not crossed → no alert. Evidence `.omo/evidence/task-56-disaster-cf-replatform.txt`.
  Commit: Y | feat(field): Form-Builder field forms + equipment checkout + dosimeter + K9 + heat/air/hazard/geofence alerts + PAR

- [ ] 57. Requests for help: schema + all inbound channels (public/Turnstile, SMS, email, WhatsApp, Telegram, IVR, hotline, field) + multi-language
  What to do / Must NOT do: All channels → `raw_reports` staging → `help_requests(category,geo,contact,score,status,visibility)`. Public form = Turnstile-protected. Inbound adapters: Twilio/MSG91 SMS webhook, WhatsApp Cloud API, Telegram bot, CF Email Workers, IVR (Exotel/Twilio keypad), hotline operator entry, field responder entry. Multi-language form. All HMAC-verified + delivery-id dedupe. Satisfies FEATURES.md:742-751.
  Parallelization: Wave 26 | Blocked by: T34, T48 (help-request map consumes Map System; uses local help_requests staging until P5 raw_reports lands in T75; the shared staging is later-wired-by T75, NOT a blocking dep) | Blocks: T58
  References: FEATURES.md:739. `src/api/routes/helpRequests.ts`, `src/ingest/channels/*.ts`.
  Acceptance: submit via each channel → help_request row created; Turnstile rejects bot; HMAC invalid → 401; idempotent (replay = no dup).
  QA: happy = all channels + Turnstile + dedupe; failure = bad HMAC → 401 + audit. Evidence `.omo/evidence/task-57-disaster-cf-replatform.txt`.
  Commit: Y | feat(requests): all inbound help channels + Turnstile + HMAC dedupe + multi-language

- [ ] 58. Help request triage: dedupe + repeat-caller + merge + priority score + categories + status + assignment (creates task) + verification/follow-up/closure + callback
  What to do / Must NOT do: Dedupe (phone+geo+time window + embedding similarity via Vectorize); repeat-caller linking; merge; priority scoring (severity×vulnerability×age decay); triage; categories (rescue/medical/food/water/shelter/transport/missing/trapped/animal/accessibility); status tracking; assignment (creates linked task); verification; follow-up; closure; callback scheduling (Queue with retry). Satisfies FEATURES.md:752-774.
  Parallelization: Wave 26 | Blocked by: T57 | Blocks: T59
  References: FEATURES.md:739. `src/lib/scoring/helpPriority.ts`.
  Acceptance: dedupe merges similar; repeat-caller linked; assignment creates a task; callback Queue retries.
  QA: happy = dedupe+priority+assign+callback; failure = duplicate phone+geo+window → merged. Evidence `.omo/evidence/task-58-disaster-cf-replatform.txt`.
  Commit: Y | feat(requests): triage + dedupe + priority + categories + assignment + callback

- [ ] 59. Help request geo + reverse geocode + confidence + fraud detection + abuse protection + public-safe redaction + heatmap + surge detection
  What to do / Must NOT do: Geolocation; reverse geocoding; confidence score; fraud detection (velocity rules + blocklist); abuse protection (rate limit + blocklist); public-safe redaction (serializer); heatmap; surge detection (rate spike per H3 area). Satisfies FEATURES.md:775-783.
  Parallelization: Wave 27 | Blocked by: T57 | Blocks: T60
  References: FEATURES.md:739. `src/lib/fraud.ts`.
  Acceptance: reverse geocode fills address; fraud flags velocity spikes; redaction strips PII on public route; surge detected on rate spike.
  QA: happy = geo+fraud+redaction+surge; failure = blocklisted phone → rejected. Evidence `.omo/evidence/task-59-disaster-cf-replatform.txt`.
  Commit: Y | feat(requests): geo + fraud + abuse + redaction + heatmap + surge detection

- [ ] 60. Volunteer management: registration + verification + skill profile + availability + assignment + shifts + check-in/out + geofenced check-in + task board
  What to do / Must NOT do: Extends responder tables with `kind=volunteer`. Verification = doc upload + admin approve. Skill profile; availability; assignment; shift scheduling; check-in/out; geofenced check-in (location within site polygon); volunteer task board. Satisfies FEATURES.md:1090-1100.
  Parallelization: Wave 27 | Blocked by: T53 | Blocks: T61
  References: FEATURES.md:1087. `src/db/schema/volunteers.ts`, `src/api/routes/volunteers.ts`.
  Acceptance: register → verify → assign; geofenced check-in rejects out-of-polygon; task board shows volunteer tasks.
  QA: happy = register+verify+geofence+board; failure = out-of-polygon check-in → rejected. Evidence `.omo/evidence/task-60-disaster-cf-replatform.txt`.
  Commit: Y | feat(volunteer): registration + verification + skills + shifts + geofenced check-in + task board

- [ ] 61. Volunteer training/credentials/consent/insurance/safety + team grouping + supervisor + comms + hours + ID badge + certificate + abuse prevention + dup detection
  What to do / Must NOT do: Training status; skills quiz (Form Builder scored form); credential upload; background status; minor guardian consent; insurance flag; safety briefing; incident reporting; team grouping; supervisor assignment; communication; hours tracking (check-in/out diff); ID badge (QR, pdf-lib); certificate generation (pdf-lib); abuse prevention; duplicate detection; spontaneous volunteer intake. Satisfies FEATURES.md:1101-1117.
  Parallelization: Wave 28 | Blocked by: T60 | Blocks: T62
  References: FEATURES.md:1087. `src/lib/pdf/badge.ts`.
  Acceptance: quiz scored; badge PDF with QR generated; certificate generated; hours computed; spontaneous intake works.
  QA: happy = quiz+badge+cert+hours+intake; failure = minor without consent → blocked. Evidence `.omo/evidence/task-61-disaster-cf-replatform.txt`.
  Commit: Y | feat(volunteer): training + consent + insurance + hours + ID badge + certificate + intake

- [ ] 62. Volunteer: community org registry + NGO coordination + mutual aid coordination (Multi-Agency link)
  What to do / Must NOT do: Community organization registry; NGO coordination; mutual aid coordination (links to Multi-Agency section P12 — creates the trigger here, mechanism in P12). Satisfies FEATURES.md:1118,1119,1120.
  Parallelization: Wave 28 | Blocked by: T60 | Blocks: — (mutual-aid mechanism wires in P12)
  References: FEATURES.md:1087,1120. `src/api/routes/volunteers.ts`.
  Acceptance: registry CRUD; NGO coordination links orgs; mutual-aid trigger created (wires to P12 mutual aid).
  QA: happy = registry+NGO+mutual-aid-trigger; failure = mutual-aid not yet wired → stub. Evidence `.omo/evidence/task-62-disaster-cf-replatform.txt`.
  Commit: Y | feat(volunteer): community org registry + NGO coordination + mutual-aid trigger

- [ ] 63. [P13-thread] Playwright e2e on field responder PWA + axe-core a11y on field forms
  What to do / Must NOT do: Playwright e2e on field responder flow (login→accept task→offline→sync); axe-core on field forms (large-touch-target "gloves" mode, screen reader). P13 thread in P3. Satisfies partial FEATURES.md:1850,1851,1891.
  Parallelization: Wave 28 (parallel) | Blocked by: T55,T56 | Blocks: —
  References: FEATURES.md:1850,1891. `platform/web/test/field.e2e.test.ts`.
  Acceptance: e2e green offline→sync; axe-core 0 violations on field forms with gloves mode.
  QA: happy = e2e+a11y; failure = violation → CI red. Evidence `.omo/evidence/task-63-disaster-cf-replatform.txt`.
  Commit: Y | feat(field): [P13-thread] Playwright e2e + axe-core a11y on field PWA

- [ ] 64. P3 integration gate: task→assign→field-offline→sync→help-request→triage→volunteer
  What to do / Must NOT do: Integration test: create task → auto-assign → field accept offline → sync → submit help request → triage → volunteer check-in. P3 gate.
  Parallelization: Wave 29 (P3 gate) | Blocked by: T49-T63 | Blocks: P4+
  References: FEATURES.md:637-783,1086-1120. `platform/worker/test/p3_integration.test.ts`.
  Acceptance: test green; covers offline→sync idempotency + help-request dedupe + geofenced volunteer check-in.
  QA: happy = full P3 loop; failure = any step missing → fails with name. Evidence `.omo/evidence/task-64-disaster-cf-replatform.txt`.
  Commit: Y | test(tasks): P3 integration gate (task→field-offline→sync→help-request→volunteer)

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- PHASE P4: SHELTER MANAGEMENT + MISSING PERSONS / REUNIFICATION — FEATURES.md:583-636, 784-818 -->
<!-- Build blocks: FEATURES.md:584 (shelters+ShelterCounter DO+checkins+QR+haversine finder), :785 (PFIF+fuzzy name+pHash+encrypted sensitive cols) -->
<!-- NOTE (Metis B3): Population Impact moved to P5 (depends on Data Ingestion census imports). -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 65. Shelter schema + ShelterCounter DO (live occupancy) + capacity/availability/accessibility/pet/medical/generator/water/food/sanitation/staff/security status
  What to do / Must NOT do: `shelters(geo,capacity,flags...)`, `shelter_status` snapshots, `checkins(person split-name,flags,visibility)`. Live occupancy = `ShelterCounter` DO per shelter = checkins − checkouts (Metis B1: distinct DO, not crowded into IncidentRoom). Status fields: availability, accessibility, pet support, medical support, generator (+fuel-hours), water, food, kitchen meal capacity/day, sanitation (Sphere ratios), staff, staffing roster, security. Satisfies FEATURES.md:587-604.
  Parallelization: Wave 30 | Blocked by: T48 | Blocks: T66-T72
  References: FEATURES.md:584. `src/db/schema/shelters.ts`, `src/do/ShelterCounter.ts`.
  Acceptance: check-in → ShelterCounter increments → broadcast; check-out decrements; all status fields CRUD; generator fuel-hours computed.
  QA: happy = check-in/out + counter + statuses; failure = DO unavailable → fallback D1 count. Evidence `.omo/evidence/task-65-disaster-cf-replatform.txt`.
  Commit: Y | feat(shelters): schema + ShelterCounter DO + capacity/status fields

- [ ] 66. Shelter check-in/out + bed inventory + gender segregation + child-friendly + family grouping + reunification link + vulnerable/medical/dietary flags + privacy serializer
  What to do / Must NOT do: Check-in (QR or manual); check-out; bed-level inventory; gender-segregated capacity; child-friendly space flag; family grouping; reunification support (match against Missing Persons — trigger here, mechanism in T74); vulnerable/medical/dietary needs flagging; privacy-safe shelter records (visibility serializer). Satisfies FEATURES.md:604-614.
  Parallelization: Wave 30 | Blocked by: T65 | Blocks: T67
  References: FEATURES.md:584. `src/api/routes/shelters.ts`.
  Acceptance: QR check-in works; bed inventory tracks; reunification trigger created; serializer redacts PII on public route.
  QA: happy = QR+beds+reunification-trigger+redaction; failure = public route leaking PII → test fails. Evidence `.omo/evidence/task-66-disaster-cf-replatform.txt`.
  Commit: Y | feat(shelters): check-in/out + beds + family + reunification link + flags + privacy serializer

- [ ] 67. Shelter supply requests (ICS-213RR → Logistics trigger) + incident reports + overcrowding alerts + transfer workflow + NGO operator assignment
  What to do / Must NOT do: Shelter supply requests (ICS-213RR keyword → creates Logistics trigger, mechanism in P8); incident reports; overcrowding alerts (threshold → notification); transfer workflow; NGO operator assignment. Satisfies FEATURES.md:615-619.
  Parallelization: Wave 31 | Blocked by: T65 | Blocks: T68
  References: FEATURES.md:584. `src/api/routes/shelters.ts`.
  Acceptance: supply request creates ICS-213RR trigger (wires in P8); overcrowding alert fires at threshold; transfer moves occupant.
  QA: happy = supply+overcrowding+transfer; failure = below threshold → no alert. Evidence `.omo/evidence/task-67-disaster-cf-replatform.txt`.
  Commit: Y | feat(shelters): supply requests (ICS-213RR trigger) + overcrowding alerts + transfer + NGO assignment

- [ ] 68. Shelter recommendation engine + nearest/best-fit finder + load balancing + route directions + QR + intake form + daily report + closure
  What to do / Must NOT do: Recommendation engine; nearest shelter finder (haversine top-N → route-time re-rank); best-fit (needs flags match); load balancing (capacity-weighted assignment); route directions; QR code (`qrcode` npm signed links); intake form (Form Builder schema); daily report (scheduled template); closure workflow. Satisfies FEATURES.md:620-629.
  Parallelization: Wave 31 | Blocked by: T65 | Blocks: T69
  References: FEATURES.md:584. `src/lib/recommend/shelterFinder.ts`.
  Acceptance: nearest finder returns top-N re-ranked by route time; best-fit matches needs flags; load-balance assigns to least-loaded; QR generates; daily report cron produces PDF.
  QA: happy = finder+best-fit+balance+QR+report; failure = no shelters in range → empty state. Evidence `.omo/evidence/task-68-disaster-cf-replatform.txt`.
  Commit: Y | feat(shelters): recommendation + finder + load-balance + QR + intake form + daily report + closure

- [ ] 69. Shelter planning: donation drop-point + temporary/mega/micro/special-needs/hospital-overflow shelter planning
  What to do / Must NOT do: Donation drop-point flag; temporary shelter planning; mega shelter planning; micro shelter planning; special needs shelter planning; hospital overflow shelter planning. Satisfies FEATURES.md:630-635.
  Parallelization: Wave 32 | Blocked by: T65 | Blocks: T70
  References: FEATURES.md:584. `src/api/routes/shelterPlanning.ts`.
  Acceptance: each planning type creates a planned shelter with appropriate flags; hospital-overflow links to a hospital.
  QA: happy = 6 planning types; failure = invalid type → 400. Evidence `.omo/evidence/task-69-disaster-cf-replatform.txt`.
  Commit: Y | feat(shelters): planning (donation/temporary/mega/micro/special-needs/hospital-overflow)

- [ ] 70. Shelter public page (PFIF-safe redacted subset)
  What to do / Must NOT do: Shelter public page = separate route rendering PFIF-safe redacted subset through the public serializer. Satisfies FEATURES.md:625.
  Parallelization: Wave 32 | Blocked by: T65,T6(serializer) | Blocks: P6 public portal
  References: FEATURES.md:584,625. `src/api/routes/public/shelters.ts`.
  Acceptance: public route renders redacted shelter info; no PII; KV-cached 60s.
  QA: happy = public page redacted; failure = sensitive field → stripped. Evidence `.omo/evidence/task-70-disaster-cf-replatform.txt`.
  Commit: Y | feat(shelters): public page (PFIF-safe redacted)

- [ ] 71. Missing persons: schema (PFIF-compatible) + missing/found reports + photo + last known location/time + medical/age/vulnerability flags + encrypted sensitive cols
  What to do / Must NOT do: PFIF-compatible schema (Google Person Finder format). `missing_persons` + `found_persons`. Photo upload; last known location/time; medical condition flag; age group flag; vulnerability flag. Sensitive fields encrypted at rest (WebCrypto AES-GCM, keys in Secrets Store). Public listing = redacted consented subset. Satisfies FEATURES.md:788-797.
  Parallelization: Wave 33 | Blocked by: T48 | Blocks: T72-T74
  References: FEATURES.md:785. `src/db/schema/missingPersons.ts`, `src/lib/crypto.ts`.
  Acceptance: create missing + found person; photo uploads; sensitive fields round-trip encrypted (assert ciphertext at rest ≠ plaintext); public listing redacted.
  QA: happy = missing+found+photo+encryption+redaction; failure = decrypt with wrong key → error. Evidence `.omo/evidence/task-71-disaster-cf-replatform.txt`.
  Commit: Y | feat(missing): PFIF schema + reports + photo + flags + encrypted sensitive cols

- [ ] 72. Missing persons: case status + notes + assignment + duplicate detection + shelter/hospital/field/hotline matching + manual match approval
  What to do / Must NOT do: Case status tracking; notes; assignment; duplicate case detection; possible match suggestions = fuzzy name (jaro-winkler + double-metaphone, `talisman` npm) + age/sex/geo filters + photo perceptual hash (`blockhash`). Match sources: shelter check-in (T66), hospital intake, field report, hotline report. All matches require human approval. Satisfies FEATURES.md:798-809.
  Parallelization: Wave 33 | Blocked by: T71 | Blocks: T73
  References: FEATURES.md:785. `src/lib/matching/fuzzy.ts`.
  Acceptance: match suggestions ranked; duplicate cases flagged; manual approval promotes a match; shelter check-in matches a missing person.
  QA: happy = matches+dedupe+approval; failure = low-similarity match → not suggested. Evidence `.omo/evidence/task-72-disaster-cf-replatform.txt`.
  Commit: Y | feat(missing): case mgmt + fuzzy+pHash matching + multi-source + human approval

- [ ] 73. Missing persons: family notification + reunification center + QR card + safe-and-well + foreign national/embassy + deceased handling + PFIF import/export + report
  What to do / Must NOT do: Family notification workflow; reunification center management; QR-based reunification card; safe-and-well registry; foreign national/embassy flag; deceased-person handling (sensitive, restricted role); PFIF import/export; reunification report export. Satisfies FEATURES.md:810-817.
  Parallelization: Wave 34 | Blocked by: T72 | Blocks: T74
  References: FEATURES.md:785. `src/api/routes/reunification.ts`.
  Acceptance: notification workflow fires; QR card generates; PFIF import/export round-trips; deceased handling restricted to authorized role.
  QA: happy = notification+QR+PFIF+deceased; failure = unauthorized role → deceased view 403. Evidence `.omo/evidence/task-73-disaster-cf-replatform.txt`.
  Commit: Y | feat(missing): family notification + reunification center + QR + safe-and-well + PFIF + deceased handling

- [ ] 74. P4 integration gate: shelter check-in → match missing person → reunification
  What to do / Must NOT do: Integration test: shelter check-in matches a missing person → suggest → approve → reunification case + PFIF export. P4 gate.
  Parallelization: Wave 35 (P4 gate) | Blocked by: T65-T73 | Blocks: P5+
  References: FEATURES.md:583-636,784-818. `platform/worker/test/p4_integration.test.ts`.
  Acceptance: test green; covers encryption-at-rest + fuzzy match + PFIF round-trip.
  QA: happy = full P4 loop; failure = no match → no suggestion. Evidence `.omo/evidence/task-74-disaster-cf-replatform.txt`.
  Commit: Y | test(shelters): P4 integration gate (check-in→match→reunification)

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- PHASE P5: DATA INGESTION + WEATHER + POPULATION IMPACT — FEATURES.md:326-396, 955-990, 489-529 -->
<!-- Build blocks: :327 (raw_reports staging+Queues+zod+verify+Cron+HMAC+geocode+OCR+EXIF+dedupe), :956 (Open-Meteo+NWIS/CWC+OpenAQ+Blitzortung+IMD/JTWC+FWI), :490 (Kontur H3 pop_h3 + polygon→H3 cover→SUM) -->
<!-- NOTE (Metis B3/C3): Population Impact lives HERE (after census imports); pop_h3 row/size budget + polygon-size cap stated in T87. -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 75. Ingestion core: raw_reports staging + Queues + zod + verify queue + promote + Cron + HMAC webhooks + replayable log
  What to do / Must NOT do: One staging table `raw_reports(source,external_id UNIQUE-with-source,payload json,geo,observed_at,confidence,status)` via Queues; validate (zod) → human-verify queue (optional per source) → promote to typed tables. Pull feeds = Cron Triggers; push = HMAC-verified webhooks. Replayable ingest log (re-run promotion from raw_reports). Idempotency: `(source,external_id)` unique + message idempotency keys + webhook delivery-id dedupe. Satisfies FEATURES.md:330,340,367,368,369,372,373,376,379,380,381,394,395.
  Parallelization: Wave 36 | Blocked by: T6,T20 | Blocks: T76-T82, P6/P9/P10
  References: FEATURES.md:327. `src/db/schema/raw_reports.ts`, `src/ingestion/pipeline.ts`, `src/queues/ingestConsumer.ts`.
  Acceptance: ingest a record via queue → validates → promotes; replay re-runs promotion idempotently; HMAC invalid → 401; duplicate external_id → no-op.
  QA: happy = ingest+promote+replay+dedupe; failure = bad HMAC → 401 + audit. Evidence `.omo/evidence/task-75-disaster-cf-replatform.txt`.
  Commit: Y | feat(ingestion): raw_reports staging + Queues + zod + verify + promote + Cron + HMAC + replay

- [ ] 76. File/layer uploads (CSV/Excel/GeoJSON/KML/Shapefile/GPX/PDF/image/drone) + sensor webhook + mapping templates + quarantine
  What to do / Must NOT do: Manual entry + CSV (`papaparse`) + Excel (`SheetJS`) + GeoJSON + KML (`togeojson`) + Shapefile (`shpjs`) + GPX + PDF report (text extract in container) + image + drone image upload; sensor feed (generic webhook adapter); ingest mapping templates (saved column→field maps per source); quarantine queue for failed validation. Satisfies FEATURES.md:330-339,371,372.
  Parallelization: Wave 36 | Blocked by: T75 | Blocks: T77
  References: FEATURES.md:327. `src/api/routes/ingestUpload.ts`, `src/lib/ingest/parsers.ts`.
  Acceptance: each format uploads → parses → stages in raw_reports; invalid rows quarantined; mapping template applies column→field.
  QA: happy = 9 formats + templates + quarantine; failure = malformed shapefile → quarantined. Evidence `.omo/evidence/task-76-disaster-cf-replatform.txt`.
  Commit: Y | feat(ingestion): file/layer uploads (9 formats) + sensor webhook + mapping templates + quarantine

- [ ] 77. Feed imports: weather(Open-Meteo) + seismic(USGS) + river(NWIS/CWC) + fire(NASA FIRMS) + satellite(GDACS/Copernicus) + road closure + emergency call
  What to do / Must NOT do: Weather feed (Open-Meteo cron), seismic (USGS GeoJSON feed), river gauge (USGS NWIS / CWC India-WRIS), fire detection (NASA FIRMS VIIRS/MODIS API), satellite detection (GDACS, Copernicus EMS), road closure feed, emergency call feed. Each = thin adapter + integrations row + cron. Free/no-key first. Satisfies FEATURES.md:341-347.
  Parallelization: Wave 37 | Blocked by: T75 | Blocks: T78
  References: FEATURES.md:327,341-347. `src/ingest/feeds/*.ts`.
  Acceptance: each feed cron pulls → stages raw_reports with provenance; idempotent (re-pull no dup); free feeds tested live, others stubbed.
  QA: happy = 7 feeds; failure = feed down → last_success_at stale + alert. Evidence `.omo/evidence/task-77-disaster-cf-replatform.txt`.
  Commit: Y | feat(ingestion): 7 feed imports (weather/seismic/river/fire/satellite/road/call)

- [ ] 78. Registry imports: shelter/hospital/volunteer/asset/building(Overture/MS)/census/population grid(Kontur H3/WorldPop) + power/cell/radio outage + social/public report
  What to do / Must NOT do: Shelter registry, hospital registry, volunteer registry, asset inventory, building database (Overture/MS footprints), census data, population grid (Kontur H3 / WorldPop) — NOTE: pop grid feeds T87 pop_h3 preload; power/cell/radio outage feeds; social media report; public report form import. Satisfies FEATURES.md:348-360.
  Parallelization: Wave 37 | Blocked by: T75 | Blocks: T79
  References: FEATURES.md:327,348-360. `src/ingest/registries/*.ts`.
  Acceptance: each registry imports → typed tables; building footprints joinable to zones; pop grid loads to pop_h3 (T87).
  QA: happy = 10 registry imports; failure = invalid census row → quarantined. Evidence `.omo/evidence/task-78-disaster-cf-replatform.txt`.
  Commit: Y | feat(ingestion): registry imports (shelter/hospital/volunteer/asset/building/census/pop/outages×3/social/public)

- [ ] 79. Channel imports: SMS/WhatsApp/email/Telegram/IVR + RSS/Atom + CAP alert feed (SACHET/IPAWS) + webhook + API + scheduled sync + manual trigger
  What to do / Must NOT do: SMS (Twilio/MSG91 inbound webhook), WhatsApp (Cloud API webhook), email (CF Email Workers), Telegram (Bot API), IVR (Twilio/Exotel voice keypad + transcript); RSS/Atom feed; CAP alert feed (CAP v1.2 XML parse; SACHET/IPAWS); webhook data import; API data import; scheduled data sync (Cron); manual sync trigger. Satisfies FEATURES.md:360-370.
  Parallelization: Wave 38 | Blocked by: T75 | Blocks: T80
  References: FEATURES.md:327,360-369. `src/ingest/channels/*.ts`.
  Acceptance: each channel inbound → raw_reports; CAP XML parses to alert; manual trigger re-runs a source; idempotent.
  QA: happy = 9 channels + CAP + manual; failure = bad CAP XML → quarantined. Evidence `.omo/evidence/task-79-disaster-cf-replatform.txt`.
  Commit: Y | feat(ingestion): channel imports (SMS/WhatsApp/email/Telegram/IVR/RSS/CAP/webhook/API) + scheduled/manual sync

- [ ] 80. Ingestion quality: duplicate detection + embedding near-dup (Vectorize) + validation + confidence + source reliability + human verification + conflict detection + normalization + enrichment
  What to do / Must NOT do: Duplicate detection (unique keys); embedding-based near-duplicate (Vectorize cosine); data validation (zod); data confidence scoring; source reliability scoring (rolling accuracy per source); human verification workflow; conflicting report detection (same geo+time window, different values); data normalization; data enrichment. Satisfies FEATURES.md:374-382.
  Parallelization: Wave 38 | Blocked by: T75 | Blocks: T81
  References: FEATURES.md:327. `src/lib/dedupe/embedding.ts` (v1 `verify.py` ported to TS).
  Acceptance: near-dup via embedding cosine merges; conflict flagged; source reliability updates on verify outcome; enrichment fills missing fields.
  QA: happy = dedupe+conflict+reliability+enrich; failure = low-confidence source → flagged for verify. Evidence `.omo/evidence/task-80-disaster-cf-replatform.txt`.
  Commit: Y | feat(ingestion): dedupe + embedding near-dup + confidence + reliability + verification + conflict + enrichment

- [ ] 81. Ingestion enrichment: language detection + machine translation + image moderation gate + geocoding + reverse geocoding + bulk geocode (Queue) + attachment/EXIF metadata + OCR + timestamp normalization + provenance
  What to do / Must NOT do: Language detection (`franc`/AI); machine translation on ingest (AI translate, keep original); image moderation gate (vision model NSFW/gore check); geocoding pipeline (Nominatim/Photon + cache table); reverse geocoding; bulk geocode job (geocodeQ batch); attachment metadata extraction; image metadata; EXIF location (`exifr`); OCR (Workers AI vision / Tesseract container); timestamp normalization; source provenance tracking. Satisfies FEATURES.md:383-393.
  Parallelization: Wave 39 | Blocked by: T75 | Blocks: T82
  References: FEATURES.md:327. `src/lib/geo/geocode.ts`, `src/queues/geocodeConsumer.ts`.
  Acceptance: language detected + translated; NSFW image gated; geocode fills geo; EXIF → geo pin; OCR extracts text; bulk geocode via geocodeQ.
  QA: happy = 11 enrichment steps; failure = geocoder down → cached or stub. Evidence `.omo/evidence/task-81-disaster-cf-replatform.txt`.
  Commit: Y | feat(ingestion): language/translation/moderation/geocode/EXIF/OCR/provenance enrichment

- [ ] 82. Schema drift alerts (Data Ingestion loose end)
  What to do / Must NOT do: Schema drift alerts when a source's payload shape changes. Satisfies FEATURES.md:373.
  Parallelization: Wave 39 | Blocked by: T75 | Blocks: —
  References: FEATURES.md:327,373. `src/ingestion/drift.ts`.
  Acceptance: a source payload with a new/missing field → drift alert raised.
  QA: happy = drift detected; failure = unchanged schema → no alert. Evidence `.omo/evidence/task-82-disaster-cf-replatform.txt`.
  Commit: Y | feat(ingestion): schema drift alerts

- [ ] 83. Weather: current/forecast/rain/wind/humidity/temp/heat-index/UV + air quality(OpenAQ) + river(NWIS/CWC) + reservoir + tide + storm surge + lightning(Blitzortung) + cyclone(IMD/JTWC) + source comparison + confidence + manual input
  What to do / Must NOT do: Open-Meteo (free, no key) cron per incident bbox → `weather_obs` / `weather_forecast`. River = USGS NWIS / CWC India-WRIS; air = OpenAQ; lightning = Blitzortung; cyclone tracks = IMD/JTWC bulletins. Current/forecast/rain/wind/humidity/temp/heat-index/UV panels. Reservoir/tide/storm-surge tracking. Forecast comparison; weather confidence scoring; manual weather data input; weather source comparison. Satisfies FEATURES.md:959-970,986,987,988,989.
  Parallelization: Wave 40 | Blocked by: T77 | Blocks: T84
  References: FEATURES.md:956. `src/db/schema/weather.ts`, `src/ingest/feeds/weather.ts`.
  Acceptance: weather cron populates obs+forecast; river/air/lightning/cyclone tracked; confidence computed; manual input accepted.
  QA: happy = 14 weather metrics; failure = Open-Meteo down → stale + alert. Evidence `.omo/evidence/task-83-disaster-cf-replatform.txt`.
  Commit: Y | feat(weather): obs/forecast + air/river/reservoir/tide/surge/lightning/cyclone + confidence + manual

- [ ] 84. Weather indices + impact: FWI + flood/landslide/heatwave risk + smoke/plume estimate + impact explanation + op risk score + evac timing + responder safety + shelter/route recommendation
  What to do / Must NOT do: FWI (fire weather index calc); flood risk index; landslide risk index (slope + rainfall threshold); heatwave risk index; smoke spread estimate; chemical plume estimate (Gaussian plume, P9-fed); weather impact explanation (AI template citing rows); weather operation risk score; weather-based evacuation timing; responder safety alert; shelter recommendation; route recommendation. Satisfies FEATURES.md:971-985.
  Parallelization: Wave 40 | Blocked by: T83 | Blocks: T85
  References: FEATURES.md:956. `src/lib/weather/indices.ts`.
  Acceptance: FWI/flood/landslide/heatwave indices computed from obs; impact explanation cites obs rows; evac timing/route rec produced.
  QA: happy = indices+impact+timing+recs; failure = missing slope data → landslide index degraded. Evidence `.omo/evidence/task-84-disaster-cf-replatform.txt`.
  Commit: Y | feat(weather): risk indices + impact explanation + op risk + evac/responder/shelter/route recs

- [ ] 85. Population Impact: pop_h3 preload (Kontur H3) + affected population (polygon→H3 cover→SUM) + by zone/radius + vulnerable splits (elderly/children/disabled) + confidence
  What to do / Must NOT do: Preload Kontur Population dataset (H3 res 8, on HDX) for served regions → `pop_h3(h3,pop)` (batch load R2→D1). Any zone estimate = polygon → H3 cover → `SUM(pop)`. Alternates: WorldPop, GHSL, Meta HRSL; day/night = LandScan. Demographic splits = census ratio config per admin area. Confidence = dataset resolution + age heuristic. **Concrete budget/cap (Metis C3): pop_h3 preload ≤ 5,000,000 rows per region (D1 10GB Paid budget); any single zone query covering >50,000 H3 cells MUST split the AOI into sub-polygons OR downsample to H3 res 7 (coarser) — reject with a guidance error rather than run an unbounded join.** Satisfies FEATURES.md:493-496,524.
  Parallelization: Wave 41 | Blocked by: T78(pop grid import) | Blocks: T86-T88
  References: FEATURES.md:490. `src/db/schema/pop_h3.ts`, `src/lib/geo/popEstimate.ts`.
  Acceptance: preload pop_h3 for a region; polygon→H3 cover→SUM returns affected pop; vulnerable splits via census ratios; confidence computed. **Asserts: preload row count ≤ 5M for the test region; a 60,000-cell AOI is either split into 2 sub-queries or downsampled to res 7 (not run as one join); an AOI exceeding the cap without split/downsample is rejected with a guidance error.**
  QA: happy = preload+SUM+splits+confidence; failure = AOI exceeds cap → error with guidance. Evidence `.omo/evidence/task-85-disaster-cf-replatform.txt`.
  Commit: Y | feat(popimpact): pop_h3 preload + affected pop (H3 SUM) + vulnerable splits + confidence + budget/cap

- [ ] 86. Population Impact: facility estimates (hospital patients/school students/tourists/workers/households/buildings/critical facilities) + day/night + informal + livestock + languages + heatmap + by admin area/ward/district/census block + trend + building-level
  What to do / Must NOT do: Hospital patients affected (facility capacity × in-zone); school students; tourists; workers (day-population, LandScan); households (pop / avg household size); buildings affected (footprints in zone); critical facilities; day vs night toggle; informal settlement flag (higher vulnerability weight); livestock (rural; agri census config); languages-spoken (census ratios → alert language mix); heatmap (H3 hex layer); by administrative area/ward/district/census block; trend over time (zone version snapshots); building-level estimate (footprint area × floors heuristic). Satisfies FEATURES.md:497-516,527.
  Parallelization: Wave 41 | Blocked by: T85 | Blocks: T87
  References: FEATURES.md:490. `src/lib/geo/popEstimate.ts`.
  Acceptance: each facility/segment estimate computed; day/night toggle; heatmap renders; trend over snapshots; building-level per footprint.
  QA: happy = estimates+heatmap+trend+building-level; failure = missing footprints → buildings estimate degraded. Evidence `.omo/evidence/task-86-disaster-cf-replatform.txt`.
  Commit: Y | feat(popimpact): facility/segment estimates + day/night + informal + livestock + languages + heatmap + trend + building-level

- [ ] 87. Population Impact: needs estimates (evac/shelter/medical/food/water(Sphere)/trapped/unreachable) + manual override + source comparison + export report
  What to do / Must NOT do: People needing evacuation; shelter (evac × shelter-seeking ratio config); medical help; food; water (Sphere standards 15L/person/day); trapped; unreachable; manual override (override row wins, both kept); data source comparison; export population impact report. Satisfies FEATURES.md:517-526,528.
  Parallelization: Wave 42 | Blocked by: T85 | Blocks: T88
  References: FEATURES.md:490. `src/lib/geo/popNeeds.ts`.
  Acceptance: needs estimates computed; water uses Sphere 15L/person/day; manual override wins + both kept; export PDF.
  QA: happy = needs+override+export; failure = no evac ratio config → default + warn. Evidence `.omo/evidence/task-87-disaster-cf-replatform.txt`.
  Commit: Y | feat(popimpact): needs estimates (Sphere) + manual override + source comparison + export

- [ ] 88. P5 integration gate: feed pull → ingest → verify → pop estimate → weather index
  What to do / Must NOT do: Integration test: Open-Meteo cron pulls → stages → promotes → pop estimate for a flood zone → weather flood risk index. P5 gate.
  Parallelization: Wave 43 (P5 gate) | Blocked by: T75-T87 | Blocks: P6+
  References: FEATURES.md:326-396,489-529,955-990. `platform/worker/test/p5_integration.test.ts`.
  Acceptance: test green; covers idempotent re-pull + dedupe + pop_h3 SUM + weather index.
  QA: happy = full P5 loop; failure = feed down → stale alert. Evidence `.omo/evidence/task-88-disaster-cf-replatform.txt`.
  Commit: Y | test(ingestion): P5 integration gate (feed→ingest→verify→pop→weather)

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- PHASE P6: COMMUNICATIONS + PUBLIC PORTAL — FEATURES.md:1035-1085, 1192-1227 -->
<!-- Build blocks: :1036 (alerts→approval→Workflow fanout→per-channel Queues+DLQ; CAP v1.2; targeting polygon→H3), :1193 (unauthenticated routes+KV cache+public serializer+PWA+CAP/RSS) -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 89. Alerts schema + approval workflow + fanout Workflow + per-channel Queues (idempotent + DLQ) + alert_deliveries
  What to do / Must NOT do: `alerts(audience query,channels[],content per-lang,status)` → approval → Workflow fanout → per-channel Queues (`alertQ` + DLQ) with per-message idempotency. Delivery status = provider webhooks → `alert_deliveries`. Satisfies FEATURES.md:1039,1040,1054,1065,1066 (public/internal alert builder, approval, delivery status, bounce).
  Parallelization: Wave 44 | Blocked by: T88 | Blocks: T90-T94
  References: FEATURES.md:1036. `src/db/schema/alerts.ts`, `src/workflows/alertFanout.ts`, `src/queues/alertConsumer.ts`.
  Acceptance: approve alert → fanout enqueues per-channel messages idempotently; delivery webhook updates `alert_deliveries`; replay idempotent.
  QA: happy = fanout+delivery+idempotent; failure = provider down → DLQ + retry. Evidence `.omo/evidence/task-89-disaster-cf-replatform.txt`.
  Commit: Y | feat(comms): alerts schema + approval + fanout Workflow + per-channel Queues + DLQ

- [ ] 90. Channel adapters (SMS/voice/TTS + WhatsApp templates + email Resend/SES + push FCM/WebPush VAPID + Telegram) — one fanout engine, 5 channel todos batched
  What to do / Must NOT do: ONE channel-adapter interface, 5 implementations: MSG91/Twilio (SMS + voice w/ TTS), WhatsApp Cloud API templates, Resend/SES email, FCM + Web Push (VAPID), Telegram. Each behind adapter + integrations row + env secret; stubbed in dev. (Metis D4: channels share fanout → one todo.) Satisfies FEATURES.md:1041,1042,1043,1044,1045,1046,1047.
  Parallelization: Wave 44 | Blocked by: T89 | Blocks: T91
  References: FEATURES.md:1036. `src/comms/channels/*.ts`.
  Acceptance: each channel sends via adapter (stubbed returns fixture); real-key path unit-tested with mocked HTTP; delivery webhook recorded.
  QA: happy = 5 channels; failure = adapter down → DLQ. Evidence `.omo/evidence/task-90-disaster-cf-replatform.txt`.
  Commit: Y | feat(comms): 5 channel adapters (SMS/voice, WhatsApp, email, push, Telegram)

- [ ] 91. Alert targeting (location polygon→H3, role, shelter, evac-zone) + resend/cancel/correction + read receipts + public-safe redaction
  What to do / Must NOT do: Location-targeted (polygon → subscriber H3 match); role-targeted; shelter-targeted; evacuation-zone alerts; alert resend; cancellation; correction; read receipts (tracked links / provider callbacks); alert public-safe redaction (serializer). Satisfies FEATURES.md:1058,1059,1060,1061,1062,1063,1064,1067,1068.
  Parallelization: Wave 45 | Blocked by: T89 | Blocks: T92
  References: FEATURES.md:1036. `src/lib/comms/targeting.ts`.
  Acceptance: polygon targeting matches subscribers in H3 cover; resend/cancel/correction work; read receipts tracked; redaction strips sensitive on public alert.
  QA: happy = targeting+resend+receipts+redaction; failure = subscriber outside polygon → not targeted. Evidence `.omo/evidence/task-91-disaster-cf-replatform.txt`.
  Commit: Y | feat(comms): targeting (location/role/shelter/zone) + resend/cancel/correction + read receipts + redaction

- [ ] 92. CAP v1.2 export + import relay (SACHET/IPAWS) + alert template library + multilingual AI generation + AI TTS voice + cell-broadcast note
  What to do / Must NOT do: CAP v1.2 export (SACHET/IPAWS interop); CAP v1.2 import relay; cell broadcast (WEA) integration note only (gov-gated, NOT built — explicit OUT); alert template library; multilingual alert generation (AI translate + review queue); AI text-to-speech voice alert generation. Satisfies FEATURES.md:1069,1070,1071,1055,1056,1057.
  Parallelization: Wave 45 | Blocked by: T89 | Blocks: T93
  References: FEATURES.md:1036. `src/lib/comms/cap.ts`. NOTE: cell broadcast is a documented note, not a built integration (FEATURES.md:1071 self-scopes).
  Acceptance: CAP XML export validates against CAP v1.2 schema; import relay ingests SACHET/IPAWS; multilingual drafts land for review; TTS audio generated.
  QA: happy = CAP export/import + multilingual + TTS; failure = invalid CAP → rejected. Evidence `.omo/evidence/task-92-disaster-cf-replatform.txt`.
  Commit: Y | feat(comms): CAP v1.2 export/import + templates + multilingual + AI TTS + WEA note

- [ ] 93. Comms drafts: radio message + ham frequency plan (ICS-205) + loudspeaker/PA script + social posts + website banner + status page updates + rumor correction + misinformation + press release + media kit + embeddable widget + sitrep/FAQ/hotline/door-to-door scripts + brevity + blackout plan + offline bulletin + poster
  What to do / Must NOT do: Radio message drafts; ham radio frequency plan export (ICS-205); loudspeaker/PA script export; social media post drafts; website banner alerts; public status page updates; rumor correction message builder; misinformation response drafts; press release generator; media kit export; embeddable alert widget for news sites; situation update generator; public FAQ generator; hotline script generator; door-to-door script generator; field radio brevity formatter; communication blackout fallback plan; offline bulletin export; printable poster export. Many are AI drafts (P7 wrapper) → human review. Satisfies FEATURES.md:1048-1053,1072-1084.
  Parallelization: Wave 46 | Blocked by: T89 | Blocks: T94
  References: FEATURES.md:1036. `src/api/routes/commsDrafts.ts`.
  Acceptance: each draft type generates a draft artifact (review_status=draft); poster/bulletin export as PDF; embeddable widget iframe renders.
  QA: happy = 18 draft/export types; failure = AI down → fallback template draft. Evidence `.omo/evidence/task-93-disaster-cf-replatform.txt`.
  Commit: Y (split per mechanism family, per orphan guard) | feat(comms): radio/ham/PA scripts; feat(comms): social/banner/status/rumor/press; feat(comms): media-kit/widget/sitrep/FAQ/scripts; feat(comms): brevity/blackout/bulletin/poster

- [ ] 94. P6 comms integration gate: build alert → approve → fanout → delivery status → CAP export
  What to do / Must NOT do: Integration test: build alert → approve → fanout to 2 channels (stubbed) → delivery status → CAP export validates. P6 comms gate.
  Parallelization: Wave 47 (P6 comms gate) | Blocked by: T89-T93 | Blocks: P7
  References: FEATURES.md:1035-1085. `platform/worker/test/p6_comms.test.ts`.
  Acceptance: test green; covers idempotent fanout + DLQ + CAP validation + redaction.
  QA: happy = full comms loop; failure = channel down → DLQ. Evidence `.omo/evidence/task-94-disaster-cf-replatform.txt`.
  Commit: Y | test(comms): P6 comms integration gate (alert→approve→fanout→delivery→CAP)

- [ ] 95. Public Portal core: unauthenticated routes + KV/cache + public serializer + PWA + low-bandwidth + multilingual + a11y
  What to do / Must NOT do: Separate unauthenticated Worker routes; aggressive KV/cache. Public serializer enforced (one place). PWA installable; one-file HTML fallback. Public multilingual content; public low-bandwidth page (no JS fallback); public accessibility mode; screen-reader optimized pages. Satisfies FEATURES.md:1196-1217,1219.
  Parallelization: Wave 47 | Blocked by: T6,T88 | Blocks: T96-T100
  References: FEATURES.md:1193. `src/api/routes/public/*.ts`.
  Acceptance: public routes render only `visibility=public` data (test a sensitive row is omitted); KV cache hit on 2nd call; low-bandwidth page loads without JS; axe-core clean.
  QA: happy = public+cache+lowband+a11y; failure = sensitive leak → test fails. Evidence `.omo/evidence/task-95-disaster-cf-replatform.txt`.
  Commit: Y | feat(public): unauthenticated routes + KV cache + serializer + PWA + low-bandwidth + a11y

- [ ] 96. Public incident page + map + alerts + CAP/RSS feed + shelter finder + evacuation route finder (evac wires in P8) + safety instructions
  What to do / Must NOT do: Public incident page; public map (public layers only); public alerts; public CAP/RSS feed; public shelter finder; public evacuation route finder (NOTE: full evac routing wires in P8 — skeleton here); public safety instructions. Satisfies FEATURES.md:1196,1197,1198,1199,1200,1201,1202.
  Parallelization: Wave 48 | Blocked by: T95 | Blocks: T97
  References: FEATURES.md:1193. `src/api/routes/public/incident.ts`.
  Acceptance: public map renders public layers only; CAP/RSS feed valid; shelter finder returns nearest; evac route finder skeleton (wires in P8).
  QA: happy = 7 public pages; failure = evac route not yet wired → "coming soon" state. Evidence `.omo/evidence/task-96-disaster-cf-replatform.txt`.
  Commit: Y | feat(public): incident/map/alerts/CAP-RSS/shelter/evac-route/safety pages

- [ ] 97. Public report submission (Turnstile) + missing person submission + donation page + volunteer signup + FAQ + SMS/IVR info + rumor reporting + subscription
  What to do / Must NOT do: Public report submission (Turnstile); public missing person submission; public donation page; public volunteer signup; public FAQ; public SMS instructions (keyword autoresponder); public IVR info line; public rumor reporting; public status update subscription (location polygon subscribe). Satisfies FEATURES.md:1203,1204,1205,1206,1207,1211,1212,1213,1214.
  Parallelization: Wave 48 | Blocked by: T95 | Blocks: T98
  References: FEATURES.md:1193. `src/api/routes/public/forms.ts`.
  Acceptance: Turnstile protects report/missing forms; SMS keyword autoresponder; subscription stores point/polygon + channel prefs.
  QA: happy = 9 public interactions; failure = bot submission → Turnstile rejects. Evidence `.omo/evidence/task-97-disaster-cf-replatform.txt`.
  Commit: Y | feat(public): report/missing/donation/volunteer/FAQ/SMS/IVR/rumor/subscription

- [ ] 98. Public printable instructions + offline packet + kiosk + embeddable widgets + safe-route + family check-in + safe-and-well + donation needs + trusted links + privacy notice
  What to do / Must NOT do: Public printable instructions; public offline downloadable packet; kiosk display mode; embeddable public widgets; public safe-route guidance; public family check-in; public safe-and-well registry; public donation needs list; public trusted source links; public privacy notice. Satisfies FEATURES.md:1208,1210,1216,1218,1220,1221,1222,1223,1224,1225,1226.
  Parallelization: Wave 49 | Blocked by: T95 | Blocks: T99
  References: FEATURES.md:1193. `src/api/routes/public/*.ts`.
  Acceptance: printable PDF; offline packet (one JSON bundle + one-file HTML); kiosk mode via signed URL; widgets embed; family check-in + safe-and-well work.
  QA: happy = 11 public features; failure = expired kiosk URL → 403. Evidence `.omo/evidence/task-98-disaster-cf-replatform.txt`.
  Commit: Y | feat(public): printable/offline-packet/kiosk/widgets/safe-route/family/safe-and-well/donation/links/privacy

- [ ] 99. P6 public-portal integration gate: public site renders only public data across all public pages
  What to do / Must NOT do: Integration test: drive every public route with a mix of public/internal/sensitive/draft entities; assert only public+official fields render. P6 public gate.
  Parallelization: Wave 50 (P6 public gate) | Blocked by: T95-T98 | Blocks: P7
  References: FEATURES.md:1192-1227. `platform/worker/test/p6_public.test.ts`.
  Acceptance: test green; sensitive/internal/draft data never appears on any public route (F4 invariants enforced).
  QA: happy = zero leaks; failure = any leak → fails with route name. Evidence `.omo/evidence/task-99-disaster-cf-replatform.txt`.
  Commit: Y | test(public): P6 public-portal integration gate (public-data-only enforcement)

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- PHASE P7: AI CONFIGURATION + REPORTS — FEATURES.md:397-488, 1228-1272 -->
<!-- Build blocks: :398 (provider config user→incident→org; one OpenAI-compatible call wrapper; zod+retry; ai_calls log; prompts table; injection firewall; PII mask; Workers AI fallback), :1229 (template+frozen snapshot→md→HTML→PDF Browser Rendering; pdf-lib/docx; ICS pack; signed-token share; Cron schedule) -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 100. AI infra: provider config (user→incident→org resolution) + one call wrapper + zod+retry + fallback chain + ai_calls logging
  What to do / Must NOT do: Provider config `{baseUrl,apiKey,model,headers,endpointPath}` resolved user→incident→org. One call wrapper: OpenAI-compatible `chat.completions`, JSON mode, zod schema parse with 1 retry (feed parse error back), AbortController timeout, fallback model → fallback provider chain. Log every call (`ai_calls`: prompt name+version, tokens, latency, est cost) → D1 + Analytics Engine. Workers AI zero-key fallback. AI temperature settings (L436, exposed in config + passed to call wrapper). Satisfies FEATURES.md:401-411,431,432,433,434,435,436,437,438,439,440,449,451,452.
  Parallelization: Wave 51 | Blocked by: T20,T88 (AI infra needs Core gate + ingestion/AI Consumers ready; NOT blocked by P6 public-portal — P7 serializes after P5, parallel to P6) | Blocks: T101-T108, all AI consumers
  References: FEATURES.md:398. `src/lib/ai/provider.ts`, `src/lib/ai/call.ts`, `src/db/schema/ai_calls.ts`.
  Acceptance: call wrapper returns zod-validated JSON; on parse-fail retries once with error fed back; timeout fires; fallback chain tried; ai_calls row logged per call; Workers AI fallback used when no key. **L437 reasoning-effort: the `reasoning_effort` param is forwarded to the provider request (assert the outbound request body carries it). L438 streaming: an SSE-passthrough call returns chunked tokens (`text/event-stream`) until `[DONE]`; a non-streaming call returns one JSON object.**
  QA: happy = call+validate+retry+fallback+log; failure = all providers down → typed error + logged. Evidence `.omo/evidence/task-100-disaster-cf-replatform.txt`.
  Commit: Y | feat(ai): provider config + one call wrapper + zod/retry/fallback + ai_calls logging

- [ ] 101. AI safety: injection firewall + PII masking + safe mode + prompt versioning/library/variables/preview/A-B + safe rewriting + cost caps + disabled mode
  What to do / Must NOT do: Injection defense (untrusted data fenced + instruction firewall preamble); PII mask pass (regex + NER prompt) before send when `safe mode` on; AI safe mode (masking on, approval mandatory); AI cost control (per-tenant spend caps); AI disabled mode; prompt versioning (`prompts(name,version,body with {{vars}},schema)` table); prompt library; prompt variables; prompt preview (render with sample data); prompt A/B comparison; AI public-safe rewriting. Satisfies FEATURES.md:412-430,419,420,453,454,455.
  Parallelization: Wave 51 | Blocked by: T100 | Blocks: T102
  References: FEATURES.md:398. `src/lib/ai/{injectionFirewall,piiMask,safeMode}.ts`, `src/db/schema/prompts.ts`.
  Acceptance: fenced untrusted data doesn't leak instructions; PII masked in safe mode; prompt preview renders vars; A/B compares two versions; spend cap blocks over-budget.
  QA: happy = firewall+mask+preview+AB+cap; failure = injection attempt → blocked + logged. Evidence `.omo/evidence/task-101-disaster-cf-replatform.txt`.
  Commit: Y | feat(ai): injection firewall + PII mask + safe mode + prompt versioning/library/vars/preview/AB + cost caps

- [ ] 102. AI outputs: structured JSON + citation requirement (validate row ids exist) + confidence + uncertainty + hallucination warning + human approval gate + red-team/jailbreak test suite + eval harness + audit replay + diff viewer
  What to do / Must NOT do: AI structured JSON outputs; citation requirement (must cite data row ids; validate they exist); AI confidence score; uncertainty flag; hallucination warning; human approval gate (draft→approve, global convention); red-team test mode; jailbreak/injection test suite (golden attack set in CI); eval harness with golden set (fixture inputs → expected schema/quality); audit replay; answer comparison; output diff viewer. Satisfies FEATURES.md:441-452,445-448.
  Parallelization: Wave 52 | Blocked by: T101 | Blocks: T103-T108
  References: FEATURES.md:398,441-452. `src/lib/ai/eval.ts`, `src/ai-tests/golden/*.json`.
  Acceptance: structured output validates zod; citations validated to exist; confidence/uncertainty/hallucination flags; golden eval passes; jailbreak attack set blocked in CI.
  QA: happy = structured+citations+eval+jailbreak; failure = hallucinated citation → rejected. Evidence `.omo/evidence/task-102-disaster-cf-replatform.txt`.
  Commit: Y | feat(ai): structured output + citation validation + confidence + eval harness + jailbreak suite + diff

- [ ] 103. AI generation features: incident summary + report + task + evac/shelter/responder/weather/logistics recs + public alert + command briefing + radio/SMS/email/social drafts
  What to do / Must NOT do: AI incident summary generation; report generation; task generation; evacuation recommendation; shelter recommendation; responder prioritization; weather impact explanation; logistics explanation; public alert drafting; command briefing generation; radio message drafting (brevity codes, char limits); SMS message drafting (160-char aware); email message drafting; social post drafting; missing-data question generation. Each = a prompt template + zod schema + draft-status artifact (per Conventions). Satisfies FEATURES.md:456-471.
  Parallelization: Wave 52 | Blocked by: T102 | Blocks: T104
  References: FEATURES.md:398,456-471. `src/lib/ai/prompts/*.ts`.
  Acceptance: each generation produces a draft artifact with citations + confidence; radio/SMS respect char limits; missing-data questions generated.
  QA: happy = 15 generation types; failure = parse fail → retry once then fallback. Evidence `.omo/evidence/task-103-disaster-cf-replatform.txt`.
  Commit: Y | feat(ai): 15 generation features (summary/report/task/recs×7/alert/briefing/radio/SMS/email/social/questions)

- [ ] 104. AI copilots (operator/field/PIO/logistics/shelter/medical-triage) + tool-calling allowlist + RAG corpus per copilot + policy compliance checker + risk/timeline/anomaly/quality/conflict explanations + decision memo + AAR writer
  What to do / Must NOT do: Operator copilot (chat over incident state, tool-calling allowlist); field responder copilot; PIO copilot; logistics copilot; shelter manager copilot; medical triage copilot. RAG corpus selection per copilot (Vectorize namespaces). Tool-calling allowlist per copilot (read-only tools by default). AI policy compliance checker; risk explanation engine; timeline reconstruction; anomaly detection (prompt analysis); data quality explanation; source conflict explanation; decision memo writer; after-action report writer. Satisfies FEATURES.md:472-488.
  Parallelization: Wave 53 | Blocked by: T102 | Blocks: T105
  References: FEATURES.md:398,472-488. `src/lib/ai/copilots/*.ts`.
  Acceptance: each copilot chats over incident state with read-only tool allowlist; RAG namespace scoped; tool calls validated against allowlist; memo/AAR draft generated.
  QA: happy = 6 copilots + tool allowlist + RAG + explanations + memo/AAR; failure = disallowed tool call → blocked. Evidence `.omo/evidence/task-104-disaster-cf-replatform.txt`.
  Commit: Y | feat(ai): 6 copilots + tool allowlist + RAG namespaces + compliance/risk/timeline/anomaly + memo/AAR

- [ ] 105. AI latency tracking + injection detection + multilingual translation (human review queue)
  What to do / Must NOT do: AI latency tracking; AI prompt injection detection; AI multilingual translation (translate + human review queue). Satisfies FEATURES.md:452,453,465.
  Parallelization: Wave 53 | Blocked by: T101 | Blocks: T106
  References: FEATURES.md:398. `src/lib/ai/{latency,injectionDetect}.ts`.
  Acceptance: latency tracked per call; injection detection flags suspicious prompts; translation drafts land in review queue.
  QA: happy = latency+injection+translation; failure = injection → flagged + blocked. Evidence `.omo/evidence/task-105-disaster-cf-replatform.txt`.
  Commit: Y | feat(ai): latency tracking + injection detection + multilingual translation review queue

- [ ] 106. AI API (Developer Platform preview) + AI monitor (latency/error/token charts) + AI usage analytics
  What to do / Must NOT do: AI API route (for Developer Platform); AI monitor (latency/error/token charts); AI usage analytics (from ai_calls). NOTE: full Developer Platform in P11; here expose the AI API surface + monitor. Satisfies FEATURES.md:1593,1576,1304.
  Parallelization: Wave 54 | Blocked by: T100 | Blocks: P11 devplatform
  References: FEATURES.md:398,1593,1576. `src/api/routes/ai.ts`.
  Acceptance: AI API callable with key+scope; monitor renders latency/error/token charts from ai_calls.
  QA: happy = API+monitor+analytics; failure = over scope → 403. Evidence `.omo/evidence/task-106-disaster-cf-replatform.txt`.
  Commit: Y | feat(ai): AI API + monitor (latency/error/tokens) + usage analytics

- [ ] 107. Reports engine: template (Markdown + {{query}} placeholders) + frozen snapshot → md → HTML → PDF (Browser Rendering) + versions + comments + share (signed token) + schedule (Cron)
  What to do / Must NOT do: Report = template (Markdown + `{{query}}` placeholders) + frozen data snapshot → render md → HTML → PDF via Browser Rendering; versions table; report comments; sharing via signed-token links; auto-scheduled reports (Cron). Satisfies FEATURES.md:1257-1270.
  Parallelization: Wave 54 | Blocked by: T99 | Blocks: T108-T111
  References: FEATURES.md:1229. `src/lib/reports/render.ts`, `src/workflows/scheduledReport.ts`.
  Acceptance: render a report → PDF via Browser Rendering; version history; share link signed + expiry; scheduled report produces + stores.
  QA: happy = render+version+share+schedule; failure = expired share token → 403. Evidence `.omo/evidence/task-107-disaster-cf-replatform.txt`.
  Commit: Y | feat(reports): template+snapshot→md→HTML→PDF + versions + comments + signed share + Cron schedule

- [ ] 108. Report types: sitrep + IAP (ICS-202+204) + op-period + evac + shelter + resource + medical + infra + weather + damage + volunteer + missing + public-comms + after-action + custom builder
  What to do / Must NOT do: Situation report; incident action plan (ICS-202+204 pack); operational period report; evacuation report; shelter report; resource report; medical report; infrastructure report; weather impact report; damage assessment report; volunteer report; missing persons report; public communication report; after-action report; custom report builder. Satisfies FEATURES.md:1232-1245,1271.
  Parallelization: Wave 55 | Blocked by: T107 | Blocks: T109
  References: FEATURES.md:1229. `src/lib/reports/templates/*.ts`.
  Acceptance: each report type renders from a frozen snapshot; custom builder composes arbitrary widgets.
  QA: happy = 15 report types + custom; failure = missing data → section shows "no data". Evidence `.omo/evidence/task-108-disaster-cf-replatform.txt`.
  Commit: Y | feat(reports): 15 report types (sitrep/IAP/op-period/evac/shelter/resource/medical/infra/weather/damage/volunteer/missing/comms/AAR) + custom builder

- [ ] 109. ICS form pack export (201/202/204/205/209/214) + 3W + HXL CSV + OCHA donor sitrep + executive summary + appendices (technical/map/timeline/source/data-quality/decision-log) + AI drafts + human approval
  What to do / Must NOT do: ICS form pack export (201/202/204/205/209/214); 3W report (who-what-where, humanitarian); HXL-tagged CSV export; OCHA-style donor sitrep; executive summary; technical/map/timeline/source/data-quality/decision-log appendices; AI-generated report drafts + human approval workflow. Satisfies FEATURES.md:1246-1256,1258.
  Parallelization: Wave 55 | Blocked by: T107 | Blocks: T110
  References: FEATURES.md:1229. `src/lib/reports/ics.ts`, `src/lib/reports/hxl.ts`.
  Acceptance: ICS pack exports all 6 forms; HXL CSV valid; OCHA sitrep renders; appendices render; AI drafts land for approval.
  QA: happy = ICS pack+3W+HXL+OCHA+appendices+AI; failure = AI draft not approved → not published. Evidence `.omo/evidence/task-109-disaster-cf-replatform.txt`.
  Commit: Y | feat(reports): ICS pack + 3W + HXL CSV + OCHA + executive summary + appendices + AI drafts

- [ ] 110. Report exports: PDF (Browser Rendering) + DOCX (docx npm) + Markdown + JSON + CSV + public-safe + confidential + report template library
  What to do / Must NOT do: Report export to PDF (Browser Rendering); DOCX (`docx` npm); Markdown; JSON; CSV; public-safe report export (serializer); confidential report export (watermarked); report template library. Satisfies FEATURES.md:1261-1268,1270.
  Parallelization: Wave 56 | Blocked by: T107 | Blocks: T111
  References: FEATURES.md:1229. `src/lib/reports/export.ts`.
  Acceptance: each format exports correctly; public-safe strips sensitive; confidential watermarks (user+ts).
  QA: happy = 6 formats + public/confidential + library; failure = public-safe leak → test fails. Evidence `.omo/evidence/task-110-disaster-cf-replatform.txt`.
  Commit: Y | feat(reports): PDF/DOCX/MD/JSON/CSV exports + public-safe + confidential + template library

- [ ] 111. P7 integration gate: AI draft → human approve → report → PDF export
  What to do / Must NOT do: Integration test: generate an AI incident summary draft → human approve → render sitrep report → PDF export. P7 gate.
  Parallelization: Wave 57 (P7 gate) | Blocked by: T100-T110 | Blocks: P8+
  References: FEATURES.md:397-488,1228-1272. `platform/worker/test/p7_integration.test.ts`.
  Acceptance: test green; covers injection firewall + citation validation + draft→approve→report→PDF + cost logged.
  QA: happy = full P7 loop; failure = unapproved draft → not in report. Evidence `.omo/evidence/task-111-disaster-cf-replatform.txt`.
  Commit: Y | test(ai): P7 integration gate (AI draft→approve→report→PDF)

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- PHASE P8: EVACUATION + MEDICAL + LOGISTICS + INFRASTRUCTURE — FEATURES.md:530-582, 819-856, 857-914, 915-954 -->
<!-- Build blocks: :531 (OSM road graph→D1 edges; Dijkstra/A* in Worker city-scale or Valhalla/OSRM large; hazard edge weights; BPR congestion; zone lifecycle), :820 (facilities+capacity+FHIR+triage START/SALT/JumpSTART+QR wristband+MCI+encrypted cols), :858 (items/stock/movements ledger+state machine via Workflows+burn rate+html5-qrcode+EDXL-RM), :916 (assets+asset_dependencies DAG+BFS cascade) -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 112. Evacuation: road graph (OSM→D1 edges) + routing engine (Dijkstra/A* Worker; Valhalla/OSRM threshold) + hazard-aware edge weights + contraflow + BPR congestion
  What to do / Must NOT do: Road graph = OSM extract → `edges(nodes,length,capacity,oneway)` in D1 per region (offline job). Routing = Dijkstra/A* in Worker for city scale; Valhalla/OSRM/openrouteservice for large. **Concrete cap (Metis C4): in-Worker Dijkstra limited to ≤50,000 edges per request; graphs (or sub-graphs) larger than 50,000 edges MUST delegate to the external Valhalla/OSRM/openrouteservice adapter — the worker returns a 302/redirect to the external route rather than running an unbounded in-Worker search.** Hazard-aware = edge weight penalty/∞ when edge H3 intersects hazard layer. Contraflow = reversed-direction capacity flag. Congestion = demand/capacity (BPR function). Satisfies FEATURES.md:538-543,548.
  Parallelization: Wave 58 | Blocked by: T88 | Blocks: T113-T116
  References: FEATURES.md:531. `src/lib/routing/{dijkstra,bpr}.ts`, `src/db/schema/edges.ts`.
  Acceptance: route avoids blocked/dangerous edges; contraflow doubles capacity; BPR congestion computed; **a test with a 60,000-edge graph delegates to the external router (assert no in-Worker Dijkstra ran); a 5,000-edge graph routes in-Worker.**
  QA: happy = route+hazard+contraflow+BPR; failure = graph above cap → external router or error. Evidence `.omo/evidence/task-112-disaster-cf-replatform.txt`.
  Commit: Y | feat(evac): road graph + routing engine + hazard/contraflow/BPR + external threshold

- [ ] 113. Evacuation: recommend zones/phased order/start time/priority/routes/alternates/no-go + duration/congestion/vehicle/bus/ambulance/accessible demand + capacity analysis
  What to do / Must NOT do: Recommend evacuation zones (hazard layer+buffer+pop); phased order (nearest-risk-first batching); start time; priority; routes; alternate routes (k-shortest paths); no-go routes; estimate duration; congestion; vehicle demand; bus demand (carless pop ratio); ambulance demand; accessible transport demand; route capacity analysis. Satisfies FEATURES.md:534-548.
  Parallelization: Wave 58 | Blocked by: T112,T85(pop) | Blocks: T114
  References: FEATURES.md:531. `src/lib/recommend/evacPlan.ts`.
  Acceptance: recommend zones + phased order + routes; duration/congestion/demand estimates produced; k-shortest alternates returned.
  QA: happy = recs+estimates+alternates; failure = no road graph → degraded. Evidence `.omo/evidence/task-113-disaster-cf-replatform.txt`.
  Commit: Y | feat(evac): recommend zones/order/routes/alternates + duration/congestion/demand estimates

- [ ] 114. Evacuation: hazard-aware routing variants (flood/fire/wind/bridge-failure/signal/transit) + staging/pickup/assembly points + route map export + order builder + alert templates + zone status board
  What to do / Must NOT do: Flood-aware, fire-spread-aware, wind-aware, bridge-failure-aware, traffic-signal-disruption-aware, public-transit-disruption-aware routing; evacuation staging points; pickup points; assembly areas; route map export; evacuation order builder; evacuation alert templates; evacuation zone status board (advisory/ordered/cleared). Satisfies FEATURES.md:549-562.
  Parallelization: Wave 59 | Blocked by: T112 | Blocks: T115
  References: FEATURES.md:531. `src/lib/routing/hazardAware.ts`.
  Acceptance: each hazard variant reroutes; staging/pickup/assembly points placed; order builder produces an order; status board tracks zone lifecycle.
  QA: happy = 6 hazard variants + points + order + board; failure = hazard layer missing → default route. Evidence `.omo/evidence/task-114-disaster-cf-replatform.txt`.
  Commit: Y | feat(evac): hazard-aware routing variants + staging/pickup/assembly + order builder + zone status board

- [ ] 115. Evacuation compliance/tracking: compliance + completion + refusal + door-to-door tasking + household status + animal/hospital/school/prison/industrial support + fuel along routes + multilingual export + bottleneck detector + reverse warning + re-entry + permit (QR) + safe return
  What to do / Must NOT do: Compliance tracker; completion tracker; refusal tracker; door-to-door tasking (task batch per street segment); household status; animal/hospital/school/prison/industrial evacuation support; fuel availability along routes (station status layer); multilingual order export; bottleneck detector (max demand/capacity edges); reverse evacuation warning; re-entry planning; re-entry permit workflow (QR permits, scan validation); safe return notification. Satisfies FEATURES.md:563-581.
  Parallelization: Wave 59 | Blocked by: T114 | Blocks: T116
  References: FEATURES.md:531. `src/api/routes/evac.ts`.
  Acceptance: door-to-door tasks batch per segment; household status tracked; QR re-entry permit validates on scan; bottleneck detector flags max demand/capacity edges.
  QA: happy = compliance+door-to-door+permit+bottleneck; failure = invalid QR permit → rejected. Evidence `.omo/evidence/task-115-disaster-cf-replatform.txt`.
  Commit: Y | feat(evac): compliance/door-to-door/household/special-pop/fuel/bottleneck/re-entry permit

- [ ] 116. Medical: facilities + capacity (ICU/emergency beds/ambulance) + supply inventory + stockpile expiry + triage zone map + triage form (START/SALT/JumpSTART) + QR wristband + MCI mode + severity + transport request + ambulance dispatch queue (AmbulanceQueue DO)
  What to do / Must NOT do: `facilities` + capacity snapshots (manual + FHIR API import); ICU/emergency bed tracking; ambulance availability; medical supply inventory (Logistics reuse); stockpile expiry; triage zone map; triage patient form (START/SALT/JumpSTART via Form Builder); patient wristband QR IDs; mass casualty incident mode (bulk entry UI); patient severity; patient transport request; ambulance dispatch queue (`AmbulanceQueue` DO — Metis B1 distinct DO). Privacy = encrypted columns. Satisfies FEATURES.md:823-836.
  Parallelization: Wave 60 | Blocked by: T88 | Blocks: T117
  References: FEATURES.md:820. `src/db/schema/medical.ts`, `src/do/AmbulanceQueue.ts`.
  Acceptance: FHIR import populates facilities; triage form renders; QR wristband generates; MCI bulk entry; AmbulanceQueue DO prioritizes dispatch.
  QA: happy = facilities+FHIR+triage+QR+MCI+dispatch; failure = AmbulanceQueue unavailable → fallback queue. Evidence `.omo/evidence/task-116-disaster-cf-replatform.txt`.
  Commit: Y | feat(medical): facilities+capacity+FHIR+triage+QR wristband+MCI+AmbulanceQueue DO

- [ ] 117. Medical: medevac + field clinic + mobile unit + pharmacy/oxygen/blood (e-RaktKosh) + staff + disease/heat/smoke/waterborne monitoring + MHPSS + surge forecast + diversion alerts/board + FHIR adapter + advisory drafting + privacy reporting + incident summary
  What to do / Must NOT do: Medical evacuation planning; field clinic planning; mobile medical unit tracking; pharmacy availability; oxygen availability; blood availability (e-RaktKosh India); medical staff availability; disease outbreak monitoring (case counts, SEIR in P9); heat illness monitoring; smoke inhalation monitoring; waterborne disease risk monitoring; mental health/psychosocial support (MHPSS); medical surge forecast; hospital diversion alerts; hospital diversion status board; FHIR import adapter (HL7 FHIR); public health advisory drafting; privacy-safe medical reporting; medical incident summary. Satisfies FEATURES.md:837-855.
  Parallelization: Wave 60 | Blocked by: T116 | Blocks: T118
  References: FEATURES.md:820. `src/api/routes/medical.ts`.
  Acceptance: each tracking feature CRUD; surge forecast from casualty estimate × transport-time model; FHIR adapter round-trips; advisory draft + privacy report.
  QA: happy = medevac+units+supplies+monitoring+surge+diversion+FHIR+reports; failure = FHIR invalid → rejected. Evidence `.omo/evidence/task-117-disaster-cf-replatform.txt`.
  Commit: Y | feat(medical): medevac+units+supplies+monitoring+surge+diversion+FHIR+advisory+reports

- [ ] 118. Logistics: items/stock/movements ledger (idempotent) + barcode/QR scanning (html5-qrcode) + lot/batch/expiry + kit/bundle templates
  What to do / Must NOT do: `items(sku,name,category,unit)`, `stock(location_id,item_id,qty,lot,expiry)`, append-only `movements` ledger (idempotent; every qty change = a movement). Barcode/QR item scanning (`html5-qrcode`); lot/batch tracking; expiry tracking + alerts; kit/bundle templates (family kit = item BOM). Satisfies FEATURES.md:861-881.
  Parallelization: Wave 61 | Blocked by: T88 | Blocks: T119-T122
  References: FEATURES.md:858. `src/db/schema/logistics.ts`, `src/lib/inventory/movements.ts`.
  Acceptance: movement append is idempotent (replay no dup); QR scan checks out item; expiry alerts fire; kit template expands BOM.
  QA: happy = ledger+scan+expiry+kits; failure = duplicate movement → no-op. Evidence `.omo/evidence/task-118-disaster-cf-replatform.txt`.
  Commit: Y | feat(logistics): items/stock/movements ledger + QR scan + lot/expiry + kit templates

- [ ] 119. Logistics: resource request→approve→allocate→dispatch→deliver→return (Workflow state machine) + shortage/surplus alerts + burn-rate + demand forecast + staging + warehouse
  What to do / Must NOT do: Resource request workflow (ICS-213RR); approval; allocation; dispatch; delivery tracking; return tracking; shortage alerts; surplus alerts; burn-rate calculation (rolling avg of movements); demand forecast (burn × population served); staging area management; warehouse management. Long flows via Workflows. Satisfies FEATURES.md:882-893.
  Parallelization: Wave 61 | Blocked by: T118 | Blocks: T120
  References: FEATURES.md:858. `src/workflows/resourceRequest.ts`.
  Acceptance: request→approve→allocate→dispatch→deliver→return transitions; burn-rate + forecast computed; shortage/surplus alerts fire.
  QA: happy = state machine+alerts+burn+forecast; failure = invalid transition → rejected. Evidence `.omo/evidence/task-119-disaster-cf-replatform.txt`.
  Commit: Y | feat(logistics): resource request Workflow + alerts + burn-rate + forecast + staging + warehouse

- [ ] 120. Logistics: donations (intake/sort/match/distribute) + suppliers + procurement/PO + fleet dispatch + vehicle maintenance + driver duty-hours + fuel planning + cold chain + customs
  What to do / Must NOT do: Donation intake; donation sorting; donation matching; donation distribution; supplier registry; procurement request workflow; purchase order tracking; fleet dispatch; vehicle maintenance status; driver duty-hours tracking; fuel planning; cold chain tracking (temp log per movement); customs/clearance tracking (international aid). Satisfies FEATURES.md:894-906.
  Parallelization: Wave 62 | Blocked by: T118 | Blocks: T121
  References: FEATURES.md:858. `src/api/routes/logistics.ts`.
  Acceptance: donation lifecycle; PO tracking; fleet dispatch; driver duty-hours; cold chain temp logged; customs tracked.
  QA: happy = donations+suppliers+PO+fleet+duty+fuel+cold+customs; failure = cold chain breach → alert. Evidence `.omo/evidence/task-120-disaster-cf-replatform.txt`.
  Commit: Y | feat(logistics): donations + suppliers + PO + fleet + duty-hours + fuel + cold chain + customs

- [ ] 121. Logistics: supply route optimization + last-mile + air-drop + boat + drone + autonomous delivery + EDXL-RM export
  What to do / Must NOT do: Supply route optimization (reuse Evacuation routing); last-mile delivery planning; air-drop planning; boat delivery planning; drone delivery planning; autonomous delivery planning; EDXL-RM export. Satisfies FEATURES.md:907-913.
  Parallelization: Wave 62 | Blocked by: T112 | Blocks: T122
  References: FEATURES.md:858. `src/lib/routing/supplyRoute.ts`.
  Acceptance: supply route optimized; each delivery mode planned; EDXL-RM export validates.
  QA: happy = routes+5 delivery modes+EDXL-RM; failure = no road graph → degraded. Evidence `.omo/evidence/task-121-disaster-cf-replatform.txt`.
  Commit: Y | feat(logistics): supply route + last-mile + air-drop/boat/drone/autonomous + EDXL-RM

- [ ] 122. Logistics inventories (fuel/food/water/medicine/PPE/tents/blankets/rescue/comms-equip/drone/boat/heavy-machinery)
  What to do / Must NOT do: The remaining typed inventories beyond items T118: fuel, food, water, medicine, PPE, tents, blankets, rescue equipment, communication equipment, drone, boat, heavy machinery. All are `items.category` values reusing the T118 ledger. Satisfies FEATURES.md:862-877 (inventories already covered structurally by T118; this todo ensures category seeds + UI views).
  Parallelization: Wave 63 | Blocked by: T118 | Blocks: T123
  References: FEATURES.md:858,862-877. `src/lib/inventory/categories.ts`.
  Acceptance: each inventory category has a seeded catalog + a filtered UI view.
  QA: happy = 12 category views; failure = missing category → empty state. Evidence `.omo/evidence/task-122-disaster-cf-replatform.txt`.
  Commit: Y | feat(logistics): 12 typed inventory categories (fuel/food/water/medicine/PPE/tents/blankets/rescue/comms/drone/boat/machinery)

- [ ] 123. Infrastructure: assets + asset_dependencies DAG + cascade failure (BFS) + status tracking (power/cell/internet/radio/TV/road/bridge/rail/airport/port/water/sewage/gas/fuel/ATM/hospital/school/shelter/critical/dam/levee/embankment)
  What to do / Must NOT do: `assets(type,geo,status,restore_eta)` + `asset_dependencies(parent,child)` edge table → cascade = BFS over the DAG. Status updates from feeds (Ingestion) + field reports. Seeds from Overture/OSM. Status tracking for: power outage, cell, internet, radio, TV broadcast, road access, bridge, railway, airport, port, water supply, sewage, gas pipeline, fuel station, ATM/bank, hospital/school/shelter infrastructure, critical facility, dam, levee, embankment. Satisfies FEATURES.md:919-940.
  Parallelization: Wave 63 | Blocked by: T88 | Blocks: T124
  References: FEATURES.md:916. `src/db/schema/assets.ts`, `src/lib/infra/cascade.ts`.
  Acceptance: each asset type tracked; BFS cascade flags downstream failures when a parent fails; restore ETA tracked.
  QA: happy = assets+DAG+BFS+24 asset types; failure = cycle in DAG → detected + reported. Evidence `.omo/evidence/task-123-disaster-cf-replatform.txt`.
  Commit: Y | feat(infra): assets + dependency DAG + BFS cascade + 24 status types

- [ ] 124. Infrastructure: debris blockage layer + cell tower map (OpenCelliD) + power grid map + road closure map + restoration ETA + COW deployment + damage reports + repair tasks + priority scoring + risk forecast + public advisory
  What to do / Must NOT do: Debris blockage layer; cell tower map (OpenCelliD); power grid map; road closure map; utility restoration ETA; cell-on-wheels (COW) deployment tracking; infrastructure damage reports; infrastructure repair tasks; infrastructure priority scoring; critical infrastructure risk forecast; public infrastructure advisory. Satisfies FEATURES.md:941-953.
  Parallelization: Wave 64 | Blocked by: T123 | Blocks: T125
  References: FEATURES.md:916. `src/api/routes/infrastructure.ts`.
  Acceptance: debris/cell/power/road maps render; restoration ETA computed; COW tracked; repair tasks prioritized; advisory drafted.
  QA: happy = maps+ETA+COW+tasks+forecast+advisory; failure = no OSM/Overture seed → degraded. Evidence `.omo/evidence/task-124-disaster-cf-replatform.txt`.
  Commit: Y | feat(infra): debris/cell/power/road maps + restoration ETA + COW + repair tasks + forecast + advisory

- [ ] 125. P8 integration gate: evac recommend → road graph route → medical triage → logistics request → infra cascade
  What to do / Must NOT do: Integration test: hazard layer → evac recommend → route avoids blocked edges → medical triage + ambulance dispatch → logistics request Workflow → infra cascade BFS. P8 gate.
  Parallelization: Wave 65 (P8 gate) | Blocked by: T112-T124 | Blocks: P9+
  References: FEATURES.md:530-582,819-856,857-914,915-954. `platform/worker/test/p8_integration.test.ts`.
  Acceptance: test green; covers routing+triage+Workflow state machine+BFS cascade.
  QA: happy = full P8 loop; failure = cascade missed → fails. Evidence `.omo/evidence/task-125-disaster-cf-replatform.txt`.
  Commit: Y | test(evac): P8 integration gate (evac→route→triage→logistics→cascade)

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- PHASE P9: PREDICTION/SIMULATION + DRONE + DAMAGE ASSESSMENT — FEATURES.md:991-1034, 1160-1191, 1122-1159 -->
<!-- Build blocks: :992 (heavy sims in CF Containers or external runner fed by Queue; outputs COG/GeoJSON to R2; fire CA/flood bathtub/plume Gaussian/evac time-step/SEIR; scenarios+results), :1161 (missions/flights/media→R2; WebODM orthomosaic→COG; vision-model detection Queue; waypoint search patterns; live drone DO), :1123 (Form Builder per asset class; FEMA PDA severity; EXIF verify; react-compare-slider; unit-cost loss; AI vision) -->
<!-- Metis B9 decision: heavy compute = external job-runner adapter fed by Queues (default); Containers binding OPTIONAL — adapters swap. -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 126. Prediction infra: scenarios + scenario_results + heavy-compute adapter (Containers/external runner) fed by Queue + COG/GeoJSON output to R2 + render via geotiff.js/PMTiles
  What to do / Must NOT do: `scenarios(params json)` + `scenario_results(snapshot)`. Heavy sims run in Cloudflare Containers OR external job runner fed by a Queue; outputs = raster COG / GeoJSON to R2, rendered via geotiff.js or converted to PMTiles. (Metis B9: external-runner adapter default; Containers binding optional, adapters swap.) Satisfies foundation for FEATURES.md:992,1009-1029.
  Parallelization: Wave 66 | Blocked by: T88 | Blocks: T127-T130
  References: FEATURES.md:992. `src/db/schema/scenarios.ts`, `src/queues/simConsumer.ts`, `src/lib/sim/runner.ts`.
  Acceptance: submit scenario → Queue → runner produces COG/GeoJSON to R2 → render layer; idempotent (same params = cached result).
  QA: happy = scenario→queue→R2→render; failure = runner down → DLQ + alert. Evidence `.omo/evidence/task-126-disaster-cf-replatform.txt`.
  Commit: Y | feat(predsim): scenarios + heavy-compute adapter + Queue + COG/GeoJSON output + render

- [ ] 127. Prediction models: fire spread (cellular automata) + flood (DEM bathtub/HAND) + smoke + chemical plume (Gaussian) + dam-break + evac (time-stepped) + shelter/resource/hospital demand + outbreak (SEIR) + road congestion (BPR) + power/comms outage cascade
  What to do / Must NOT do: Fire spread (cellular automata over fuel/slope/wind grid; slope from Copernicus GLO-30 DEM; Rothermel keyword for serious); flood spread (bathtub fill of DEM vs water level; HAND keyword); smoke spread; chemical plume (Gaussian w/ Open-Meteo wind; ALOHA reference); dam-break; evacuation (time-stepped demand assignment on road graph); shelter demand; resource demand; hospital surge; disease outbreak (SEIR); road congestion (BPR); power outage cascade (dependency DAG BFS); communications outage. Satisfies FEATURES.md:995-1008.
  Parallelization: Wave 66 | Blocked by: T126 | Blocks: T128
  References: FEATURES.md:992. `src/lib/sim/models/*.ts`.
  Acceptance: each model produces a scenario_result snapshot; fire/flood/plume render on map (T45 plume overlay); SEIR curve sensible; BPR congestion matches T112.
  QA: happy = 13 models; failure = missing DEM → flood degrades. Evidence `.omo/evidence/task-127-disaster-cf-replatform.txt`.
  Commit: Y | feat(predsim): 13 simulation models (fire/flood/smoke/plume/dam-break/evac/demands×3/SEIR/congestion/cascades×2)

- [ ] 128. Prediction: multi-scenario (best/expected/worst) + confidence bands + timeline/escalation/de-escalation forecast + future recs (evac/responder/shelter/resource staging) + replay + comparison + shareable snapshots + confidence + manual params + AI explanation + what-if board + red-team + black-swan
  What to do / Must NOT do: Multi-scenario planning (best/expected/worst-case); confidence bands on forecasts; timeline forecast; escalation forecast; de-escalation forecast; future evacuation/responder activity/shelter opening/resource staging recommendation; simulation replay; simulation comparison; shareable scenario snapshots; simulation confidence score; manual simulation parameters; AI-generated scenario explanation; what-if planning board; red-team scenario mode; black-swan scenario mode. Satisfies FEATURES.md:1009-1029.
  Parallelization: Wave 67 | Blocked by: T127 | Blocks: T129
  References: FEATURES.md:992. `src/lib/sim/compare.ts`.
  Acceptance: 3 scenarios compare; confidence bands render; replay scrubs; AI explanation cites scenario_result rows; what-if board swaps params.
  QA: happy = compare+replay+AI+what-if; failure = AI explanation ungrounded → rejected. Evidence `.omo/evidence/task-128-disaster-cf-replatform.txt`.
  Commit: Y | feat(predsim): multi-scenario + confidence + forecasts + future recs + replay/compare + AI explanation + what-if/red-team/black-swan

- [ ] 129. Drone: missions + survey zones + flight logs + image/thermal/video upload + map overlay (COG on R2) + orthomosaic (WebODM) + live location + battery + operator + no-fly zone + evidence tagging
  What to do / Must NOT do: `missions`, `flights`, media → R2. Orthomosaic = WebODM (external/container) → COG → R2 → map overlay (geotiff.js or tile to PMTiles). Live drone position = same DO pipeline as responders (IncidentRoom). Battery tracking; operator assignment; no-fly zone warnings; evidence tagging. Satisfies FEATURES.md:1164-1176.
  Parallelization: Wave 67 | Blocked by: T88 | Blocks: T130
  References: FEATURES.md:1161. `src/db/schema/drone.ts`, `src/lib/drone/orthomosaic.ts`.
  Acceptance: mission/flight CRUD; image/thermal/video upload to R2; COG overlay renders; orthomosaic processed; live position broadcasts; no-fly warning fires.
  QA: happy = missions+overlay+orthomosaic+live+nofly; failure = WebODM down → COG not produced + alert. Evidence `.omo/evidence/task-129-disaster-cf-replatform.txt`.
  Commit: Y | feat(drone): missions + flights + media + COG overlay + orthomosaic (WebODM) + live + battery + no-fly

- [ ] 130. Drone: search patterns (expanding square/parallel track) + waypoint export (KML/GeoJSON) + damage detection (vision queue) + trapped-person flagging + flood/fire/landslide mapping + satellite import + change detection + confidence + thermal survivor (P14 hint) + auto safe landing (P14 hint)
  What to do / Must NOT do: Search pattern planning (expanding square / parallel track); search pattern waypoint export (KML/GeoJSON); drone damage detection workflow (vision model queue → flagged-points layer, human-confirm); trapped-person flagging; flood extent mapping; fire edge mapping; landslide mapping; satellite imagery import (Sentinel Hub / Copernicus); satellite change detection; remote sensing confidence score. (Thermal survivor + auto safe landing = P14 composition, hinted here.) Satisfies FEATURES.md:1177-1186.
  Parallelization: Wave 68 | Blocked by: T129 | Blocks: T131
  References: FEATURES.md:1161. `src/lib/drone/{patterns,detection}.ts`.
  Acceptance: search patterns generate waypoints; KML/GeoJSON export; vision detection flags points (draft, human-confirm); change detection highlights diffs.
  QA: happy = patterns+detection+mapping+satellite+change; failure = vision model down → queue + retry. Evidence `.omo/evidence/task-130-disaster-cf-replatform.txt`.
  Commit: Y | feat(drone): search patterns + waypoint export + vision detection + mapping + satellite + change detection

- [ ] 131. Damage: typed Form Builder forms per asset class (building/road/bridge/utility/crop/industrial/shelter/hospital/school) + FEMA PDA severity + photo/video + location tagging + EXIF geotag verification + verification workflow
  What to do / Must NOT do: Typed Form Builder forms per asset class (building, road, bridge, utility, crop, industrial, shelter, hospital, school). Severity = FEMA PDA categories (affected/minor/major/destroyed). Photo/video upload; damage location tagging; geotag verification (EXIF GPS vs tagged location match); damage verification workflow. Satisfies FEATURES.md:1126-1141.
  Parallelization: Wave 68 | Blocked by: T88 | Blocks: T132
  References: FEATURES.md:1123. `src/db/schema/damage.ts`, `src/lib/forms/damageForms.ts`.
  Acceptance: each asset-class form renders + submits; FEMA PDA severity set; EXIF vs tag distance verified; verification workflow moves status.
  QA: happy = 9 forms+severity+EXIF+verify; failure = EXIF mismatch → flagged. Evidence `.omo/evidence/task-131-disaster-cf-replatform.txt`.
  Commit: Y | feat(damage): 9 asset-class Form Builder forms + FEMA PDA severity + EXIF verify + workflow

- [ ] 132. Damage: map + checklist + rapid/detailed needs assessment + loss estimate (unit-cost library) + repair cost library + repair priority + recovery planning (link) + insurance/government/donor report exports
  What to do / Must NOT do: Damage assessment map; checklist; rapid needs assessment; detailed needs assessment; loss estimate (unit-cost library × quantities); repair cost library (configurable unit costs); repair priority scoring; recovery planning (link to P12 Recovery — trigger here); insurance-safe export; insurance claim packet export; government report export; donor report export. Satisfies FEATURES.md:1142-1153.
  Parallelization: Wave 69 | Blocked by: T131 | Blocks: T133
  References: FEATURES.md:1123. `src/lib/damage/loss.ts`.
  Acceptance: map renders damage; rapid/detailed assessments produce; loss estimate from unit-cost library; each export format produces.
  QA: happy = map+assessments+loss+exports; failure = missing unit-cost → default + warn. Evidence `.omo/evidence/task-132-disaster-cf-replatform.txt`.
  Commit: Y | feat(damage): map + assessments + loss estimate + repair library + exports (insurance/govt/donor)

- [ ] 133. Damage: before-after image comparison (react-compare-slider) + drone/satellite damage survey import + AI damage description from images (vision) + AI damage report summary
  What to do / Must NOT do: Before-after image comparison (`react-compare-slider`); drone damage survey import; satellite damage survey import (Copernicus EMS grading maps); AI damage description from images (vision model); AI damage report summary. All AI outputs draft + human-verified. Satisfies FEATURES.md:1154-1159.
  Parallelization: Wave 69 | Blocked by: T131 | Blocks: T134
  References: FEATURES.md:1123. `src/lib/damage/aiVision.ts`.
  Acceptance: before-after slider compares; drone/satellite surveys import; AI vision describes damage (draft); AI summary generates.
  QA: happy = compare+imports+AI; failure = vision down → fallback draft. Evidence `.omo/evidence/task-133-disaster-cf-replatform.txt`.
  Commit: Y | feat(damage): before-after slider + survey imports + AI vision description + AI summary

- [ ] 134. P9 integration gate: scenario sim → COG on map → drone survey → AI damage description
  What to do / Must NOT do: Integration test: run flood sim → COG renders on map → drone survey imports → AI damage description. P9 gate.
  Parallelization: Wave 70 (P9 gate) | Blocked by: T126-T133 | Blocks: P10+
  References: FEATURES.md:991-1034,1122-1191. `platform/worker/test/p9_integration.test.ts`.
  Acceptance: test green; covers sim→R2→render + vision queue + idempotent detection.
  QA: happy = full P9 loop; failure = runner down → DLQ. Evidence `.omo/evidence/task-134-disaster-cf-replatform.txt`.
  Commit: Y | test(predsim): P9 integration gate (sim→COG→drone→AI damage)

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- PHASE P10: ANALYTICS + DECISION SUPPORT + SEARCH/KB — FEATURES.md:1273-1312, 1313-1352, 1352-1387 -->
<!-- Build blocks: :1274 (Analytics Engine writes; nightly Cron→D1 rollups; ECharts; custom=saved JSON layouts; CSV export), :1314 (deterministic scoring + AI memo w/ cited row ids; decisions append-only hash-chained; sign-off role-gated; alternatives=scenario snapshots), :1353 (D1 FTS5 per entity + unified /search w/ permission filters; Vectorize semantic; RAG citations; versioned MD KB) -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 135. Analytics: Analytics Engine writes (route/status/ms + org/incident) + nightly Cron rollups to D1 + ECharts dashboards
  What to do / Must NOT do: Hot path = write events to Workers Analytics Engine (blobs + doubles). Dashboards: nightly Cron aggregates into D1 rollup tables; charts = ECharts. Rollups: incident/response/population/evac/shelter/resource/medical/volunteer/comms/infra/weather/damage/task/SLA/team-performance/responder-utilization/help-request-funnel/bottleneck/trend/geographic(H3)/time-series/heatmap/comparison/cross-incident/scenario/data-quality/source-reliability/AI-usage/API-usage/cost. Satisfies FEATURES.md:1277-1306.
  Parallelization: Wave 71 | Blocked by: T88 | Blocks: T136
  References: FEATURES.md:1274. `src/db/schema/analytics_rollups.ts`, `src/cron/analyticsRollup.ts`, `platform/web/src/components/analytics/*.tsx`.
  Acceptance: Analytics Engine receives writes; nightly rollup populates D1; each of ~30 analytics dashboards renders ECharts.
  QA: happy = writes+rollup+30 dashboards; failure = rollup cron failure → stale + alert. Evidence `.omo/evidence/task-135-disaster-cf-replatform.txt`.
  Commit: Y | feat(analytics): Analytics Engine writes + nightly Cron rollups + 30 ECharts dashboards

- [ ] 136. Analytics: custom dashboards (saved JSON layouts) + custom metrics + saved views + scheduled analytics emails + export
  What to do / Must NOT do: Custom dashboards = saved JSON layouts of widget queries; custom metrics; saved views; scheduled analytics emails (Cron); export analytics data (CSV from rollups). Satisfies FEATURES.md:1307-1311.
  Parallelization: Wave 71 | Blocked by: T135 | Blocks: T137
  References: FEATURES.md:1274. `src/api/routes/analytics.ts`.
  Acceptance: build a custom dashboard from widgets → saves JSON → renders; scheduled email sends CSV; export produces CSV.
  QA: happy = custom+metrics+views+email+export; failure = invalid widget query → error. Evidence `.omo/evidence/task-136-disaster-cf-replatform.txt`.
  Commit: Y | feat(analytics): custom dashboards + custom metrics + saved views + scheduled emails + CSV export

- [ ] 137. Decision Support: recommendation engines (priority/evac/shelter/resource/responder/route/medical/infra/alert/missing-data) + decision memo generator + approval + decision log (hash-chained)
  What to do / Must NOT do: Recommendation engines = deterministic scoring functions over real data + AI memo on top (memo must cite row IDs; citations validated to exist). `decisions` = append-only, hash-chained (Conventions). Engines: priority, evacuation, shelter, resource, responder, route, medical priority, infrastructure priority, public alert, missing-data. Decision memo generator; decision approval workflow; decision log (append-only hash chain). Satisfies FEATURES.md:1317-1329.
  Parallelization: Wave 72 | Blocked by: T111 | Blocks: T138
  References: FEATURES.md:1314. `src/lib/recommend/decisionEngines.ts`, `src/db/schema/decisions.ts`.
  Acceptance: each engine produces a scored recommendation + AI memo with valid citations; decision log hash-chain verifies; approval moves status.
  QA: happy = 10 engines+memo+log; failure = invalid citation → memo rejected. Evidence `.omo/evidence/task-137-disaster-cf-replatform.txt`.
  Commit: Y | feat(decision): 10 recommendation engines + AI memo (cited) + approval + hash-chained decision log

- [ ] 138. Decision Support: rationale/source links/confidence/risk/impact/alternatives/consequence preview (scenario link)/tradeoff matrix/premortem/dissent/rollback/sign-off/legal/public-comms/ethics flags + AI-assisted draft + human-only final approval
  What to do / Must NOT do: Decision rationale; source links; confidence score; risk score; impact estimate; alternatives; consequence preview (scenario snapshot link from Prediction); tradeoff matrix builder; premortem prompt; dissent/objection log; rollback notes; commander sign-off; legal review flag; public communication flag; ethics review flag; AI-assisted decision draft; human-only final approval. Satisfies FEATURES.md:1330-1346.
  Parallelization: Wave 72 | Blocked by: T137 | Blocks: T139
  References: FEATURES.md:1314. `src/api/routes/decisions.ts`.
  Acceptance: each decision field populated; consequence preview links a scenario snapshot; tradeoff matrix builds; flags set; AI draft → human-only final approval (no auto-approve).
  QA: happy = fields+consequence+matrix+flags+approval; failure = auto-approve attempt → blocked. Evidence `.omo/evidence/task-138-disaster-cf-replatform.txt`.
  Commit: Y | feat(decision): rationale/consequence/tradeoff/premortem/dissent/flags + AI draft + human-only approval

- [ ] 139. Search: D1 FTS5 per entity + unified /search w/ permission filters + saved searches + search filters + permissions
  What to do / Must NOT do: D1 FTS5 virtual tables per entity + one unified `/search` endpoint with permission filters. Saved searches; search filters; search permissions. (Metis C2/D6: validate FTS5 enabled in D1; use raw-SQL migrations for FTS5 virtual tables since Drizzle lacks FTS support.) Satisfies FEATURES.md:1356-1369.
  Parallelization: Wave 73 | Blocked by: T99 | Blocks: T140
  References: FEATURES.md:1353. `src/db/migrations/fts5.sql` (raw), `src/api/routes/search.ts`.
  Acceptance: FTS5 virtual table creation migration applies; unified search returns ranked results across entities filtered by permissions; saved searches persist.
  QA: happy = FTS5+search+filters+saved; failure = FTS5 unsupported → documented blocker + fallback LIKE search. Evidence `.omo/evidence/task-139-disaster-cf-replatform.txt`.
  Commit: Y | feat(search): D1 FTS5 per entity + unified /search + permission filters + saved searches

- [ ] 140. Search: semantic search (Vectorize) + attachment search (OCR text indexed) + person/map-object/shelter/resource/task/report/document search
  What to do / Must NOT do: Semantic search = Vectorize w/ configured embeddings; attachment search (OCR'd attachment text indexed too). Entity-specific search: incident, map object, person, shelter, resource, task, report, document, attachment. Satisfies FEATURES.md:1357-1365,1366.
  Parallelization: Wave 73 | Blocked by: T139 | Blocks: T141
  References: FEATURES.md:1353. `src/lib/search/semantic.ts`.
  Acceptance: semantic search returns near-meaning matches via Vectorize; OCR text searchable; each entity type searchable with permission filter.
  QA: happy = semantic+OCR+9 entity searches; failure = no embeddings → fallback FTS5. Evidence `.omo/evidence/task-140-disaster-cf-replatform.txt`.
  Commit: Y | feat(search): semantic (Vectorize) + attachment/OCR + 9 entity searches

- [ ] 141. Knowledge Base: versioned Markdown docs + incident/SOP KB + SOP review-expiry reminders (cron) + playbook/laws/contacts/operations/evac/triage/logistics/comms guides + AI KB assistant (RAG, citations required) + AI source-grounded answers + summarization + checklist extraction + glossary
  What to do / Must NOT do: KB = versioned Markdown docs. Incident KB; SOP KB; KB document versioning; SOP review-expiry reminders (cron). Libraries: disaster playbook, local laws, agency contacts, shelter operations guide, evacuation guide, medical triage guide, logistics guide, communications guide. AI KB assistant (RAG, citations required); AI source-grounded answers; AI document summarization; AI checklist extraction; AI glossary generation. Satisfies FEATURES.md:1370-1386.
  Parallelization: Wave 74 | Blocked by: T140 | Blocks: T142
  References: FEATURES.md:1353. `src/db/schema/kb.ts`, `src/lib/ai/rag.ts`.
  Acceptance: KB docs versioned; SOP expiry cron fires; RAG assistant answers with mandatory citations (validated to exist); summarization/checklist/glossary produce.
  QA: happy = KB+libraries+RAG+citations; failure = RAG without citations → rejected. Evidence `.omo/evidence/task-141-disaster-cf-replatform.txt`.
  Commit: Y | feat(kb): versioned MD docs + libraries + RAG assistant (cited) + summarization/checklist/glossary

- [ ] 142. P10 integration gate: analytics rollup → decision memo (cited) → semantic search → RAG KB answer
  What to do / Must NOT do: Integration test: nightly rollup → decision memo with cited rows → semantic search hits → RAG KB answer with citations. P10 gate.
  Parallelization: Wave 75 (P10 gate) | Blocked by: T135-T141 | Blocks: P11+
  References: FEATURES.md:1273-1387. `platform/worker/test/p10_integration.test.ts`.
  Acceptance: test green; covers citation validation + FTS5 + Vectorize + RAG.
  QA: happy = full P10 loop; failure = uncited memo → rejected. Evidence `.omo/evidence/task-142-disaster-cf-replatform.txt`.
  Commit: Y | test(analytics): P10 integration gate (rollup→decision→search→RAG)

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- PHASE P11: SECURITY + COMPLIANCE + ADMIN + DEVELOPER PLATFORM + OFFLINE — FEATURES.md:1444-1498, 1499-1535, 1536-1579, 1580-1624, 1626-1662 -->
<!-- Build blocks: :1445 (Turnstile+httpOnly sessions+devices+WebAuthn+policy+field serializers+PII mask+AES-GCM+hash chain+rate DO+break-glass), :1500 (retention_policies+cron purge+legal_holds+consents+DSR Workflow+transparency+evidence chain-of-custody), :1537 (KV/DO limits+grace mode+feature flags+templates+form builder+monitors+impersonation), :1581 (chanfana OpenAPI+sk_ keys+service accounts+webhook subs+HMAC+replay+SSE event stream+faker generators+openapi-typescript SDK), :1627 (Workbox PWA+Dexie outbox+PMTiles OPFS+incident pack+one-file HTML+QR packets+degraded modes+SMS/email fallback+DB restore) -->
<!-- NOTE: Many P0 items already satisfy security checkboxes (T5 audit, T8 auth/passkeys/sessions/devices/lockout, T9 RBAC, T6 serializer, T14 rate limit, T19 key vaults). P11 = consolidation + remaining items. -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 143. Security: field-level/incident/map/report permissions + PII detection/masking/redaction + location privacy (coordinate fuzzing) + medical/missing-person privacy
  What to do / Must NOT do: Field-level permissions (serializer whitelists — extend T6/T9); attribute-based permissions; incident-level/map-layer/report permissions; PII detection (regex + NER prompt) → mask map; PII masking; PII redaction; location privacy protection (coordinate fuzzing on public); medical privacy; missing person privacy. Satisfies FEATURES.md:1455-1468.
  Parallelization: Wave 76 | Blocked by: T142 | Blocks: T144
  References: FEATURES.md:1445. `src/lib/security/pii.ts`, `src/lib/serialize.ts`.
  Acceptance: PII detected + masked before send/AI; coordinate fuzzing on public route (assert precision reduced); medical/missing fields encrypted (T71) + serializer-redacted.
  QA: happy = PII+mask+fuzz+privacy; failure = PII leak → test fails. Evidence `.omo/evidence/task-143-disaster-cf-replatform.txt`.
  Commit: Y | feat(security): field/ABAC permissions + PII detect/mask/redact + location fuzzing + medical/missing privacy

- [ ] 144. Security: audit logs (admin/API/AI/data-export) + export watermarking + webhook signing (HMAC) + bot protection (Turnstile) + IP allowlist + security headers/CSP + signed URL expiry + break-glass + security incident mode
  What to do / Must NOT do: Admin action log; API access log; AI request audit log; data export audit log; export watermarking (user+ts stamp on PDFs); webhook signing (HMAC header); abuse prevention; bot protection (Turnstile); public form spam protection; IP allowlist; security headers/CSP; signed URL expiry policy; break-glass admin access (time-boxed + alert + log); security incident mode. Also enumerates (functionally built in T5/T18/T137): Audit logs (L1469), Immutable decision log — hash chain (L1470). Satisfies FEATURES.md:1469,1470,1471-1492.
  Parallelization: Wave 76 | Blocked by: T143 | Blocks: T145
  References: FEATURES.md:1445. `src/middleware/{csp,ipAllowlist,breakglass}.ts`.
  Acceptance: each audit log appends to hash chain (T5); export PDF watermarked; webhook HMAC verified; Turnstile on public forms; CSP headers set; break-glass time-boxed + loud alert + immutable log.
  QA: happy = logs+watermark+HMAC+Turnstile+CSP+break-glass; failure = expired signed URL → 403. Evidence `.omo/evidence/task-144-disaster-cf-replatform.txt`.
  Commit: Y | feat(security): audit logs + watermark + HMAC + Turnstile + IP allowlist + CSP + signed URL + break-glass + incident mode

- [ ] 145. Security: data retention + deletion + legal hold + backup restore + disaster recovery plan
  What to do / Must NOT do: Data retention policy; data deletion workflow; legal hold (blocks retention purge); backup restore; disaster recovery plan. (Reuses Compliance retention_policies T147.) Satisfies FEATURES.md:1493-1497.
  Parallelization: Wave 77 | Blocked by: T144 | Blocks: T146
  References: FEATURES.md:1445. `src/lib/security/retention.ts`.
  Acceptance: retention cron purges aged data; legal hold blocks purge by entity; backup restore tested; DR plan documented + tested script.
  QA: happy = retention+deletion+hold+backup+DR; failure = legal hold blocks purge. Evidence `.omo/evidence/task-145-disaster-cf-replatform.txt`.
  Commit: Y | feat(security): data retention + deletion + legal hold + backup restore + DR plan

- [ ] 146. Compliance: org policy + data classification + sensitive handling + consent tracking + data processing register + subprocessor list + DPDP readiness + inter-org sharing tracker + transparency page
  What to do / Must NOT do: Organization policy settings; data classification (public/internal/sensitive enum); sensitive data handling; consent tracking (`consents` table, purpose-scoped); data processing register (purposes × data classes); subprocessor list page (CF, AI provider, SMS provider); DPDP Act readiness notes (India; GDPR analog); inter-org data sharing agreement tracker (MOU records w/ scope+expiry); public transparency page. Satisfies FEATURES.md:1503-1514,1531-1532.
  Parallelization: Wave 77 | Blocked by: T143 | Blocks: T147
  References: FEATURES.md:1500. `src/db/schema/compliance.ts`, `src/api/routes/transparency.ts`.
  Acceptance: classification enforced; consent tracked (grant/revoke); processing register populated; transparency page public; MOU tracker with scope+expiry.
  QA: happy = classification+consent+register+transparency+MOU; failure = revoked consent → data use blocked. Evidence `.omo/evidence/task-146-disaster-cf-replatform.txt`.
  Commit: Y | feat(compliance): classification + consent + processing register + DPDP + MOU tracker + transparency page

- [ ] 147. Compliance: retention policies + legal holds + DSR export/delete Workflow + public/report/alert/decision approval + audit export + incident closure/AAR review + SOP checklist + accessibility/localization compliance + govt/NGO/donor formats + privacy impact + AI policy/risk + model disclosure + human-in-loop + evidence chain-of-custody + tamper-evident logs
  What to do / Must NOT do: Data retention rules (per data_class TTL + cron purge); legal holds (blocks purge by entity ref); DSR export (Workflow: gather rows across tables by person ref → JSON/PDF); DSR deletion (anonymize-in-place, keep aggregates); public data approval; report approval; alert approval; decision approval; audit export; incident closure review; after-action review; SOP compliance checklist; accessibility compliance (see A11y T218); localization compliance; government/NGO/donor report format support; privacy impact report; AI usage policy; AI risk disclosure; human-in-the-loop enforcement (review_status gate, no auto-publish); model provider disclosure; evidence chain-of-custody (hash-chained `evidence_events` per attachment); tamper-evident logs (hash chain + periodic anchor export). Satisfies FEATURES.md:1504-1534.
  Parallelization: Wave 78 | Blocked by: T146 | Blocks: T148
  References: FEATURES.md:1500. `src/workflows/dsr.ts`, `src/lib/compliance/custody.ts`.
  Acceptance: retention cron purges; legal hold blocks; DSR export gathers cross-table; DSR delete anonymizes; approvals reuse generic workflow; chain-of-custody hash verifies; tamper-evident anchor export works.
  QA: happy = retention+DSR+approvals+custody+anchors; failure = DSR export incomplete → fails. Evidence `.omo/evidence/task-147-disaster-cf-replatform.txt`.
  Commit: Y | feat(compliance): retention + legal holds + DSR Workflow + approvals + custody + tamper-evident anchors + AI policy

- [ ] 148. Admin: org/workspace/member management + invites + usage/storage/API/AI/incident/export limits (KV/DO counters) + grace mode + feature flags (D1+KV) + maintenance mode + announcements
  What to do / Must NOT do: Organization creation; invitation; member management; workspace management; usage limits (KV/DO counters in middleware); storage limits (sum R2 object sizes per org); API limits; AI request limits (token counter per org); incident limits; export limits; grace mode during active incidents (soft-limit, never block ops); feature flags (D1 + KV cache 60s, scope global/org/incident); maintenance mode; system announcements (banner table + dismiss state); admin notifications; global configuration; tenant configuration. Satisfies FEATURES.md:1540-1556.
  Parallelization: Wave 78 | Blocked by: T142 | Blocks: T149
  References: FEATURES.md:1537. `src/db/schema/{limits,flags,announcements}.ts`, `src/middleware/limits.ts`.
  Acceptance: each limit counter checks in middleware; over-limit → 429 + banner (never blocks active incident ops in grace); feature flag toggles routes+UI; maintenance mode shows banner.
  QA: happy = limits+grace+flags+maintenance+announcements; failure = over-limit during active incident → grace (not blocked). Evidence `.omo/evidence/task-148-disaster-cf-replatform.txt`.
  Commit: Y | feat(admin): org/member mgmt + limits + grace mode + feature flags + maintenance + announcements

- [ ] 149. Admin: tenant impersonation (consent+audit+banner) + exercise tenant toggle + templates (incident/disaster-type/report/alert/task/map-layer) + form builder (JSON-Schema) + custom fields/statuses/tags/workflows + audit viewer + error logs + health checks + job/queue/webhook/AI/data-sync/cron monitors
  What to do / Must NOT do: Tenant impersonation with consent log (admin assumes org-scoped session, consent + audit row, banner shown); exercise tenant toggle (marks org as drill/sandbox); incident templates; disaster type templates; report templates; alert templates; task templates; map layer templates; form builder (JSON-Schema + react-jsonschema-form — ONE engine per Conventions); custom fields; custom statuses; custom tags; custom workflows (state machine JSON per entity kind); audit viewer; error logs; health checks (/healthz deep-check D1/R2/Queues); background job monitor (job_runs table UI); queue monitor (depth + DLQ count via GraphQL API); webhook monitor (webhook_deliveries status board); AI monitor (latency/error/token charts); data sync monitor (feed last_success_at staleness); cron job registry UI (list schedules + last run + force-run). Satisfies FEATURES.md:1557-1578,1565-1569.
  Parallelization: Wave 79 | Blocked by: T148 | Blocks: T150
  References: FEATURES.md:1537. `src/lib/forms/builder.ts`, `src/api/routes/admin/*.ts`.
  Acceptance: impersonation shows banner + audit; exercise toggle watermarks; each template instantiates (deep-copy); Form Builder renders JSON-Schema; custom fields/statuses/tags/workflows persist; monitors render.
  QA: happy = impersonation+templates+formbuilder+custom+monitors; failure = impersonation without consent → blocked. Evidence `.omo/evidence/task-149-disaster-cf-replatform.txt`.
  Commit: Y (split per mechanism family, per orphan guard) | feat(admin): impersonation + exercise toggle; feat(admin): 7 templates (incident/disaster-type/report/alert/task/map-layer); feat(admin): Form Builder + custom fields/statuses/tags/workflows; feat(admin): monitors (audit/errors/health/job/queue/webhook/AI/data-sync/cron)

- [ ] 150. Developer Platform: OpenAPI spec (chanfana) + docs (Scalar) + playground + API key creation/rotation/scopes + service accounts
  What to do / Must NOT do: Public/Admin/Incident/Map/Shelter/Evacuation/Resource/Task/Report/AI/Webhook APIs (all via chanfana → OpenAPI auto-spec at `/openapi.json`); docs UI (Scalar/Swagger embed); API playground; API key creation (`sk_live_` prefix + sha256 hash stored, scopes array, last_used_at); API key rotation; scoped API keys (scopes[] checked in middleware); service accounts (keys not bound to a human user). Satisfies FEATURES.md:1584-1601.
  Parallelization: Wave 79 | Blocked by: T142 | Blocks: T151
  References: FEATURES.md:1581. `src/api/openapi.ts`, `src/api/routes/devplatform.ts`.
  Acceptance: `/openapi.json` lists all route groups; Scalar docs load; playground executes; key create returns full key once (hash+prefix stored); scopes enforced; service accounts work.
  QA: happy = OpenAPI+docs+playground+keys+scopes+service-accounts; failure = over-scope key → 403. Evidence `.omo/evidence/task-150-disaster-cf-replatform.txt`.
  Commit: Y | feat(devplatform): OpenAPI (chanfana) + Scalar docs + playground + scoped API keys + service accounts

- [ ] 151. Developer Platform: webhook subscriptions + retry logs + replay UI + HMAC signing secret + event stream API (SSE from IncidentRoom DO) + import/export/bulk (NDJSON) APIs
  What to do / Must NOT do: Webhook subscriptions (`webhook_subscriptions`: url, events[], secret) + Queue-driven delivery with HMAC `X-Signature`, exponential retries, `webhook_deliveries` log + replay button; webhook signing secret (HMAC X-Signature); event stream API (SSE endpoint backed by IncidentRoom DO broadcast); import API; export API; bulk operations API (NDJSON batch endpoints). Satisfies FEATURES.md:1602-1609.
  Parallelization: Wave 80 | Blocked by: T150 | Blocks: T152
  References: FEATURES.md:1581. `src/queues/webhookDeliveryConsumer.ts` (uses `webhookDeliveryQ`), `src/api/routes/sse.ts`.
  Acceptance: webhook subscription delivers with HMAC + retries + `webhook_deliveries` log; replay re-enqueues stored payload; SSE streams IncidentRoom events; bulk NDJSON import/export works.
  QA: happy = webhooks+replay+SSE+bulk; failure = delivery fail → DLQ + retry. Evidence `.omo/evidence/task-151-disaster-cf-replatform.txt`.
  Commit: Y | feat(devplatform): webhook subscriptions + delivery (HMAC/retry/replay) + SSE event stream + import/export/bulk NDJSON

- [ ] 152. Developer Platform: SDK-ready schema (openapi-typescript) + CLI-ready + Bruno/Postman collection + sandbox env + seed data (faker-js) + generators (incident/mock-disaster/population/shelter/resource/map-layer/feed-replayer) + AI prompt test harness + rate-limit dashboard + changelog
  What to do / Must NOT do: SDK-ready schema (`openapi-typescript` gen from spec); CLI-ready API; Bruno/Postman collection export (from OpenAPI spec); sandbox environment (wrangler env w/ synthetic data); local development seed data (faker-js seed script); test incident generator; mock disaster data generator; synthetic population generator (random H3 weights); synthetic shelter/resource/map-layer generators; synthetic feed replayer (replay stored GeoJSON ticks); AI prompt test harness; API rate limit dashboard; API changelog. Satisfies FEATURES.md:1610-1624.
  Parallelization: Wave 80 | Blocked by: T150 | Blocks: T153
  References: FEATURES.md:1581. `platform/packages/sdk/`, `src/seed/generators/*.ts`.
  Acceptance: openapi-typescript generates SDK from spec; Bruno collection exports; sandbox env seeds synthetic data; each generator produces realistic data via normal API (dogfood); AI prompt harness runs golden set.
  QA: happy = SDK+collection+sandbox+generators+harness; failure = spec drift → SDK regen fails. Evidence `.omo/evidence/task-152-disaster-cf-replatform.txt`.
  Commit: Y | feat(devplatform): SDK gen + Bruno collection + sandbox + faker seed + 6 generators + AI harness + rate dashboard + changelog

- [ ] 153. Offline: full PWA (Workbox precache + runtime cache) + Dexie outbox + PMTiles region packs (OPFS) + region pack manager + offline shelter/evac-route/task lists + offline forms + report drafts + attachment queue + sync conflict (LWW + per-field merge UI) + low-bandwidth delta sync (gzip)
  What to do / Must NOT do: Offline public pages (Workbox precache); offline field app mode; offline map tiles (PMTiles packs in OPFS, MapLibre reads via SW range handler); offline region pack manager (download/update/delete per area); offline shelter list; offline evacuation routes; offline task list; offline forms (JSON-Schema renders offline); offline report drafts; offline attachment queue (blobs in IndexedDB, upload on sync); offline sync conflict resolution (LWW + per-field merge UI for flagged entities); low-bandwidth sync (delta since cursor, gzip). Deepens T17 foundation. Satisfies FEATURES.md:1630-1641.
  Parallelization: Wave 81 | Blocked by: T142 | Blocks: T154
  References: FEATURES.md:1627. `platform/web/src/lib/{offline-db,regionPack}.ts`, `src/sw.ts`.
  Acceptance: offline app loads from cache; PMTiles pack in OPFS renders offline; outbox syncs on reconnect (idempotent); conflict merge UI resolves flagged fields; delta sync shrinks payload.
  QA: happy = offline+packs+outbox+conflict+delta; failure = sync conflict unresolved → flagged for merge. Evidence `.omo/evidence/task-153-disaster-cf-replatform.txt`.
  Commit: Y | feat(offline): full PWA + Dexie outbox + PMTiles OPFS packs + conflict merge + low-bandwidth delta

- [ ] 154. Offline: SMS/email fallback + printable packets + QR data packets (chunked ~2KB) + incident pack download + local/edge cache + static emergency page + incident snapshot export + one-file HTML packet + P2P field sync (WebRTC) + USB/SD sneakernet + backup command dashboard + degraded modes (read-only/AI-off/map-off/public-static) + DB restore + emergency import/export
  What to do / Must NOT do: SMS fallback; email fallback; printable fallback packets; QR code data packets (chunked JSON ~2KB/code + index header); incident pack download endpoint (one JSON bundle for field kit); local cache; edge cache (Cache API on public GETs); static emergency page fallback (CF custom error page / Worker static); incident snapshot export; one-file HTML emergency packet (inline data, opens from file://); peer-to-peer field sync (WebRTC DataChannel, LAN-first); USB/SD sneakernet bundle (import/export signed zip); backup command dashboard (read-only mirror page); read-only degraded mode (flag gates all writes); AI-disabled degraded mode; map-disabled degraded mode (table fallbacks everywhere); public portal degraded mode (static rendered snapshot); database restore workflow (D1 time-travel / R2 dump restore); emergency data export; emergency data import. Satisfies FEATURES.md:1642-1661,94 (L94 "Exportable incident packets" = the incident-pack download endpoint here).
  Parallelization: Wave 81 | Blocked by: T153 | Blocks: T155
  References: FEATURES.md:1627. `src/lib/offline/{packets,webrtc,degraded}.ts`.
  Acceptance: SMS/email fallback sends; QR packets chunk + reassemble; incident pack downloads; one-file HTML opens from file://; WebRTC P2P sync works LAN; degraded modes gate writes/map/AI; D1 time-travel restore tested.
  QA: happy = fallbacks+packets+one-file+P2P+sneakernet+degraded+restore; failure = degraded flag stuck → alert. Evidence `.omo/evidence/task-154-disaster-cf-replatform.txt`.
  Commit: Y (split per mechanism family, per orphan guard) | feat(offline): SMS/email fallbacks + printable/QR/incident packets + one-file HTML; feat(offline): WebRTC P2P + sneakernet + backup command dashboard; feat(offline): degraded modes (read-only/AI-off/map-off/public-static) + DB restore + emergency import/export

- [ ] 155. P11 integration gate: break-glass → DSR export → webhook delivery → offline pack → degraded mode
  What to do / Must NOT do: Integration test: break-glass admin (time-boxed+alert) → DSR export → webhook subscription delivers (HMAC) → offline incident pack → toggle read-only degraded mode. P11 gate.
  Parallelization: Wave 82 (P11 gate) | Blocked by: T143-T154 | Blocks: P12+
  References: FEATURES.md:1444-1662. `platform/worker/test/p11_integration.test.ts`.
  Acceptance: test green; covers break-glass audit + DSR + webhook HMAC/retry + offline pack + degraded flag.
  QA: happy = full P11 loop; failure = webhook HMAC fail → 401. Evidence `.omo/evidence/task-155-disaster-cf-replatform.txt`.
  Commit: Y | test(security): P11 integration gate (break-glass→DSR→webhook→offline→degraded)

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- PHASE P12: MULTI-AGENCY + DRILLS + EARLY WARNING + RECOVERY + FINANCE — FEATURES.md:1731-1772, 1774-1794, 1795-1816, 1817-1834 -->
<!-- Build blocks: :1732 (agencies+mous+incident_shares+EDXL-RM+liaison+unified command), :1753 (exercise_mode flag+injects Workflow+sim-cell+feed replay+HSEEP EEG+AAR+teardown), :1775 (watches+threshold rules+CAP relay+subscriptions+pre-registry+checklists+family plan+siren registry+seasonal+ward score), :1796 (needs_registry+cases+CVA+debris+rebuild+donor ledger+lessons), :1818 (cost_codes+cost_entries+214 time capture+rate cards+FEMA PA A-G+budget caps+burn-rate+multi-currency+donor allocation+claim packet) -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 156. Multi-Agency: agencies registry + capability profile + MOU tracker + liaison officer role + cross-org incident sharing (incident_shares scope grants)
  What to do / Must NOT do: `agencies` registry (internal orgs + external stubs); agency capability profile (resources, skills, coverage area); MOU/mutual aid agreement tracker (scope + expiry + doc in R2); liaison officer role (single-incident foreign-org access); cross-org incident sharing (`incident_shares`: incident_id, target_org, scope: layers[]/panels[]) enforced in policy middleware; shared layers = read-only mirrors. Satisfies FEATURES.md:1735-1740.
  Parallelization: Wave 83 | Blocked by: T155 | Blocks: T157
  References: FEATURES.md:1732. `src/db/schema/{agencies,mous,incident_shares}.ts`.
  Acceptance: agency registry CRUD; MOU with expiry; liaison accesses one incident in foreign org (scoped); shared layer read-only (assert write 403).
  QA: happy = agencies+MOU+liaison+sharing; failure = cross-org write → 403. Evidence `.omo/evidence/task-156-disaster-cf-replatform.txt`.
  Commit: Y | feat(multiagency): agencies + capability + MOU + liaison + cross-org incident_shares

- [ ] 157. Multi-Agency: shared panel publishing + inter-org resource request/offer (EDXL-RM) + mutual aid deployment tracking + unified command (dual approval) + JIC workspace + inter-agency directory + chat (AgencyRoom DO) + regional dashboard + debrief
  What to do / Must NOT do: Shared panel publishing (pick panels visible to partner); inter-org resource request (EDXL-RM record + webhook to target org); inter-org resource offer; mutual aid deployment tracking (who sent what where); unified command mode (one incident, multiple command-owner orgs, dual approval on key actions); joint information center workspace (shared PIO drafts); inter-agency contact directory; inter-agency chat channel (`AgencyRoom` DO — Metis B1 distinct DO, scoped to share); regional multi-incident dashboard (aggregator Worker reading multiple orgs the user belongs to); agency performance debrief (post-incident, private). Satisfies FEATURES.md:1741-1750.
  Parallelization: Wave 83 | Blocked by: T156 | Blocks: T158
  References: FEATURES.md:1732. `src/do/AgencyRoom.ts`, `src/api/routes/multiagency.ts`.
  Acceptance: shared panel visible to partner; EDXL-RM request routes via webhook; mutual aid tracked; unified command dual-approval (assert single-approval blocked); AgencyRoom chat works; regional dashboard aggregates.
  QA: happy = panels+EDXL+aid+unified+JIC+directory+chat+regional+debrief; failure = single-org approval in unified mode → blocked. Evidence `.omo/evidence/task-157-disaster-cf-replatform.txt`.
  Commit: Y | feat(multiagency): shared panels + EDXL-RM + mutual aid + unified command + JIC + AgencyRoom chat + regional dashboard

- [ ] 158. Drills: exercise_mode flag (banner+DRILL watermark) + external comms lockout + scenario builder (injects) + inject scheduler (Workflow) + sim-cell console + feed replay + tabletop/full-scale + objectives (HSEEP) + evaluator forms (EEG) + observations + roster + timeline + AAR + improvement plan + teardown + drill comparison
  What to do / Must NOT do: `exercise_mode` flag on incident → loud persistent banner, all comms watermarked "DRILL", external send disabled or routed to sim inbox. Scenario = `injects` table (t_offset, kind, payload) executed by Workflow timer into the normal ingest path. Sim-cell console (inject editor + manual fire + pause/resume clock). Feed replay (stored feed snapshots re-emitted on schedule). Tabletop exercise mode (discussion prompts, no field ops); functional/full-scale exercise mode. Exercise objectives tracker (HSEEP keyword); evaluator forms (EEG-style, Form Builder); evaluator observation log; participant roster + sign-in; exercise timeline capture (auto from events); exercise AAR (draft from timeline); improvement plan tracker (findings → tasks w/ owners); exercise data teardown (cascade-delete or archive to exercise org); drill performance comparison (across exercises). Satisfies FEATURES.md:1756-1772.
  Parallelization: Wave 84 | Blocked by: T155 | Blocks: T159
  References: FEATURES.md:1753. `src/workflows/injectScheduler.ts`, `src/api/routes/drills.ts`.
  Acceptance: exercise banner + watermark; external send locked; inject fires into ingest via Workflow; sim-cell pause/resume; feed replay; EEG evaluator form; AAR drafts; teardown cascades.
  QA: happy = exercise mode+injects+simcell+replay+EEG+AAR+teardown; failure = external send in exercise → blocked. Evidence `.omo/evidence/task-158-disaster-cf-replatform.txt`.
  Commit: Y | feat(drills): exercise mode + inject scheduler Workflow + sim-cell + feed replay + HSEEP/EEG + AAR + teardown

- [ ] 159. Early Warning: watch states + polygon + threshold auto-rules + CAP relay + public location subscriptions + fan-out + vulnerable household pre-registry + assist matching + checklists + family plan + school drill scheduler + siren registry + seasonal campaigns + ward score + shelter mapping drive + pre-incident briefs
  What to do / Must NOT do: `watches` (hazard, polygon GeoJSON+H3, state: monitoring/advisory/watch/warning) promoted manually or by threshold rules (`gauge X > level Y for Z min` evaluated by cron over feed data). Public subscriptions = point/polygon + channel prefs; alert fan-out reuses Communications. Pre-registry = opt-in vulnerable household records (consent-tracked, sensitive class). Pre-registry evacuation assist matching (feeds door-to-door tasking). Household preparedness checklist (go-bag, docs, meds); family emergency plan builder (contacts, meeting points, printable); school drill scheduler (term calendar + participation log); community siren registry (location + coverage + test log); seasonal preparedness campaigns (scheduled content pushes); ward preparedness score (composite metric + leaderboard); pre-disaster shelter mapping drive (crowdsource + verify queue); pre-incident risk briefs (monsoon/cyclone season memos). Satisfies FEATURES.md:1778-1793.
  Parallelization: Wave 84 | Blocked by: T94(comms) | Blocks: T160
  References: FEATURES.md:1775. `src/db/schema/{watches,subscriptions,preregistry}.ts`, `src/cron/watchRules.ts`.
  Acceptance: threshold rule promotes watch; CAP relay ingests official CAP → mirrors to subscribers; pre-registry consent-tracked; family plan printable; ward score computed.
  QA: happy = watches+threshold+relay+subscriptions+preregistry+plans+sirens+ward; failure = threshold not crossed → no promote. Evidence `.omo/evidence/task-159-disaster-cf-replatform.txt`.
  Commit: Y | feat(earlywarning): watches + threshold rules + CAP relay + subscriptions + pre-registry + plans + drills + ward score

- [ ] 160. Recovery: household needs registry + case management (caseworker/stages/visits) + caseworker load + CVA tracking + relief distribution ledger + debris volume + debris removal tasking + temp housing + rebuild permit + structure repair + livelihood + donor pledge ledger + grants + long-term dashboard + milestones + lessons-learned + anniversary reminders
  What to do / Must NOT do: `needs_registry` (household, needs[], assessed_at) seeded from damage + requests; case management = `cases` w/ caseworker, stages, visit notes (sensitive class). Caseworker assignment + load view; CVA = cash/voucher disbursement records (amount, channel, status) — track only, no payment rails. Relief distribution ledger (who received what, dedup); debris volume estimation (per zone, m³); debris removal tasking (feeds Task system); temporary housing tracker; rebuild permit workflow; structure repair status tracker (grade → permit → done); livelihood restoration tracking (crops, shops, boats); donor pledge tracker (pledged vs received vs distributed); grant utilization reports; long-term recovery dashboard (months timescale); recovery milestone timeline; lessons-learned registry (tagged findings → memory graph); anniversary review reminders (cron + memo draft). Satisfies FEATURES.md:1799-1815.
  Parallelization: Wave 85 | Blocked by: T132(damage) | Blocks: T161
  References: FEATURES.md:1796. `src/db/schema/recovery.ts`.
  Acceptance: needs registry seeded; case management CRUD; CVA track-only; debris volume per zone; rebuild permit flow; donor ledger reconciles; lessons-learned tagged.
  QA: happy = needs+cases+CVA+debris+rebuild+livelihood+donor+dashboard+lessons; failure = CVA payment attempt → blocked (track-only). Evidence `.omo/evidence/task-160-disaster-cf-replatform.txt`.
  Commit: Y | feat(recovery): needs registry + case mgmt + CVA + debris + rebuild + donor ledger + lessons-learned

- [ ] 161. Finance: cost codes + cost entry ledger + personnel time capture (ICS-214 × rate cards) + role/equipment rates + purchase/contract + FEMA PA A-G + budget caps + burn-rate dashboard + multi-currency + donor-fund allocation + cost summary export + claim-ready packet
  What to do / Must NOT do: `cost_codes` (incident-scoped chart) + `cost_entries` (code, amount, currency, source: time/equipment/purchase/contract). Time capture from ICS-214 entries × `rate_cards` (role hourly); equipment hours × equipment rates. Purchase and contract logging; FEMA reimbursement categories (PA cat A–G as tagging dimension for reimbursement-shaped exports); budget caps (soft alerts at thresholds); burn-rate dashboard (cost over time vs budget); multi-currency (store minor units + currency, daily rate snapshot table for rollups); donor-fund allocation tracking (fund → cost code mapping); cost summary report export (CSV/XLSX via Reports); claim-ready documentation packet (costs + evidence bundle). Satisfies FEATURES.md:1821-1833.
  Parallelization: Wave 85 | Blocked by: T31(ICS-214),T107(reports) | Blocks: T162
  References: FEATURES.md:1818. `src/db/schema/finance.ts`, `src/lib/finance/timeCapture.ts`.
  Acceptance: ICS-214 entries × rate cards → cost entries; FEMA PA A-G tags; burn-rate dashboard renders; multi-currency rollups via rate snapshots; claim packet bundles costs + evidence.
  QA: happy = codes+entries+time+rates+FEMA+budget+burn+currency+claim; failure = budget cap exceeded → soft alert (not block). Evidence `.omo/evidence/task-161-disaster-cf-replatform.txt`.
  Commit: Y | feat(finance): cost codes + entries + ICS-214 time capture + FEMA PA A-G + burn-rate + multi-currency + claim packet

- [ ] 162. P12 integration gate: MOU share → EDXL-RM request → exercise inject → early-warning threshold promote → recovery case → finance time capture
  What to do / Must NOT do: Integration test across P12: MOU share incident → EDXL-RM resource request → exercise inject fires → early-warning threshold promotes watch → recovery case from damage → finance time capture from ICS-214. P12 gate.
  Parallelization: Wave 86 (P12 gate) | Blocked by: T156-T161 | Blocks: P13+
  References: FEATURES.md:1731-1834. `platform/worker/test/p12_integration.test.ts`.
  Acceptance: test green; covers cross-org sharing + exercise lockout + threshold + recovery + finance.
  QA: happy = full P12 loop; failure = exercise external send → blocked. Evidence `.omo/evidence/task-162-disaster-cf-replatform.txt`.
  Commit: Y | test(multiagency): P12 integration gate (MOU→EDXL→drill→warning→recovery→finance)

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- PHASE P13: OBSERVABILITY/QA + DEPLOYMENT + ACCESSIBILITY/LOCALIZATION — FEATURES.md:1835-1857, 1858-1878, 1879-1904 -->
<!-- Build blocks: :1836 (structured JSON logs+request_id+Logpush+Sentry+Analytics Engine+SLO+alerting+vitest-pool-workers+Playwright+k6+axe+screenshot diff+chaos+probes), :1859 (wrangler envs+CI+preview+gated migrations+backup Workflow+Time Travel+R2 lifecycle+gradual rollout+rollback+CF for SaaS+Smart Placement+secrets+terraform+cost+status page), :1880 (WCAG 2.2 AA+keyboard+ARIA+focus+map table-twin+high-contrast+reduced motion+dyslexia+touch+colorblind+plain-language+TTS+i18next+locale mgmt+AI translation review+glossary lock+RTL+Indic+per-user/incident lang+Intl formatting) -->
<!-- NOTE: P13 was THREADED from P0 (T4 request_id, T33 sentry, T44 axe/screenshot, T63 Playwright e2e). This phase = the FINISH wave consolidating remaining items. -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 163. Observability: log shipping (Logpush → Baselime/Axiom) + SLO dashboards + error-budget alerting + queue/DLQ depth alerts + feed staleness alerts
  What to do / Must NOT do: Structured JSON logging (done T4) + request_id (T4); log shipping (Workers Logpush → Baselime/Axiom, OTel-ish); error tracking (Sentry toucan-js — T33); metrics (Analytics Engine — T135). NEW finish items: SLO dashboards (p95 latency, error rate); alerting on error budget burn; queue depth + DLQ alerts; feed staleness alerts (last_success_at > threshold). Satisfies FEATURES.md:1841-1847.
  Parallelization: Wave 87 | Blocked by: T162 | Blocks: T164
  References: FEATURES.md:1836. `src/lib/observability/{slo,alerts}.ts`.
  Acceptance: Logpush ships structured logs; SLO dashboard renders p95/error-rate; error-budget burn triggers alert; queue depth/DLQ alert fires; feed staleness alert fires.
  QA: happy = logpush+SLO+alerts; failure = error budget burn → alert fires. Evidence `.omo/evidence/task-163-disaster-cf-replatform.txt`.
  Commit: Y | feat(observability): Logpush + SLO dashboards + error-budget + queue/DLQ/staleness alerts

- [ ] 164. QA testing suite: unit (vitest) + integration (vitest-pool-workers/Miniflare) + e2e (Playwright) + load (k6) + a11y (axe) + visual regression (screenshot diff) + seed fixtures + chaos drills + synthetic probes
  What to do / Must NOT do: Unit tests (vitest); integration tests on Workers runtime (vitest-pool-workers + Miniflare — Metis C6 per-binding approach); e2e (Playwright vs preview deploys — T63); load tests (k6 on ingest + map routes); accessibility tests in CI (axe-core — T44); visual regression tests (screenshot diff on map/panels — T44); seed-based deterministic test fixtures; chaos drill scripts (feed outage, DLQ flood in staging); synthetic uptime probes (external ping on public routes). Satisfies FEATURES.md:1848-1856.
  Parallelization: Wave 87 | Blocked by: T162 | Blocks: T165
  References: FEATURES.md:1836. `platform/worker/test/`, `platform/web/test/`, `platform/load/k6/*.js`.
  Acceptance: full QA suite green in CI; k6 load test reports p95; chaos drill recovers; probe pings public routes.
  QA: happy = full suite green; failure = chaos drill → recovery validated. Evidence `.omo/evidence/task-164-disaster-cf-replatform.txt`.
  Commit: Y | feat(observability): full QA suite (unit/integration/e2e/load/a11y/visual/chaos/probes)

- [ ] 165. Deployment: CI pipeline (typecheck→test→deploy) + preview deploys per PR + gated D1 migrations (drizzle-kit + manual approve) + rollback notes
  What to do / Must NOT do: wrangler environments dev/staging/prod (T2); GitHub Actions CI pipeline (typecheck → test → deploy preview per PR (workers.dev or versioned) → promote); migrations = drizzle-kit generate, applied via gated CI step (`wrangler d1 migrations apply`), never auto on prod without approval; migration rollback notes (down scripts where possible). Satisfies FEATURES.md:1862-1866.
  Parallelization: Wave 88 | Blocked by: T162 | Blocks: T166
  References: FEATURES.md:1859. `.github/workflows/ci.yml`.
  Acceptance: CI runs typecheck+test on PR; preview deploys per PR; D1 migration to prod gated (manual approve); rollback notes documented.
  QA: happy = CI+preview+gated migration+rollback; failure = migration fails CI → blocked. Evidence `.omo/evidence/task-165-disaster-cf-replatform.txt`.
  Commit: Y | feat(deploy): CI pipeline + preview deploys + gated D1 migrations + rollback notes

- [ ] 166. Deployment: nightly D1→R2 backup (Workflow) + D1 Time Travel restore runbook + R2 lifecycle rules + gradual rollout + instant rollback + tenant custom domains (CF for SaaS) + Smart Placement + secrets per env + IaC (terraform) + cost monitoring + status page
  What to do / Must NOT do: Nightly D1 → R2 backup (Workflow dump); D1 Time Travel restore runbook (tested script); R2 lifecycle rules (tmp uploads expiry); gradual rollout deploys (percentage-based); instant rollback procedure (previous version pin); tenant custom domains (CF for SaaS); Smart Placement tuning (for chatty D1 routes); secrets management per env (wrangler secret / Secrets Store — T19); infrastructure as code (terraform cloudflare provider for buckets/queues/DNS); cost monitoring (Workers/D1/R2 usage dashboards); status page for the platform itself (public uptime page). Satisfies FEATURES.md:1867-1877.
  Parallelization: Wave 88 | Blocked by: T165 | Blocks: T167
  References: FEATURES.md:1859. `src/workflows/backupD1.ts`, `infra/terraform/`.
  Acceptance: nightly backup Workflow produces R2 dump; Time Travel restore tested; R2 lifecycle expires tmp; gradual rollout + instant rollback work; custom domain resolves; IaC applies; status page public.
  QA: happy = backup+restore+lifecycle+rollout+rollback+domains+IaC+cost+status; failure = rollback fails → runbook. Evidence `.omo/evidence/task-166-disaster-cf-replatform.txt`.
  Commit: Y | feat(deploy): backup Workflow + Time Travel + R2 lifecycle + gradual rollout + rollback + CF for SaaS + terraform + cost + status page

- [ ] 167. A11y: WCAG 2.2 AA conformance (audit + axe CI) + full keyboard nav (dnd-kit sensors) + screen reader (ARIA live regions) + focus mgmt + skip links + map alternative views (table twin)
  What to do / Must NOT do: WCAG 2.2 AA (audit checklist + axe CI — T44 threaded); full keyboard navigation (incl. board drag via dnd-kit keyboard sensors); screen reader optimized panels (ARIA live regions for alerts); focus management + skip links; map alternative views (table twin for every map — T48 threaded). Satisfies FEATURES.md:1883-1887.
  Parallelization: Wave 89 | Blocked by: T162 | Blocks: T168
  References: FEATURES.md:1880. `platform/web/src/lib/a11y.ts`.
  Acceptance: axe-core 0 violations across all pages; full keyboard path through command center + kanban; ARIA live announces alerts; every map has a table twin.
  QA: happy = WCAG+keyboard+ARIA+table-twin; failure = a11y violation → CI red. Evidence `.omo/evidence/task-167-disaster-cf-replatform.txt`.
  Commit: Y | feat(a11y): WCAG 2.2 AA + keyboard nav + ARIA live + focus/skip + map table twins

- [ ] 168. A11y: high-contrast + reduced motion + dyslexia font + large-touch-target field mode (gloves) + colorblind palettes (dual coding) + plain-language mode + TTS for public alerts
  What to do / Must NOT do: High-contrast theme; reduced motion mode (prefers-reduced-motion); dyslexia-friendly font option; large-touch-target field mode (gloves keyword); colorblind-safe palettes (dual coding icon+text, never color-only); plain-language mode (alternate string set, short sentences); text-to-speech for public alerts (Web Speech API). Satisfies FEATURES.md:1888-1894.
  Parallelization: Wave 89 | Blocked by: T167 | Blocks: T169
  References: FEATURES.md:1880. `platform/web/src/lib/{themes,tts}.ts`.
  Acceptance: each mode toggles + persists; colorblind palette dual-codes status; plain-language swaps strings; TTS reads public alert.
  QA: happy = 7 modes; failure = color-only status → violates dual-coding. Evidence `.omo/evidence/task-168-disaster-cf-replatform.txt`.
  Commit: Y | feat(a11y): high-contrast + reduced-motion + dyslexia + gloves + colorblind + plain-language + TTS

- [ ] 169. Localization: i18n framework (i18next+ICU) + locale file management (KV/R2) + AI translation draft pipeline + review queue + glossary locking + RTL + Indic fonts + per-user/incident language + Intl formatting
  What to do / Must NOT do: i18n framework (i18next + ICU — T16 threaded); locale file management (KV/R2 backed); AI translation draft pipeline (draft → human review queue); translation review queue (per-string approve); glossary term locking (fixed translations for key terms — place names, "evacuate"); RTL layout support (CSS logical properties); Indic script font support (Noto fonts); per-user language preference; per-incident default language; localized number/date/units formatting (Intl APIs — T16 threaded). Satisfies FEATURES.md:1895-1904.
  Parallelization: Wave 90 | Blocked by: T168 | Blocks: T170
  References: FEATURES.md:1880. `src/lib/i18n/{review,glossary}.ts`.
  Acceptance: AI translation drafts land in review queue; glossary lock prevents term override; RTL renders correctly; Indic fonts render; per-user/incident language persists; Intl formats localize.
  QA: happy = i18n+review+glossary+RTL+Indic+prefs+Intl; failure = glossary term override → blocked. Evidence `.omo/evidence/task-169-disaster-cf-replatform.txt`.
  Commit: Y | feat(a11y): i18n review queue + glossary lock + RTL + Indic + per-user/incident lang + Intl formatting

- [ ] 170. P13 integration gate: CI green + SLO + backup/restore + WCAG + i18n RTL
  What to do / Must NOT do: Integration test: CI pipeline green (typecheck+test+deploy) + SLO dashboard + nightly backup + Time Travel restore + WCAG axe 0 + RTL locale renders. P13 gate.
  Parallelization: Wave 91 (P13 gate) | Blocked by: T163-T169 | Blocks: P14
  References: FEATURES.md:1835-1904. `platform/worker/test/p13_integration.test.ts`.
  Acceptance: test green; covers CI + SLO + restore + WCAG + RTL.
  QA: happy = full P13 loop; failure = a11y violation → CI red. Evidence `.omo/evidence/task-170-disaster-cf-replatform.txt`.
  Commit: Y | test(observability): P13 integration gate (CI+SLO+restore+WCAG+RTL)

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- CROSS-CUTTING: INTEGRATIONS CONSOLIDATION (Metis B6) — FEATURES.md:1388-1442 (45 adapters) -->
<!-- Most adapters landed in consuming phases (geocoder→T41, weather→T77, feeds→T77-79, comms→T90, AI→T100, auth→T8). This todo covers the remaining outbound/data interop adapters behind the shared `integrations` registry + adapter interface (T6). -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 171. Integrations: remaining adapters (Slack/Discord/Teams + Sheets/Airtable + ArcGIS + WMS/WFS + QGIS/GeoServer export + IoT/MQTT + Sahana/Ushahidi + SSO/SAML/OIDC) behind shared registry
  What to do / Must NOT do: Every integration = thin adapter module behind interface + `integrations(kind,config json,enabled,secrets-ref)` registry row (T6). This todo OWNS the Integrations section end-to-end: it builds the genuinely-missing adapters here AND enumerates (cross-refs) the integrations already built in consuming phases. **Build here (no other home):** Bhuvan (ISRO) layer import (L1404); FEMA-style data import (L1426); Government API import (L1427); NGO database import (L1428); radio dispatch system export (L1434); emergency call center export (L1435). **Build here (already listed):** Slack, Discord, Microsoft Teams (L1415-1417); Google Sheets (L1418), Airtable (L1419); ArcGIS import (L1420); WMS/WFS (L1421); QGIS export (L1422), GeoServer export (L1423); IoT/MQTT (L1433); Sahana Eden/Ushahidi (L1437); SSO/SAML/OIDC/Clerk/custom auth (L1438-1442). **Cross-refs (built in consuming phases, enumerated here for the F1 coverage ledger):** OpenAI-compatible AI + custom base URL/key (L1392-1395 → T100); Workers AI (L1396 → T100); weather Open-Meteo (L1397 → T77); NASA FIRMS (L1398 → T77); USGS earthquake (L1399 → T77); GDACS (L1400 → T77); OpenAQ (L1401 → T83); Copernicus/Sentinel (L1402 → T130); IMD/CWC India (L1403 → T83); SACHET CAP (L1404 → T92); map tile provider (L1405 → T35); geocoding (L1406 → T41); what3words (L1407 → T41); SMS (L1408 → T90); voice/IVR (L1409 → T90); email SMTP (L1410 → T90); WhatsApp (L1411 → T90); Telegram (L1412 → T90); push (L1413 → T90); webhook (L1414 → T151); OSM Overpass (L1424 → T78); Overture (L1425 → T78); hospital system FHIR (L1429 → T116); shelter system (L1430 → T65); volunteer platform (L1431 → T60); drone platform (L1432 → T129); public alerting CAP export (L1436 → T92). Inbound HMAC-verified; outbound retried via Queues. Free-first defaults. Satisfies FEATURES.md:1392-1442 (full Integrations section).
  Parallelization: Wave 91 (parallel with P13) | Blocked by: T6,T151 | Blocks: —
  References: FEATURES.md:1388. `src/integrations/{slack,discord,teams,sheets,airtable,arcgis,wms,wfs,qgis,geoserver,mqtt,sahana,sso,saml,oidc}.ts`.
  Acceptance: each adapter registered + stubbed in dev (returns fixture); real-key path unit-tested with mocked HTTP; HMAC verified inbound; outbound retried via webhookDeliveryQ (T151).
  QA: happy = 15 adapters registered + stubbed; failure = bad HMAC → 401; unavailable provider → DLQ. Evidence `.omo/evidence/task-171-disaster-cf-replatform.txt`.
  Commit: Y | feat(integrations): 15 remaining adapters (chat/sheets/ArcGIS/OGC/exports/MQTT/Sahana/SSO) behind registry

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- PHASE P14: SCI-FI BUT POSSIBLE FEATURES — FEATURES.md:1663-1729 (66 checkboxes) -->
<!-- Build block: :1664 (composition-only; deck.gl/CesiumJS twin; chained AI plan gens; N-draft debate+judge; H3 probability maps; vision thermal hints; WebRTC mesh; Web Speech voice; predictive positioning). Metis B8: each lands as draft + human-approve gate; acceptance = produces draft artifact over real data, NOT validated sim accuracy. -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 172. Sci-Fi: city-scale live digital twin (deck.gl/CesiumJS + all live layers + time slider) + future timeline explorer + real-time evac outcome predictor + command decision consequence simulator
  What to do / Must NOT do: City-scale live disaster digital twin (deck.gl/CesiumJS + all live layers + time slider); sci-fi disaster future timeline explorer; real-time evacuation outcome predictor; command decision consequence simulator. **Live 3D disaster map from drone feeds (L1190, CesiumJS — composition over drone orthomosaic + live layers, draft-only).** Composition-only — stacks existing live layers + Prediction scenario snapshots. Satisfies FEATURES.md:1667,1030-1033,1695,1696,1190.
  Parallelization: Wave 92 | Blocked by: T134(predsim),T170 | Blocks: —
  References: FEATURES.md:1664. `platform/web/src/pages/twin/DigitalTwin.tsx`.
  Acceptance: twin renders all live layers + time slider; outcome predictor links a scenario snapshot; consequence simulator shows decision→scenario. No new infra.
  QA: happy = twin+timeline+predictor+consequence; failure = missing live layer → graceful. Evidence `.omo/evidence/task-172-disaster-cf-replatform.txt`.
  Commit: Y | feat(scifi): digital twin + timeline explorer + evac predictor + consequence simulator

- [ ] 173. Sci-Fi: AI-generated full emergency response plan in seconds (chained drafts → IAP template) + multi-agent command simulation + simulated evac of every household + one-click plans (briefing room/public-safe portal/AAR/replay video/compliance review/stress test/best-response comparison/full-city evac sim)
  What to do / Must NOT do: AI-generated full emergency response plan in seconds (chained drafts → IAP template); multi-agent command simulation (N role-prompted agents + shared state JSON); simulated evacuation of every household (building footprints × routing, Containers job); one-click command center briefing room (war-room layout + auto-brief); one-click public-safe situation portal (publish snapshot pipeline); one-click after-action report from all incident data (AAR prompt over full timeline); one-click disaster replay video from timeline and map data (frame capture + Containers ffmpeg); one-click policy compliance review (SOP checklist vs incident events prompt); one-click impossible-scenario stress test (black-swan param sets); one-click best-response plan comparison (tradeoff matrix over N drafts); one-click full-city evacuation simulation (Containers batch job). All = chained AI calls → draft, human-approve. Satisfies FEATURES.md:1668,1669,1670,1702-1712.
  Parallelization: Wave 92 | Blocked by: T104(copilots),T134 | Blocks: —
  References: FEATURES.md:1664. `src/lib/scifi/planGens.ts`.
  Acceptance: each one-click produces a draft artifact (review_status=draft); plan generator chains gather→draft→critique→assemble; multi-agent sim runs N agents; replay video produced via Containers.
  QA: happy = plan+sim+one-click×9; failure = AI down → fallback draft. Evidence `.omo/evidence/task-173-disaster-cf-replatform.txt`.
  Commit: Y | feat(scifi): AI response-plan generator + multi-agent sim + 9 one-click generators

- [ ] 174. Sci-Fi: hyperlocal scores (risk per building, rescue priority per street, safe corridor, trapped-person probability, casualty surge, panic-spread, misinformation, supply-chain collapse, infra cascade, shelter overflow, responder danger, route reopening, public mood)
  What to do / Must NOT do: Hyperlocal risk score for every building (hazard × exposure × vulnerability per footprint); rescue priority score for every street (requests × population × access); real-time safe corridor generation (routing graph minus hazard H3 cells); automatic trapped-person probability map (report density × building damage × time); automatic casualty surge prediction (triage counts trend → hospital load forecast); automatic panic-spread prediction from public reports (report velocity per zone); automatic misinformation outbreak detector (embedding clusters of rumor reports); automatic supply chain collapse predictor (burn rate vs inbound deliveries); automatic infrastructure cascade failure predictor (dependency graph BFS); automatic shelter overflow prevention engine (occupancy trend → rebalance); automatic responder danger prediction (position vs hazard spread forecast); automatic route reopening prediction (repair tasks ETA → graph updates); automatic public mood analysis from reports (sentiment classify, aggregate only). **L1683 (automatic command decision stress test = premortem prompt vs decision memo) is also covered here** — each score/score-overlay above is computed and rendered; the stress-test runs the premortem prompt against a decision memo (draft, human-approve). Satisfies FEATURES.md:1671-1673,1675-1685 (L1674 drone-swarm owned by T176; this todo covers L1671-1673,1675-1685 = 14 hyperlocal scores incl. L1683 stress-test + L1685 public mood).
  Parallelization: Wave 93 | Blocked by: T134,T86(pop/buildings) | Blocks: —
  References: FEATURES.md:1664. `src/lib/scifi/hyperlocal.ts`.
  Acceptance: each score computed over H3 cells/footprints + rendered as heat layer; safe corridor = routing graph minus hazard H3; predictions link to scenario snapshots. Acceptance = produces draft overlay, NOT validated accuracy.
  QA: happy = 14 hyperlocal scores; failure = missing footprint data → degraded. Evidence `.omo/evidence/task-174-disaster-cf-replatform.txt`.
  Commit: Y | feat(scifi): 14 hyperlocal probability/score overlays (risk/rescue/corridor/trapped/casualty/panic/misinfo/supply/cascade/shelter/danger/route/mood)

- [ ] 175. Sci-Fi: AI-generated content (multilingual voice briefings, radio command scripts, interactive evac assistant, personalized evac instructions, reunification match hints, live timeline reconstruction, recovery cost estimate, donation demand forecast, future disaster risk memory)
  What to do / Must NOT do: AI-generated multilingual voice briefings (briefing → translate → TTS); AI-generated radio-ready command scripts (brevity formatter prompt); AI-generated interactive public evacuation assistant (chat over public-safe data only); AI-generated personalized evacuation instructions (address → zone → route → steps); AI-generated family reunification match hints (embedding + fuzzy name match, human approve); AI-generated live disaster timeline reconstruction (events → narrative prompt); AI-generated recovery cost estimate (damage records × cost library); AI-generated donation demand forecast (needs registry trend); AI-generated future disaster risk memory (lessons-learned embeddings recalled on new incident). All draft + human-approve. Satisfies FEATURES.md:1685-1694.
  Parallelization: Wave 93 | Blocked by: T104 | Blocks: —
  References: FEATURES.md:1664. `src/lib/scifi/aiGens.ts`.
  Acceptance: each generator produces a draft artifact with citations; voice briefing → TTS audio; personalized evac from address; memory graph recalls on new incident.
  QA: happy = 9 AI generators; failure = ungrounded output → rejected. Evidence `.omo/evidence/task-175-disaster-cf-replatform.txt`.
  Commit: Y | feat(scifi): 9 AI generators (voice briefings/radio/evac assistant/personalized evac/reunification/timeline/recovery cost/donation forecast/risk memory)

- [ ] 176. Sci-Fi: drone swarm route planner + thermal survivor hinting + predictive positioning (ambulance/generator/food-water/shelter) + predictive evac reversal
  What to do / Must NOT do: Automatic drone swarm route planner (area decomposition → waypoint sets per drone); live thermal survivor hinting from drone imagery (vision model → review queue, never auto-task); predictive ambulance positioning (medical request forecast per zone); predictive generator positioning; predictive food and water staging; predictive shelter opening (evac forecast vs capacity); predictive evacuation reversal detection (movement reports against flow). **Drone sci-fi composition (P9 section tail, draft-only):** automatic safe landing zone detector (L1189, vision/geometric candidate zones → review queue); sci-fi thermal survivor hint layer (L1188, vision on thermal frames → flagged boxes). Satisfies FEATURES.md:1674,1696-1701,1187,1188,1189.
  Parallelization: Wave 94 | Blocked by: T130(drone),T135(analytics) | Blocks: —
  References: FEATURES.md:1664. `src/lib/scifi/{swarm,thermal,positioning}.ts`.
  Acceptance: swarm planner decomposes area → waypoints per drone; thermal hints → review queue (never auto-task); predictive positioning suggests staging moves from forecast.
  QA: happy = swarm+thermal+5 positioning; failure = vision down → thermal queued. Evidence `.omo/evidence/task-176-disaster-cf-replatform.txt`.
  Commit: Y | feat(scifi): drone swarm planner + thermal survivor hints + 5 predictive positioning engines

- [ ] 177. Sci-Fi: auto briefings (next 6h command briefing + next 24h op plan + next 7-day recovery plan) via cron + briefing prompt
  What to do / Must NOT do: Automatic "next 6 hours" command briefing (cron + briefing prompt); automatic "next 24 hours" operational plan; automatic "next 7 days" recovery plan. Cron-triggered chained AI prompts. Satisfies FEATURES.md:1702-1704.
  Parallelization: Wave 94 | Blocked by: T104 | Blocks: —
  References: FEATURES.md:1664. `src/cron/autoBriefings.ts`.
  Acceptance: each cron produces a draft briefing/plan at the right horizon; idempotent.
  QA: happy = 3 auto briefings; failure = cron failure → stale + alert. Evidence `.omo/evidence/task-177-disaster-cf-replatform.txt`.
  Commit: Y | feat(scifi): auto 6h/24h/7d briefings (cron + chained AI prompts)

- [ ] 178. Sci-Fi: voice-controlled incident command (Web Speech) + hands-free responder assistant + AR field map export + wearable status + smart helmet + sensor-fusion layer + community mesh + phone-to-phone sync + disaster memory graph + strategy-from-past-disasters + AI debate/red-team/blue-team + ethical-risk reviewer + public trust score + contradiction detector + unknown-unknowns + "what are we missing" advisor
  What to do / Must NOT do: Voice-controlled incident command (Web Speech API → command palette intents); hands-free responder assistant (voice in/out + tasks readback); AR-style field responder map export (GeoJSON/KML for AR apps); wearable responder status integration (webhook ingest, heart-rate alerts); smart helmet camera data import (video upload + frame analysis); sensor-fusion disaster intelligence layer (all feeds scored into one H3 risk surface); community mesh-network report sync (WebRTC local-first relay); offline phone-to-phone incident sync (WebRTC DataChannel outbox swap — extends T154); disaster memory graph across historical incidents (cross-incident entity links + embeddings); response strategy recommendation based on past disasters (similar-incident retrieval); AI commander debate mode with multiple response strategies (N drafts + judge); AI red-team vs blue-team disaster planning (adversary prompt vs plan); AI ethical-risk reviewer for evacuation decisions (checklist prompt, flags only); AI public trust score for outgoing alerts (clarity/actionability rubric prompt); AI contradiction detector across all reports (pairwise NLI prompt on clusters); AI unknown-unknowns detector (coverage gaps vs playbook expectations); AI "what are we missing" command advisor (checklist diff prompt per op period). **Decision-Support sci-fi composition (draft-only):** sci-fi command center advisor (L1347); sci-fi disaster chess engine (L1348, multi-move consequence tree); sci-fi millions-of-possible-response-plans comparison (L1349, N-plan tradeoff matrix); one-click optimal response plan draft (L1350). All AI = draft + human-approve. Satisfies FEATURES.md:1713-1729,1347,1348,1349,1350.
  Parallelization: Wave 95 | Blocked by: T104,T134 | Blocks: —
  References: FEATURES.md:1664. `src/lib/scifi/{voice,ar,wearable,sensorfusion,mesh,memorygraph,debate,reviewers}.ts`.
  Acceptance: voice command maps to palette intent; AR export produces GeoJSON/KML; wearable webhook ingested + heart-rate alert; sensor-fusion H3 risk surface renders; mesh/phone-to-phone sync via WebRTC; memory graph recalls similar incidents; debate runs N drafts + judge; reviewers flag only (no auto-block); contradiction/unknown-unknowns/"missing" advisors produce drafts.
  QA: happy = 18 sci-fi features; failure = AI down → fallback draft. Evidence `.omo/evidence/task-178-disaster-cf-replatform.txt`.
  Commit: Y (split per mechanism family, per orphan guard) | feat(scifi): voice-controlled command + hands-free assistant + AR field map export; feat(scifi): wearable + smart helmet + sensor-fusion layer; feat(scifi): community mesh + phone-to-phone sync + disaster memory graph + strategy-from-past-disasters; feat(scifi): AI debate + red-team/blue-team + ethical-risk reviewer + public trust score + contradiction detector + unknown-unknowns + "what are we missing" advisor

- [ ] 179. P14 integration gate: digital twin renders + AI plan generator + hyperlocal overlay + auto briefing
  What to do / Must NOT do: Integration test: digital twin renders all layers + AI response-plan generator produces draft + hyperlocal risk overlay renders + auto 6h briefing cron produces draft. P14 gate (acceptance = draft artifacts produced, NOT sim accuracy).
  Parallelization: Wave 96 (P14 gate) | Blocked by: T172-T178 | Blocks: final
  References: FEATURES.md:1663-1729. `platform/worker/test/p14_integration.test.ts`.
  Acceptance: test green; all 66 sci-fi checkboxes have a draft-producing todo; human-approve gate enforced.
  QA: happy = full P14 loop; failure = auto-publish attempt → blocked. Evidence `.omo/evidence/task-179-disaster-cf-replatform.txt`.
  Commit: Y | test(scifi): P14 integration gate (twin+plan+hyperlocal+auto-briefing, draft-only)

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- FINAL: PARITY CLEANUP + v1 REMOVAL — Metis B7 (parity defined as P0-P13 gates green, not v1 feature-match) -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 180. Final: full FEATURES.md checkbox coverage ledger + v1 removal
  What to do / Must NOT do: Run F1 coverage audit — re-walk FEATURES.md lines 69-1904 line-by-line, confirm every `[x]` maps to a completed todo's enumerated acceptance; produce `.omo/evidence/F1-coverage-ledger-disaster-cf-replatform.csv`. Once P0-P13 gates green (Metis B7: parity = these gates, NOT v1 feature-match), remove v1 `backend/`+`frontend/` dirs + v1 docker-compose/alembic. Must NOT remove v1 before P0-P13 gates green.
  Parallelization: Wave 97 (final) | Blocked by: T179 | Blocks: —
  References: FEATURES.md (all). `.omo/evidence/F1-coverage-ledger-disaster-cf-replatform.csv`.
  Acceptance: coverage ledger shows 0 orphan checkboxes; `backend/`+`frontend/` removed; `platform/` is sole runtime; all P0-P13 integration gates green.
  QA: happy = 0 orphans + v1 removed + gates green; failure = any orphan → fails with line number. Evidence `.omo/evidence/task-180-disaster-cf-replatform.txt`.
  Commit: Y | chore(platform): final coverage ledger + v1 FastAPI/frontend removal (parity reached)

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete. (Metis D5: each wave defined.)
- [ ] F1. Plan compliance audit — re-walk FEATURES.md line-by-line; confirm every `[x]` checkbox (lines 69-1904) maps to a completed todo's enumerated acceptance; flag any orphan. Produce `.omo/evidence/F1-coverage-ledger-disaster-cf-replatform.csv` (checkbox_line → todo_id → done?).
- [ ] F2. Cross-tenant isolation sweep — for every data-touching route, run a two-org test (org A cannot read/write org B); assert org_id middleware + serializer. Evidence `.omo/evidence/F2-tenancy-isolation-disaster-cf-replatform.txt`.
- [ ] F3. Degraded/offline-mode sweep — toggle every degraded-mode flag (AI off, map off, read-only, low-bandwidth, offline); assert the table/list twin renders and writes queue to outbox. Evidence `.omo/evidence/F3-degraded-mode-disaster-cf-replatform.txt`.
- [ ] F4. Conventions-invariants sweep — verify audit hash-chain integrity across all `events`; verify idempotency on every queue/webhook/cron path; verify AI artifacts all `review_status=draft` until approved; verify ULID (not UUID) everywhere. Evidence `.omo/evidence/F4-invariants-disaster-cf-replatform.txt`.

## Commit strategy
- Every todo commits exactly once (Implementation + Test = ONE todo) with `feat(<scope>): <summary>` per FEATURES.md Agent Protocol (L11). Scope = section short-name (core/incidents/command/map/tasks/field/requests/volunteer/shelters/missing/medical/logistics/infra/ingestion/weather/popimpact/comms/public/ai/reports/evac/predsim/drone/damage/analytics/decision/search/kb/integrations/security/compliance/admin/devplatform/offline/multiagency/drills/earlywarning/recovery/finance/observability/deploy/a11y/scifi).
- Integration-gate todos commit as `test(<scope>): P<N> integration gate (...)`.
- The platform-skeleton todos (T1-T6) commit as `chore(platform): ...`.
- Atomic: one todo = one commit; never bundle unrelated todos. **Exception (Metis D4 / orphan guard):** mechanism-dense todos (T93 comms drafts, T149 admin, T154 offline, T178 sci-fi) split into ONE commit per mechanism family (see each todo's `Commit: Y (split per mechanism family)` line) — the todo is a wave-grouping, each family is a distinct atomic commit. Re-runs after a failing QA commit a `fix(<scope>): ...` follow-up, not an amend.
- Conventional Commits style; no Co-authored-by/AI trailers unless requested. Branch: `feat/disaster-cf-replatform` (one long-lived branch) or per-phase feature branches merged to main — worker's choice, but phase gates (P0-P14 integration tests) must be green before merging a phase.
- Final v1 removal (T180) commits as `chore(platform): final coverage ledger + v1 FastAPI/frontend removal (parity reached)`.

## Success criteria
- **Coverage (F1):** every FEATURES.md checkbox (lines 69-1904, ~1,631 `[x]`) maps to a completed todo's enumerated acceptance — zero orphans. Evidence: `.omo/evidence/F1-coverage-ledger-disaster-cf-replatform.csv`.
- **Tenancy isolation (F2):** every data-touching route passes a two-org test (org A cannot read/write org B). Evidence: `.omo/evidence/F2-tenancy-isolation-disaster-cf-replatform.txt`.
- **Degraded modes (F3):** every Offline/degraded twin (AI-off, map-off, read-only, low-bandwidth, offline) renders the table/list twin and queues writes to the outbox. Evidence: `.omo/evidence/F3-degraded-mode-disaster-cf-replatform.txt`.
- **Conventions-invariants (F4):** audit hash-chain verifies across all `events`; idempotency on every queue/webhook/cron path; all AI artifacts `review_status=draft` until approved; ULIDs (not UUIDs) everywhere. Evidence: `.omo/evidence/F4-invariants-disaster-cf-replatform.txt`.
- **Phase gates:** all P0-P14 integration-gate tests (T20,T34,T48,T64,T74,T88,T94,T99,T111,T125,T134,T142,T155,T162,T170,T179) green.
- **Ship readiness:** CI (typecheck+test+deploy) green; preview deploys per PR; WCAG 2.2 AA (axe 0 violations); RTL + Indic render; nightly backup + Time Travel restore tested.
- **Platform is sole runtime:** `backend/` + `frontend/` v1 dirs removed; `platform/` is the only runtime (T180).
- **No implementation during planning:** this plan was produced without editing product code; execution begins only on `$start-work`.
