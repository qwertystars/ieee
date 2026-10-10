import { ulid } from './ulid'
import { inferConflictClass } from './outbox-policy'

export { inferConflictClass, inferPriority } from './outbox-policy'

const DB_NAME = 'resqnet-outbox'
const DB_VERSION = 3
const STORE_ITEMS = 'pending'
const STORE_AUDIT = 'audit'
const STORE_META = 'meta'
const MAX_QUEUE_AGE_MS = 24 * 60 * 60 * 1000

export type OutboxPriority = 1 | 2 | 3 | 4
export type OutboxStatus = 'queued' | 'sending' | 'acked' | 'failed' | 'conflict'
export type ConflictResolution = null | 'manual'
export type ConflictClass = 'ordinary' | 'task_state' | 'task_assignment' | 'public_warning' | 'resource_commitment'

export interface OutboxItem {
  readonly id: string; readonly url: string; readonly method: 'POST' | 'PATCH' | 'PUT' | 'DELETE'; readonly body: unknown
  readonly content_hash: string; readonly created_at: number; readonly timestamp: number; readonly priority: OutboxPriority; readonly idempotency_key: string
  readonly device_id: string; readonly device_sequence: number; readonly reinstalled: boolean; readonly status: OutboxStatus
  readonly conflict_class: ConflictClass; readonly conflict_resolution: ConflictResolution; readonly conflict_data?: unknown; readonly server_ack?: unknown
  readonly error?: string; readonly attempts: number; readonly last_attempt?: number
}

export interface ConflictAuditEntry { readonly id: string; readonly ts: number; readonly item_id: string; readonly url: string; readonly method: string; readonly policy: 'manual'; readonly conflict_data: unknown }

export interface OutboxTransition { readonly id: string; readonly ts: number; readonly kind: 'transition' | 'conflict'; readonly item_id: string; readonly from?: OutboxStatus; readonly to?: OutboxStatus; readonly url?: string; readonly method?: string; readonly policy?: 'manual'; readonly conflict_data?: unknown }

type Ciphertext = { readonly key_id: string; readonly iv: ArrayBuffer; readonly data: ArrayBuffer }
type EncryptionKey = Parameters<typeof crypto.subtle.encrypt>[1]
type KeyRecord = { readonly key_id: string; readonly state: 'active' | 'retired' | 'revoked'; readonly key: EncryptionKey }
type DeviceRecord = { readonly key_id: 'device'; readonly device_id: string; readonly sequence: number }
type StoredAuditEntry = Omit<OutboxTransition, 'conflict_data'> & { readonly encrypted_conflict?: Ciphertext; readonly conflict_data?: unknown }
type StoredItem = Omit<OutboxItem, 'body' | 'conflict_data' | 'server_ack'> & {
  readonly encrypted_body: Ciphertext
  readonly encrypted_conflict?: Ciphertext
  readonly encrypted_ack?: Ciphertext
  readonly body?: unknown
  readonly conflict_data?: unknown
  readonly server_ack?: unknown
}

let dbPromise: Promise<IDBDatabase> | null = null

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`
  if (value !== null && typeof value === 'object') return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, entry]) => `${JSON.stringify(key)}:${canonicalJson(entry)}`).join(',')}}`
  return JSON.stringify(value) ?? 'null'
}

async function hash(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalJson(value))
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
}

function openDB(): Promise<IDBDatabase> {
  if (!dbPromise) dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_ITEMS)) {
        const store = db.createObjectStore(STORE_ITEMS, { keyPath: 'id' })
        store.createIndex('status', 'status')
        store.createIndex('priority', 'priority')
      }
      if (!db.objectStoreNames.contains(STORE_AUDIT)) db.createObjectStore(STORE_AUDIT, { keyPath: 'id' })
      if (!db.objectStoreNames.contains(STORE_META)) db.createObjectStore(STORE_META, { keyPath: 'key_id' })
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => { dbPromise = null; reject(request.error) }
  })
  return dbPromise
}

function read<T>(storeName: string, key?: string): Promise<T | undefined> {
  return openDB().then(db => new Promise<T | undefined>((resolve, reject) => {
    const tx = db.transaction(storeName, 'readonly')
    const request = key === undefined ? tx.objectStore(storeName).getAll() : tx.objectStore(storeName).get(key)
    request.onsuccess = () => resolve(request.result as T | undefined)
    request.onerror = () => reject(request.error)
    tx.onerror = () => reject(tx.error)
  }))
}

