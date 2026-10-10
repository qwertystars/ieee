# Frontend (React 18 + Vite PWA)

ResQNet-SAGE PWA: dark theme, MapLibre + deck.gl, TanStack Query v5, Tailwind.
Offline-first: mutations route to an encrypted IndexedDB outbox when offline.

## WHERE TO LOOK
| Task | Location |
|------|----------|
| API + offline routing | `src/api/client.ts` (fetch wrapper, outbox routing), `src/api/types.ts`, `src/api/token.ts` |
| Outbox | `src/lib/outbox.ts` (IndexedDB, AES-GCM), `src/lib/outbox-policy.ts` (priority/conflict), `src/hooks/useOutbox.ts` (sync, navigator.locks) |
| Auth | `src/auth/AuthContext.tsx`; low-bandwidth pref in `src/context/LowBandwidthContext.tsx` |
| Map | `src/components/MapView.tsx`, `src/components/mapLayers.ts`, `src/hooks/useMapLayers.ts`, `src/types/map.ts`, `src/lib/mapTransform.ts` |
| Pages | `src/pages/` (Login, Dashboard, Hypotheses, Planning, Simulation, Field, DeviceDetail, Audit, NotFound) |
| Reusable states | `src/components/state/` — Loading/Error/Empty/Stale/Offline (role=status, aria-live) |
| PWA | `public/sw.js` (app-shell; never caches `/api/*`), `public/manifest.json`, `public/basemaps/mumbai.pmtiles` |

## CONVENTIONS
- **Offline-first**: non-GET mutations while offline go to the outbox; sync sends Idempotency-Key + X-Device-* headers; 409 ⇒ manual conflict (never last-write-wins)
- **Freshness tiers**: `<5min fresh / 5-60min aging / >60min stale` (`types/map.ts`); stale features render in `staleColor` — honest degradation, never silent
- **Low-bandwidth mode**: 30s polling + strips map; persisted in localStorage
- **Data-age honesty**: every page surfaces StaleState/OfflineState/ErrorState; no silent failures
- Query pattern: `['incidents']` → incidentId → dependent queries with `enabled`; optimistic mutations with rollback in FieldPage

## ANTI-PATTERNS
- No `as any` / `@ts-ignore` (eslint `--max-warnings 0`)
- No `window.prompt()`; no setState-in-effect (react-hooks rules are warnings, keep them clean)
- No unmounted-toast leaks: setTimeout in toasts must be cleaned up

## COMMANDS
```bash
cd frontend && npm run test        # vitest unit (src/**/*.test.tsx)
cd frontend && npx playwright test # e2e (docker stack + seed + preview :4173)
cd frontend && npm run build       # vite build (manualChunks: react/map/query)
```
Playwright: `chromium-authenticated` (map.spec) MUST run first — freshness tiers derive from seeded data age.
