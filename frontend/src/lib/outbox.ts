// IndexedDB outbox for offline mutations with conflict-aware replay.
// Sync order on reconnect: text(1) > coordinates(2) > task_state(3) > imagery(4).
// All items are resolved — no silent discard. Conflicts are audited.

const DB_NAME = 'resqnet-outbox'
const DB_VERSION = 1
const STORE_PENDING = 'pending'
const STORE_AUDIT = 'audit'

export type OutboxPriority = 1 | 2 | 3 | 4
export type OutboxStatus = 'pending' | 'syncing' | 'synced' | 'failed' | 'conflict'
export type ConflictResolution = null | 'last_write_wins' | 'manual'

export interface OutboxItem {
  id: string
  url: string
  method: 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body: unknown
  content_hash: string
  timestamp: number
  priority: OutboxPriority
  idempotency_key: string
  status: OutboxStatus
  conflict_resolution: ConflictResolution
  conflict_data?: unknown
  error?: string
  attempts: number
  last_attempt?: number
}

export interface ConflictAuditEntry {
  id: string
  ts: number
  item_id: string
  url: string
  method: string
  policy: 'last_write_wins' | 'manual'
  conflict_data: unknown
}

// --- ULID (26-char Crockford base32, monotonic within process) ---------------

const CROCK32 = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
let lastTs = 0
let lastRand: Uint8Array = new Uint8Array(10)

function encodeBase32(big: bigint, len: number): string {
  let out = ''
  for (let i = 0; i < len; i++) {
    out = CROCK32[Number(big & 31n)] + out
    big >>= 5n
  }
  return out
}

function ulid(): string {
  const ts = Date.now()
  let rand: Uint8Array
  if (ts === lastTs) {
    rand = new Uint8Array(lastRand)
    for (let i = 9; i >= 0; i--) {
      if (rand[i] === 255) { rand[i] = 0; continue }
      rand[i]++
      break
    }
  } else {
    rand = new Uint8Array(10)
    crypto.getRandomValues(rand)
  }
  lastTs = ts
  lastRand = rand
  let big = 0n
  for (const b of rand) big = (big << 8n) | BigInt(b)
  return encodeBase32(BigInt(ts), 10) + encodeBase32(big, 16)
}

async function sha256(text: string): Promise<string> {
  const data = new TextEncoder().encode(text)
  const buf = await crypto.subtle.digest('SHA-256', data)
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')
}

// --- IndexedDB (singleton connection) ---------------------------------------

let dbPromise: Promise<IDBDatabase> | null = null

function openDB(): Promise<IDBDatabase> {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION)
      req.onupgradeneeded = () => {
        const db = req.result
        if (!db.objectStoreNames.contains(STORE_PENDING)) {
          const s = db.createObjectStore(STORE_PENDING, { keyPath: 'id' })
          s.createIndex('status', 'status', { unique: false })
          s.createIndex('priority', 'priority', { unique: false })
        }
        if (!db.objectStoreNames.contains(STORE_AUDIT)) {
          db.createObjectStore(STORE_AUDIT, { keyPath: 'id' })
        }
      }
      req.onsuccess = () => resolve(req.result)
      req.onerror = () => { dbPromise = null; reject(req.error) }
    })
  }
  return dbPromise
}

function withTx(
  store: string,
  mode: IDBTransactionMode,
  fn: (s: IDBObjectStore) => void,
): Promise<void> {
  return openDB().then(db => new Promise<void>((resolve, reject) => {
    const t = db.transaction(store, mode)
    fn(t.objectStore(store))
    t.oncomplete = () => resolve()
    t.onerror = () => reject(t.error)
    t.onabort = () => reject(t.error)
  }))
}

function withTxResult<T>(
  store: string,
  mode: IDBTransactionMode,
  fn: (s: IDBObjectStore) => IDBRequest,
): Promise<T> {
  return openDB().then(db => new Promise<T>((resolve, reject) => {
    const t = db.transaction(store, mode)
    const req = fn(t.objectStore(store))
    req.onsuccess = () => resolve(req.result as T)
    req.onerror = () => reject(req.error)
    t.onerror = () => reject(t.error)
    t.onabort = () => reject(t.error)
  }))
}