function write(storeName: string, value: unknown): Promise<void> {
  return openDB().then(db => new Promise<void>((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite')
    tx.objectStore(storeName).put(value)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error)
  }))
}

function remove(storeName: string, key: string): Promise<void> {
  return openDB().then(db => new Promise<void>((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite')
    tx.objectStore(storeName).delete(key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  }))
}

async function keyRecords(): Promise<KeyRecord[]> { return ((await read<KeyRecord[]>(STORE_META)) ?? []).filter(record => 'key' in record) }

async function activeKey(): Promise<KeyRecord> {
  const records = await keyRecords()
  const active = records.find(record => record.state === 'active')
  if (active) return active
  if (records.some(record => record.state === 'revoked')) throw new Error('outbox encryption key revoked')
  const key = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt'])
  const record: KeyRecord = { key_id: ulid(), state: 'active', key: key as EncryptionKey }
  await write(STORE_META, record)
  return record
}

async function encrypt(value: unknown, key: KeyRecord): Promise<Ciphertext> {
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const data = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key.key, new TextEncoder().encode(canonicalJson(value)))
  return { key_id: key.key_id, iv: iv.buffer, data }
}

async function decrypt(ciphertext: Ciphertext): Promise<unknown> {
  const key = (await keyRecords()).find(record => record.key_id === ciphertext.key_id)
  if (!key || key.state === 'revoked') throw new Error('outbox encryption key unavailable')
  const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: ciphertext.iv }, key.key, ciphertext.data)
  return JSON.parse(new globalThis.TextDecoder().decode(plain))
}

async function deviceSequence(): Promise<{ readonly device_id: string; readonly sequence: number; readonly reinstalled: boolean }> {
  const marker = typeof localStorage === 'undefined' ? null : localStorage.getItem('resqnet-device-id')
  const result = await openDB().then(db => new Promise<{ readonly device_id: string; readonly sequence: number; readonly reinstalled: boolean }>((resolve, reject) => {
    const tx = db.transaction(STORE_META, 'readwrite')
    const request = tx.objectStore(STORE_META).get('device')
    let next: { readonly device_id: string; readonly sequence: number; readonly reinstalled: boolean } | undefined
    request.onsuccess = () => {
      const existing = request.result as DeviceRecord | undefined
      const reinstalled = existing !== undefined && marker !== null && marker !== existing.device_id
      const device_id = reinstalled || existing === undefined ? ulid() : existing.device_id
      const sequence = reinstalled || existing === undefined ? 1 : existing.sequence + 1
      next = { device_id, sequence, reinstalled }
      tx.objectStore(STORE_META).put({ key_id: 'device', device_id, sequence })
    }
    request.onerror = () => reject(request.error)
    tx.oncomplete = () => next === undefined ? reject(new Error('device sequence allocation failed')) : resolve(next)
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error)
  }))
  const { device_id } = result
  if (typeof localStorage !== 'undefined') localStorage.setItem('resqnet-device-id', device_id)
  return result
}

async function publicItem(stored: StoredItem): Promise<OutboxItem> {
  const body = stored.encrypted_body ? await decrypt(stored.encrypted_body) : stored.body
  const conflict_data = stored.encrypted_conflict ? await decrypt(stored.encrypted_conflict) : stored.conflict_data
  const server_ack = stored.encrypted_ack ? await decrypt(stored.encrypted_ack) : stored.server_ack
  const created_at = stored.created_at ?? stored.timestamp ?? Date.now()
  const legacyStatus = String(stored.status)
  const status: OutboxStatus = legacyStatus === 'pending' ? 'queued' : legacyStatus === 'syncing' ? 'sending' : legacyStatus === 'synced' ? 'acked' : stored.status
  const legacyResolution = String(stored.conflict_resolution)
  return { ...stored, body, created_at, timestamp: stored.timestamp ?? created_at, device_id: stored.device_id ?? 'legacy-device', device_sequence: stored.device_sequence ?? 1, reinstalled: stored.reinstalled ?? false, status, conflict_class: stored.conflict_class ?? 'ordinary', conflict_resolution: legacyResolution === 'last_write_wins' ? 'manual' : stored.conflict_resolution, ...(conflict_data === undefined ? {} : { conflict_data }), ...(server_ack === undefined ? {} : { server_ack }) }
}

