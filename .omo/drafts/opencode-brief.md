# OpenCode Mission Brief — Disaster Platform Production Build

## ultrawork mode: ACTIVE

## Project
Disaster Situational Awareness & Response Platform — Cloudflare Workers re-platform.
Monorepo: `platform/worker` (Hono + TypeScript on Workers) + `platform/web` (React+Vite) + `platform/packages/shared`.

## Current State (as of last commit c642150)
- **P0 Core Platform: COMPLETE** — skeleton, drizzle/D1, ULID, audit hash-chain, idempotency, auth provider, passkeys, RBAC, API keys, rate-limiter DO, dashboards, settings, status, notifications, seed, P0 integration gate
- **P1 Incidents + Command: COMPLETE** — IncidentRoom DO, 19 disaster types, CRUD, merge/clone, WS, command center, IAP, ICS, auto-seeds, P1 gate
- **P2 Map System: STARTED** — uncommitted route stubs exist: `geocode.ts`, `map.ts`, `mapExport.ts`, `measure.ts` in `platform/worker/src/api/routes/`

## Mission
Continue from P2 (Map System) through P14, following the master plan in `.omo/plans/disaster-cf-replatform.md`.
That plan has 180 work units across 14 phases. You are entering P2.

## Execution Rules
1. Read `.omo/plans/disaster-cf-replatform.md` to find the P2 tasks and their acceptance criteria.
2. For each task: implement → test → commit. Conventional commits only (`feat(scope): name`).
3. Run `cd platform && pnpm test` before every commit. Tests must pass.
4. Follow existing code patterns in `platform/worker/src/`.
5. Keep files under 250 pure LOC. Split by responsibility.
6. Use the exact bindings from `platform/worker/wrangler.jsonc`.
7. Every state-changing route needs: audit hash-chain entry, idempotency key support, org_id tenancy.
8. All geometry is GeoJSON TEXT + H3 index rows — no PostGIS patterns.
9. Run `cd platform && pnpm build` to verify type-checking passes.
10. Do NOT stop after one task. Keep implementing, testing, and committing until the platform is production-grade.
11. When you finish a phase, run the phase gate test and commit with `feat(phase-PN): ... gate`.
12. If you hit a blocker, document it in `.omo/drafts/blockers.md` and move to the next unblocked task.
13. The boulder never stops. ulw ulw.

## Key Files
- Master plan: `.omo/plans/disaster-cf-replatform.md`
- Features catalog: `FEATURES.md`
- Design contract: `DESIGN.md`
- DB schema: `platform/worker/src/db/schema.ts`
- Routes: `platform/worker/src/api/routes/`
- Tests: `platform/worker/test/`
- Wrangler config: `platform/worker/wrangler.jsonc`
- Shared package: `platform/packages/shared/src/`

## Verification
- `cd platform && pnpm test` — all tests pass
- `cd platform && pnpm build` — type-check + build succeeds
- `git log --oneline -5` — see recent commits for pattern