async function getAllItems(): Promise<OutboxItem[]> {
  return withTxResult<OutboxItem[]>(STORE_PENDING, 'readonly', s => s.getAll())
    .then(r => r ?? [])
}

async function updateItem(id: string, patch: Partial<OutboxItem>): Promise<void> {
  await withTx(STORE_PENDING, 'readwrite', s => {
    const getReq = s.get(id)
    getReq.onsuccess = () => {
      const item = getReq.result as OutboxItem | undefined
      if (!item) return
      Object.assign(item, patch)
      s.put(item)
    }
  })
}

// --- Public API -------------------------------------------------------------

export async function addToOutbox(
  url: string,
  method: OutboxItem['method'],
  body: unknown,
  priority: OutboxPriority,
): Promise<OutboxItem> {
  // Generate ULIDs before any await: Promise.all preserves call order, but
  // await sha256 resolves in completion order, which would break monotonicity.
  const id = ulid()
  const idempotency_key = ulid()
  const bodyStr = body === undefined ? '' : JSON.stringify(body)
  const content_hash = await sha256(bodyStr)
  const item: OutboxItem = {
    id,
    url, method, body,
    content_hash,
    timestamp: Date.now(),
    priority,
    idempotency_key,
    status: 'pending',
    conflict_resolution: null,
    attempts: 0,
  }
  await withTx(STORE_PENDING, 'readwrite', s => s.add(item))
  return item
}

export async function getPendingItems(): Promise<OutboxItem[]> {
  const all = await getAllItems()
  return all
    .filter(i => i.status === 'pending' || i.status === 'failed' || i.status === 'syncing')
    .sort((a, b) => a.priority - b.priority || a.timestamp - b.timestamp)
}

export async function markSynced(
  id: string,
  resolution?: { policy: 'last_write_wins'; data: unknown },
): Promise<void> {
  const patch: Partial<OutboxItem> = { status: 'synced', last_attempt: Date.now() }
  if (resolution) {
    patch.conflict_resolution = resolution.policy
    patch.conflict_data = resolution.data
  }
  await updateItem(id, patch)
}

export async function markFailed(id: string, error: string): Promise<void> {
  const item = await withTxResult<OutboxItem | undefined>(STORE_PENDING, 'readonly', s => s.get(id))
  if (!item) return
  await updateItem(id, {
    status: 'failed',
    error,
    attempts: item.attempts + 1,
    last_attempt: Date.now(),
  })
}

export async function markConflict(id: string, conflictData: unknown): Promise<void> {
  await updateItem(id, {
    status: 'conflict',
    conflict_resolution: 'manual',
    conflict_data: conflictData,
    last_attempt: Date.now(),
  })
}

export async function getPendingCount(): Promise<number> {
  const all = await getAllItems()
  return all.filter(i => i.status !== 'synced' && i.status !== 'conflict').length
}

export async function clearSynced(): Promise<void> {
  const all = await getAllItems()
  const toDelete = all
    .filter(i => i.status === 'synced' && !i.conflict_resolution)
    .map(i => i.id)
  if (toDelete.length === 0) return
  await withTx(STORE_PENDING, 'readwrite', s => {
    for (const id of toDelete) s.delete(id)
  })
}

export async function recordConflictAudit(
  entry: Omit<ConflictAuditEntry, 'id' | 'ts'>,
): Promise<void> {
  const audit: ConflictAuditEntry = { ...entry, id: ulid(), ts: Date.now() }
  await withTx(STORE_AUDIT, 'readwrite', s => s.add(audit))
}

export async function getConflictAudit(): Promise<ConflictAuditEntry[]> {
  return withTxResult<ConflictAuditEntry[]>(STORE_AUDIT, 'readonly', s => s.getAll())
    .then(r => (r ?? []).sort((a, b) => a.ts - b.ts))
}

export function inferPriority(url: string, method: string): OutboxPriority {
  if (url.includes('/imagery') || url.includes('/upload') || url.includes('/media')) return 4
  if (/\/tasks\/[^/]+$/.test(url) && method === 'PATCH') return 3
  if (url.includes('/entities/')) return 2
  return 1
}