async function allItems(): Promise<OutboxItem[]> {
  const stored = (await read<StoredItem[]>(STORE_ITEMS)) ?? []
  return Promise.all(stored.map(publicItem))
}

async function audit(entry: Omit<OutboxTransition, 'id' | 'ts'>): Promise<void> {
  const record = await auditRecord(entry)
  await write(STORE_AUDIT, record)
}

async function auditRecord(entry: Omit<OutboxTransition, 'id' | 'ts'>): Promise<StoredAuditEntry> {
  if (entry.conflict_data === undefined) return { ...entry, id: ulid(), ts: Date.now() }
  const encrypted_conflict = await encrypt(entry.conflict_data, await activeKey())
  const record: StoredAuditEntry = { ...entry, encrypted_conflict, id: ulid(), ts: Date.now() }
  delete (record as { conflict_data?: unknown }).conflict_data
  return record
}

async function writeItemAndAudits(stored: StoredItem, entries: readonly StoredAuditEntry[]): Promise<void> {
  await openDB().then(db => new Promise<void>((resolve, reject) => {
    const tx = db.transaction([STORE_ITEMS, STORE_AUDIT], 'readwrite')
    tx.objectStore(STORE_ITEMS).put(stored)
    for (const entry of entries) tx.objectStore(STORE_AUDIT).put(entry)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error)
  }))
}

async function transition(id: string, patch: Partial<OutboxItem>, expected: readonly OutboxStatus[] = []): Promise<OutboxItem | undefined> {
  const current = (await allItems()).find(item => item.id === id)
  if (!current) return undefined
  if (expected.length > 0 && !expected.includes(current.status)) return undefined
  const next = { ...current, ...patch }
  const key = await activeKey()
  const encrypted_body = await encrypt(next.body, key)
  const encrypted_conflict = next.conflict_data === undefined ? undefined : await encrypt(next.conflict_data, key)
  const encrypted_ack = next.server_ack === undefined ? undefined : await encrypt(next.server_ack, key)
  const stored: StoredItem = { ...next, encrypted_body, ...(encrypted_conflict ? { encrypted_conflict } : {}), ...(encrypted_ack ? { encrypted_ack } : {}) }
  delete (stored as { body?: unknown }).body
  delete (stored as { conflict_data?: unknown }).conflict_data
  delete (stored as { server_ack?: unknown }).server_ack
  const entries: StoredAuditEntry[] = []
  if (current.status !== next.status) entries.push(await auditRecord({ kind: 'transition', item_id: id, from: current.status, to: next.status, url: next.url, method: next.method }))
  if (patch.conflict_data !== undefined) entries.push(await auditRecord({ kind: 'conflict', item_id: id, url: next.url, method: next.method, policy: 'manual', conflict_data: patch.conflict_data }))
  await writeItemAndAudits(stored, entries)
  return next
}

export async function addToOutbox(url: string, method: OutboxItem['method'], body: unknown, priority: OutboxPriority): Promise<OutboxItem> {
  const id = ulid()
  const idempotency_key = ulid()
  const content_hash = await hash(body)
  const device = await deviceSequence()
  const created_at = Date.now()
  const item: OutboxItem = { id, url, method, body, content_hash, created_at, timestamp: created_at, priority, idempotency_key, device_id: device.device_id, device_sequence: device.sequence, reinstalled: device.reinstalled, status: 'queued', conflict_class: inferConflictClass(url, method, body), conflict_resolution: null, attempts: 0 }
  const key = await activeKey()
  const encrypted_body = await encrypt(item.body, key)
  const stored: StoredItem = { ...item, encrypted_body }
  delete (stored as { body?: unknown }).body
  await writeItemAndAudits(stored, [await auditRecord({ kind: 'transition', item_id: item.id, to: 'queued', url, method })])
  return item
}

export async function recoverSendingItems(): Promise<number> {
  let recovered = 0
  for (const item of await allItems()) if (item.status === 'sending') { await transition(item.id, { status: 'failed', error: 'recovered_after_restart' }); recovered++ }
  return recovered
}

