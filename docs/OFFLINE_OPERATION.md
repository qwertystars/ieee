# Offline Operation

The frontend is a Progressive Web App (PWA) designed for low-connectivity and
offline field use. It caches the app shell via a service worker and queues
mutations in an IndexedDB outbox with conflict-aware replay on reconnect.

## PWA manifest

The web app manifest (`frontend/public/manifest.json`) declares the app as
installable:

```json
{
  "name": "ResQNet-SAGE",
  "short_name": "ResQNet",
  "description": "Disaster Situational Awareness & Response Platform",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "orientation": "any",
  "theme_color": "#1e293b",
  "background_color": "#0f172a",
  "icons": [
    {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
    {"src": "/icon-maskable.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "maskable"}
  ]
}
```

Users can install the app to their home screen on mobile devices. When
installed, it runs in a standalone window without browser chrome.

## Service worker

The service worker (`frontend/public/sw.js`) implements a cache-first
strategy for same-origin GET requests.

### Install

On install, the service worker precaches the app shell:

- `/` (root)
- `/index.html`
- `/manifest.json`
- `/icon.svg`
- `/icon-maskable.svg`

A single failed precache entry does not abort the install. The service worker
calls `skipWaiting()` to activate immediately on first install.

### Activate

On activation, old caches (those not matching the current `CACHE_VERSION`)
are deleted. The service worker calls `clients.claim()` to take control of
open tabs immediately.

### Fetch handling

Same-origin GET requests follow a cache-first strategy:

1. Check the cache. If present, serve from cache.
2. If not cached, fetch from network.
3. On success (200, same-type), cache a copy and return the response.
4. On network failure, serve cached `/index.html` for navigation requests.

Cross-origin and non-GET requests bypass the cache entirely and go straight
to the network. This ensures API mutations are never served from stale cache.

### Cache versioning

Bump `CACHE_VERSION` on deploys to invalidate old caches:

```javascript
const CACHE_VERSION = 'resqnet-v1';
```

The activate handler deletes all caches that do not start with the current
version prefix, ensuring users get the latest app shell after an update.

## IndexedDB outbox

The outbox (`frontend/src/lib/outbox.ts`) queues mutations when the network
is unavailable and replays them on reconnect with conflict-aware resolution.

### Data model

Each outbox item carries:

| Field | Description |
|---|---|
| `id` | ULID (26-char Crockford base32, monotonic) |
| `url` | Target API endpoint |
| `method` | POST, PATCH, PUT, or DELETE |
| `body` | Request payload |
| `content_hash` | SHA-256 of the serialized body |
| `timestamp` | Creation time (epoch ms) |
| `priority` | 1 (highest) through 4 (lowest) |
| `idempotency_key` | ULID for server-side dedup |
| `status` | pending, syncing, synced, failed, conflict |
| `conflict_resolution` | null, `last_write_wins`, or `manual` |
| `conflict_data` | Server response on conflict |
| `attempts` | Retry count |
| `last_attempt` | Last sync attempt timestamp |

### Priority ordering

Sync order on reconnect is determined by priority, then timestamp:

| Priority | Mutation type | Example |
|---|---|---|
| 1 (highest) | Text updates | POST observations, PATCH alerts |
| 2 | Coordinate updates | PATCH entities (location) |
| 3 | Task state changes | PATCH tasks (status, assignment) |
| 4 (lowest) | Imagery / media | POST imagery, uploads |

The `inferPriority(url, method)` function derives priority from the URL
pattern and HTTP method. This ensures critical text updates sync before
large imagery uploads.

### Conflict resolution

When the server returns a conflict (409), the outbox marks the item as
`conflict` with `conflict_resolution: 'manual'` and stores the server's
response in `conflict_data`. The item is not retried automatically.

For non-conflict failures (5xx, network errors), the item is marked `failed`
and the `attempts` counter increments. Failed items remain in the outbox
for manual or automatic retry.

### Conflict audit log

Every conflict is recorded in a separate IndexedDB object store (`audit`)
with:

- The item ID, URL, and method
- The conflict resolution policy (`last_write_wins` or `manual`)
- The conflict data from the server
- A timestamp

This audit trail survives outbox cleanup and provides a record of all
conflicts for post-incident review.

### ULID generation

The outbox generates ULIDs client-side using the same Crockford base32
encoding as the backend (`app.lib.ulid`). The timestamp portion encodes
`Date.now()` (48-bit), and the randomness portion is drawn from
`crypto.getRandomValues`. Same-millisecond calls increment the randomness
portion monotonically within the process.

### Idempotency

Every outbox item carries an `idempotency_key` (ULID). The server uses this
key to deduplicate requests on reconnect. If the same mutation is replayed
multiple times (e.g., the client crashed after the server processed it but
before receiving the response), the server returns the original response
instead of creating a duplicate.

## Reconciliation flow

```
1. User makes mutation offline
   → addToOutbox(url, method, body, priority)
   → Item stored in IndexedDB with status=pending

2. Network reconnects
   → getPendingItems() returns items sorted by priority, then timestamp
   → For each item:
     a. Mark status=syncing
     b. Send request with idempotency_key header
     c. On 2xx: markSynced(id) → status=synced
     d. On 409: markConflict(id, serverResponse) → status=conflict
     e. On 5xx/network error: markFailed(id, error) → status=failed, attempts++

3. Cleanup
   → clearSynced() removes synced items with no conflict_resolution
   → Conflict items remain for manual review
   → getConflictAudit() returns all conflict audit entries
```

## Offline basemap

The PMTiles basemap provides offline satellite/aerial imagery. If
`PMTILES_PATH` is not set, the frontend falls back to vector tiles (solid
dark background with vector overlays). See
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) for PMTiles activation steps.

To generate a PMTiles file for offline use:

```bash
bash scripts/offline_prep.sh   # requires tippecanoe
```

Place the file at `frontend/public/basemaps/rivertown.pmtiles` for frontend
access, or set `PMTILES_PATH` to the file path.

## Backend graceful degradation

The backend is designed to continue operating when external dependencies are
down. This supports the offline-first frontend model:

| Dependency | Offline behavior |
|---|---|
| Redis | Token denylist fails open (tokens assumed valid). Rate limiting disabled. |
| Kafka/Redpanda | Observations inserted directly into PostgreSQL. WebSocket updates not pushed. |
| Ollama LLM | LLM features fall back to structured-data-only reports. |
| ONNX models | ML inference returns `model_unavailable` response. |
| PMTiles | Frontend falls back to vector tiles. |

The `GET /api/capabilities` endpoint reports runtime availability of each
feature. The frontend can use this to show the user which features are
active. See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) for the full
blocker handling protocol.
