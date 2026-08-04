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

The service worker (`frontend/public/sw.js`) implements a cache-first strategy
for the app shell and static same-origin GET requests.

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

Non-API same-origin GET requests follow a cache-first strategy:

1. Check the cache. If present, serve from cache.
2. If not cached, fetch from network.
3. On success (200, same-type), cache a copy and return the response.
4. On network failure, serve cached `/index.html` for navigation requests.

Every `/api/` request bypasses the cache, including GETs. Cross-origin and
non-GET requests also bypass it. Authenticated or sensitive API responses are
therefore never placed in a public service-worker cache, even if a caller
omits an authorization header. Navigation requests receive the cached shell
only when the network is unavailable; other failed requests return `503`.

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

Each outbox item carries the following metadata. The request body, conflict
data, and server acknowledgement are encrypted before IndexedDB persistence
with AES-GCM 256-bit encryption. IndexedDB stores the non-exportable
`CryptoKey` in a separate key ring; raw request bodies are not stored.

| Field | Description |
|---|---|
| `id` | ULID (26-char Crockford base32, monotonic even when the wall clock moves backward) |
| `url` | Target API endpoint |
| `method` | POST, PATCH, PUT, or DELETE |
| `body` | Request payload |
| `content_hash` | SHA-256 of the serialized body |
| `created_at` | Client creation time (epoch ms), checked by the server at receipt |
| `priority` | 1 (highest) through 4 (lowest) |
| `idempotency_key` | ULID for server-side dedup |
| `device_id` | Durable installation identity |
| `device_sequence` | Monotonic per-device sequence allocated transactionally in IndexedDB |
| `reinstalled` | Explicit marker when the local installation identity changes |
| `status` | `queued`, `sending`, `acked`, `failed`, or `conflict` |
| `conflict_class` | `ordinary`, `task_state`, `task_assignment`, `public_warning`, or `resource_commitment` |
| `conflict_resolution` | `null` or `manual`; last-write-wins is not a client policy |
| `conflict_data` | Encrypted authoritative server conflict response |
| `server_ack` | Encrypted authoritative server acknowledgement |
| `attempts` | Retry count |
| `last_attempt` | Last sync attempt timestamp |

### Priority ordering

Sync order on reconnect is determined by priority, then creation time. Priority
only controls delivery order; it never grants permission to overwrite a
server value:

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
`conflict` with `conflict_resolution: 'manual'`, stores the authoritative
response in encrypted `conflict_data`, and records a transition. The item is
not retried automatically. Task assignment/state, public warnings, resource
commitments, and other safety-critical classes fail closed and require a
coordinator or other authorized human to choose the resolution. There is no
last-write-wins path.

For non-conflict failures (5xx, network errors), the item is marked `failed`
and the `attempts` counter increments. Failed items remain in the outbox
for manual or automatic retry.

### Conflict audit log

Every transition and conflict is recorded in the append-only IndexedDB
`audit` store with:

- The item ID, URL, and method
- The transition (`queued` → `sending` → `acked`, or a terminal failure)
- The conflict resolution policy (`manual` only)
- The conflict data from the server
- A timestamp

The server edge boundary also appends acknowledgement, duplicate replay,
conflict, and failure decisions to the organization hash-chained audit log.
Local audit entries survive acknowledgement cleanup and provide a record of
the device lifecycle for post-incident review.

### ULID generation

The outbox generates ULIDs client-side using the same Crockford base32
encoding as the backend (`app.lib.ulid`). The timestamp portion encodes
`Date.now()` (48-bit), and the randomness portion is drawn from
`crypto.getRandomValues`. Same-millisecond calls increment the randomness
portion monotonically within the process.

### Idempotency

Every outbox item carries an `idempotency_key` (ULID), `X-Device-Id`,
`X-Device-Sequence`, `X-Client-Created-At`, and `X-Content-Hash` on replay.
The server uses the idempotency key and receipt ledger to make duplicate
replay harmless. If the client crashes after server application but before
receiving the response, replay returns a duplicate acknowledgement instead
of applying the mutation again. The authenticated
`/api/incidents/{incident_id}/sync` boundary scopes each batch to the caller’s
organization and incident, and persists the idempotency key with the receipt so
a new item ID cannot reuse an already-applied key.

### Key lifecycle, reinstall, and clock rules

- A missing active key or revoked key fails closed; queued plaintext is never
  returned to the application. Keys are non-exportable AES-GCM keys, rotate
  every 30 days, and retired ciphertext is quarantined when the key ring is
  revoked.
- Explicit revocation prevents new writes and decryption for every key in the
  ring, including retired keys. Operators must export or reconcile affected
  work through the approved human process.
- A durable device sequence is allocated transactionally with the device
  identity. A new installation gets a new device identity and an explicit
  `reinstalled` marker; the server quarantines that stream until a coordinator
  re-enrolls the device.
- The server rejects items older than 24 hours or more than 30 seconds in the
  future. Receipt time, not the client clock, is authoritative; time-uncertain
  items are quarantined rather than sent automatically.

## Reconciliation flow

```
1. User makes mutation offline
   → addToOutbox(url, method, body, priority)
   → encrypted item stored in IndexedDB with status=queued

2. Network reconnects
   → getPendingItems() first converts any orphaned `sending` items to visible `failed` recovery state
   → items are returned sorted by priority, then creation time
   → For each item:
      a. Mark status=sending and append a local transition
      b. Send request with idempotency and device headers
      c. On an authoritative 2xx acknowledgement: status=acked
      d. On 409: status=conflict and surface for human resolution
      e. On 5xx/network error: status=failed, attempts++, and keep visible for retry

3. Cleanup
   → clearSynced() removes acked ciphertext while retaining audit entries
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
| Redis | Protected authentication and revocation checks fail closed when Redis freshness is unavailable; refresh-token validation also fails closed. Rate limiting is disabled while Redis is unavailable. |
| Kafka/Redpanda | Observations inserted directly into PostgreSQL. WebSocket updates not pushed. |
| Ollama LLM | LLM features fall back to structured-data-only reports. |
| ONNX models | ML inference returns `model_unavailable` response. |
| PMTiles | Frontend falls back to vector tiles. |

The `GET /api/capabilities` endpoint reports runtime availability of each
feature. The frontend can use this to show the user which features are
active. See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) for the full
blocker handling protocol.