export async function getPendingItems(): Promise<OutboxItem[]> {
  await recoverSendingItems()
  const cutoff = Date.now() - MAX_QUEUE_AGE_MS
  for (const item of await allItems()) if (item.status !== 'acked' && item.status !== 'conflict' && item.created_at < cutoff) await transition(item.id, { status: 'failed', error: 'queue_expired' })
  return (await allItems()).filter(item => (item.status === 'queued' || item.status === 'failed') && item.error !== 'queue_expired').sort((a, b) => a.priority - b.priority || a.created_at - b.created_at)
}
export async function getAllOutboxItems(): Promise<OutboxItem[]> { return allItems() }

export async function markSending(id: string): Promise<boolean> { return (await transition(id, { status: 'sending', last_attempt: Date.now() }, ['queued', 'failed']))?.status === 'sending' }
export async function markAcked(id: string, server_ack?: unknown): Promise<void> { await transition(id, { status: 'acked', server_ack, error: undefined, last_attempt: Date.now() }, ['queued', 'sending', 'failed']) }
export async function markSynced(id: string): Promise<void> { return markAcked(id) }
export async function markFailed(id: string, error: string): Promise<void> {
  const item = (await allItems()).find(candidate => candidate.id === id)
  if (item) await transition(id, { status: 'failed', error, attempts: item.attempts + 1, last_attempt: Date.now() }, ['queued', 'sending', 'failed'])
}
export async function markConflict(id: string, conflictData: unknown): Promise<void> {
  await transition(id, { status: 'conflict', conflict_resolution: 'manual', conflict_data: conflictData, error: 'human_resolution_required', last_attempt: Date.now() }, ['queued', 'sending', 'failed'])
}
export async function getPendingCount(): Promise<number> { return (await allItems()).filter(item => item.status !== 'acked' && item.error !== 'queue_expired').length }
export async function getStatusCounts(): Promise<Record<OutboxStatus, number>> {
  const counts: Record<OutboxStatus, number> = { queued: 0, sending: 0, acked: 0, failed: 0, conflict: 0 }
  for (const item of await allItems()) counts[item.status]++
  return counts
}
export async function clearSynced(): Promise<void> { for (const item of await allItems()) if (item.status === 'acked') await remove(STORE_ITEMS, item.id) }
export async function recordConflictAudit(entry: Omit<ConflictAuditEntry, 'id' | 'ts'>): Promise<void> { await audit({ kind: 'conflict', ...entry }) }
async function publicAudit(entry: StoredAuditEntry): Promise<OutboxTransition> {
  const conflict_data = entry.encrypted_conflict ? await decrypt(entry.encrypted_conflict) : entry.conflict_data
  return conflict_data === undefined ? entry : { ...entry, conflict_data }
}
export async function getConflictAudit(): Promise<ConflictAuditEntry[]> {
  const entries = await Promise.all((await read<StoredAuditEntry[]>(STORE_AUDIT) ?? []).filter(entry => entry.kind === 'conflict').map(publicAudit))
  return entries.sort((a, b) => a.ts - b.ts) as ConflictAuditEntry[]
}
export async function getOutboxAudit(): Promise<OutboxTransition[]> {
  const entries = await Promise.all((await read<StoredAuditEntry[]>(STORE_AUDIT) ?? []).map(publicAudit))
  return entries.sort((a, b) => a.ts - b.ts)
}
export async function rotateOutboxKey(): Promise<void> {
  const records = await keyRecords()
  const key = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt'])
  for (const record of records) if (record.state === 'active') await write(STORE_META, { ...record, state: 'retired' })
  await write(STORE_META, { key_id: ulid(), state: 'active', key: key as EncryptionKey })
}
export async function revokeOutboxKey(): Promise<void> { for (const record of await keyRecords()) if (record.state !== 'revoked') await write(STORE_META, { ...record, state: 'revoked' }) }
export async function getOutboxKeyStatus(): Promise<'active' | 'retired' | 'revoked'> { const records = await keyRecords(); return records.some(r => r.state === 'active') ? 'active' : records.some(r => r.state === 'retired') ? 'retired' : 'revoked' }

export function isMutationMethod(method: string): boolean { return method === 'POST' || method === 'PATCH' || method === 'PUT' || method === 'DELETE' }
