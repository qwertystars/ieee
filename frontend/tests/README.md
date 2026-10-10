# Frontend Tests

## Unit tests (Vitest)

```bash
cd frontend
npm run test          # vitest run (jsdom environment)
```

Covers:
- `src/api/client.test.ts` — API client: login, getMe, logout, error handling,
  offline outbox routing, query parameter building (18 tests)
- `src/auth/AuthContext.test.tsx` — Auth context: initial mount, login flow,
  logout flow, provider guard (8 tests)
- `src/lib/outbox.test.ts` — IndexedDB outbox: add, sync, conflict resolution,
  priority inference, ULID monotonicity, audit trail (19 tests)

Unit tests use `fake-indexeddb` for IndexedDB and mocked `fetch` — no backend
required.

## Typecheck & Lint

```bash
cd frontend
npm run typecheck     # tsc --noEmit
npm run lint          # eslint src/
```

## Build

```bash
cd frontend
npm run build         # vite build
```

## Playwright e2e tests

```bash
cd frontend
npx playwright test   # runs all specs in tests/
npm run test:a11y      # axe 4.10.2 proxy checks for keyboard and state semantics
```

`tests/a11y.spec.ts` is a deterministic scripted proxy for critical labels,
focus reachability, rationale help, and stale/offline/conflict/error regions.
It is not participant usability evidence and cannot retire the external
operator-study prerequisite.

### Prerequisites

**Playwright e2e tests require a running backend.** The full-flow tests in
`tests/e2e.spec.ts` exercise real API calls against the FastAPI backend on
`http://localhost:8000` and expect the Rivertown demo scenario to be seeded.

Start the stack before running e2e:

```bash
# From the repo root:
docker compose up --build -d db backend
docker compose exec backend python -m app.seed.seed_demo

# Then run e2e (the webServer config starts `npm run preview` automatically):
cd frontend && npx playwright test
```

Demo credentials: `admin@demo.disaster` / `demo1234`

### E2e coverage

`tests/e2e.spec.ts` covers the full responder flow:
1. Login → dashboard redirect
2. Dashboard map renders
3. Simulator starts (device count visible)
4. Alert panel appears in dashboard
5. Operator can access alert review (planning page)
6. Field responder view shows assigned tasks
7. Task status update from field view reaches command centre (dashboard)
8. Polling fallback — UI handles aging/stale data gracefully

`tests/action-card.spec.ts` and `tests/map.spec.ts` are component-level
Playwright specs that use `page.setContent()` with mocked React — they do
not require a backend.

Conflict recovery is covered by `tests/outbox-recovery.spec.ts`: a scripted
409 keeps the item visible as a manual-resolution conflict rather than
claiming synchronization success. Authenticated API responses remain excluded
from Cache Storage.
