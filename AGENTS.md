# Disaster Situational Awareness & Response Platform

## Stack
- Cloudflare Workers (Hono + TypeScript) — `platform/worker/`
- React + Vite + Tailwind — `platform/web/`
- Shared types/utilities — `platform/packages/shared/`
- D1 (SQLite) + Drizzle ORM + Vectorize + R2 + KV + Queues + Durable Objects
- pnpm workspace + turbo

## Commands
- Build: `cd platform && pnpm build`
- Test: `cd platform && pnpm test`
- Dev: `cd platform && pnpm dev`
- Format: `cd platform && pnpm format`

## Conventions
- ULID for all IDs (not UUID)
- UTC epoch milliseconds for timestamps
- `org_id` tenancy on every table, middleware-enforced
- `visibility ∈ {public,internal,sensitive}` + `review_status ∈ {draft,reviewed,official}`
- Hash-chained append-only audit: `events(prev_hash,hash)`
- Idempotency keys on all external/queue/webhook paths
- Geometry: GeoJSON TEXT + H3 `geo_index(entity_type,entity_id,h3)` rows (no PostGIS)
- All AI output lands as `review_status=draft` until human approval
- Files under 250 pure LOC — split by responsibility
- Conventional commits: `feat(scope): description`

## Structure
```
platform/worker/src/
  api/routes/    — Hono route handlers
  db/            — Drizzle schema + migrations
  do/            — Durable Objects
  middleware/    — auth, org_id, request_id
  lib/           — shared utilities (ulid, sha256, serialize)
  auth/          — better-auth + passkeys + RBAC
  queues/        — queue consumers
  workflows/     — Cloudflare Workflows
  cron/          — cron triggers
```
