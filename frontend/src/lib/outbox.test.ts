// Unit tests for the IndexedDB outbox — add, sync, conflict resolution,
// priority inference, and audit logging. Uses fake-indexeddb (loaded in
// src/test/setup.ts). Stores are cleared between tests via direct IndexedDB
// access; the singleton dbPromise in outbox.ts stays open across tests.
import { beforeEach, describe, expect, it } from 'vitest'
import {
  addToOutbox,
  clearSynced,
  getConflictAudit,
  getAllOutboxItems,
  getOutboxAudit,
  getOutboxKeyStatus,
  getPendingCount,
  getPendingItems,
  inferPriority,
  markConflict,
  markFailed,
  markAcked,
  markSending,
  markSynced,
  recoverSendingItems,
  recordConflictAudit,
  revokeOutboxKey,
  rotateOutboxKey,
  type OutboxItem,
} from './outbox'

const DB_NAME = 'resqnet-outbox'

// Reads the raw 'pending' store directly — the public API intentionally
// excludes synced/conflict items, so we must bypass it to verify deletion
// semantics in clearSynced tests.
async function readAllPending(): Promise<OutboxItem[]> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME)
    req.onerror = () => reject(req.error)
    req.onsuccess = () => {
      const db = req.result
      const tx = db.transaction('pending', 'readonly')
      const store = tx.objectStore('pending')
      const getAll = store.getAll()
      getAll.onsuccess = () => resolve((getAll.result ?? []) as OutboxItem[])
      getAll.onerror = () => reject(getAll.error)
      tx.oncomplete = () => db.close()
    }
  })
}

// Clears both stores via a second connection. The outbox module's singleton
// dbPromise keeps its own connection open; fake-indexeddb supports multiple
// connections to the same database. If the DB was created without stores
// (e.g. by a previous open without onupgradeneeded), delete it so the outbox
// module can recreate it with the correct schema on next access.
async function clearStores() {
  return new Promise<void>((resolve, reject) => {
    const req = indexedDB.open(DB_NAME)
    req.onerror = () => reject(req.error)
    req.onsuccess = () => {
      const db = req.result
      const storeNames = Array.from(db.objectStoreNames)
      if (!storeNames.includes('pending') || !storeNames.includes('audit')) {
        db.close()
        const delReq = indexedDB.deleteDatabase(DB_NAME)
        delReq.onsuccess = () => resolve()
        delReq.onerror = () => resolve()
        delReq.onblocked = () => resolve()
        return
      }
      const tx = db.transaction(['pending', 'audit', 'meta'], 'readwrite')
      tx.objectStore('pending').clear()
      tx.objectStore('audit').clear()
      tx.objectStore('meta').clear()
      tx.oncomplete = () => { db.close(); resolve() }
      tx.onerror = () => { db.close(); reject(tx.error) }
    }
  })
}

beforeEach(async () => {
  await clearStores()
})

describe('addToOutbox', () => {
  it('persists an item with a content hash, ULID id, and idempotency key', async () => {
    const item = await addToOutbox('/api/tasks/t1', 'PATCH', { status: 'done' }, 3)

    expect(item.id).toMatch(/^[0-9A-HJKMNP-TV-Z]{26}$/)
    expect(item.idempotency_key).toMatch(/^[0-9A-HJKMNP-TV-Z]{26}$/)
    expect(item.id).not.toBe(item.idempotency_key)
    expect(item.content_hash).toMatch(/^[0-9a-f]{64}$/)
    expect(item.status).toBe('queued')
    expect(item.device_sequence).toBeGreaterThan(0)
    expect(item.body).toEqual({ status: 'done' })
    expect(item.attempts).toBe(0)
    expect(item.conflict_resolution).toBeNull()

    const pending = await getPendingItems()
    expect(pending).toHaveLength(1)
    expect(pending[0].id).toBe(item.id)
  })

  it('produces a deterministic content hash for identical bodies', async () => {
    const a = await addToOutbox('/api/x', 'POST', { x: 1 }, 1)
    const b = await addToOutbox('/api/x', 'POST', { x: 1 }, 1)
    expect(a.content_hash).toBe(b.content_hash)
  })

  it('produces different hashes for different bodies', async () => {
    const a = await addToOutbox('/api/x', 'POST', { x: 1 }, 1)
    const b = await addToOutbox('/api/x', 'POST', { x: 2 }, 1)
    expect(a.content_hash).not.toBe(b.content_hash)
  })
})

describe('getPendingItems — priority ordering', () => {
  it('returns items sorted by priority (1=highest) then timestamp', async () => {
    await addToOutbox('/api/imagery', 'POST', { img: 1 }, 4)
    await addToOutbox('/api/tasks/t1', 'PATCH', { status: 'x' }, 3)
    await addToOutbox('/api/entities/roads/r1', 'PATCH', { status: 'open' }, 2)
    await addToOutbox('/api/observations', 'POST', { text: 'help' }, 1)

    const pending = await getPendingItems()
    expect(pending.map(p => p.priority)).toEqual([1, 2, 3, 4])
  })
})

describe('acknowledgements', () => {
  it('moves an item to acked status, excluding it from the pending count', async () => {
    const item = await addToOutbox('/api/x', 'POST', { a: 1 }, 1)
    await markSynced(item.id)
    expect(await getPendingCount()).toBe(0)
  })

  it('encrypts and returns the server acknowledgement', async () => {
    const item = await addToOutbox('/api/x', 'POST', { a: 1 }, 1)
    await markAcked(item.id, { server: 'wins' })

    const remaining = await getAllOutboxItems()
    expect(remaining).toHaveLength(1)
    expect(remaining[0].status).toBe('acked')
    expect(remaining[0].server_ack).toEqual({ server: 'wins' })
  })
})

describe('markFailed', () => {
  it('increments attempts and stores the error message', async () => {
    const item = await addToOutbox('/api/x', 'POST', { a: 1 }, 1)
    await markFailed(item.id, 'timeout')

    const pending = await getPendingItems()
    expect(pending).toHaveLength(1)
    expect(pending[0].status).toBe('failed')
    expect(pending[0].attempts).toBe(1)
    expect(pending[0].error).toBe('timeout')
    expect(pending[0].last_attempt).toBeGreaterThan(0)
  })

  it('increments attempts on repeated failures', async () => {
    const item = await addToOutbox('/api/x', 'POST', { a: 1 }, 1)
    await markFailed(item.id, 'timeout')
    await markFailed(item.id, 'timeout')
    await markFailed(item.id, 'server error')

    const pending = await getPendingItems()
    expect(pending[0].attempts).toBe(3)
    expect(pending[0].error).toBe('server error')
  })
})

describe('markConflict', () => {
  it('sets status to conflict with manual resolution and stores conflict data', async () => {
    const item = await addToOutbox('/api/x', 'POST', { a: 1 }, 1)
    await markConflict(item.id, { server_value: 42, client_value: 41 })

    expect(await getPendingCount()).toBe(1)

    const remaining = await getAllOutboxItems()
    expect(remaining).toHaveLength(1)
    expect(remaining[0].status).toBe('conflict')
    expect(remaining[0].conflict_resolution).toBe('manual')
    expect(remaining[0].conflict_data).toEqual({ server_value: 42, client_value: 41 })
  })
})

describe('clearSynced', () => {
  it('removes synced items without conflict resolution', async () => {
    const a = await addToOutbox('/api/x', 'POST', { a: 1 }, 1)
    const b = await addToOutbox('/api/y', 'POST', { b: 2 }, 1)
    await markSynced(a.id)

    await clearSynced()

    const remaining = await readAllPending()
    expect(remaining).toHaveLength(1)
    expect(remaining[0].id).toBe(b.id)
    expect(remaining[0].status).toBe('queued')
  })

  it('removes acknowledged items while retaining append-only audit entries', async () => {
    const plain = await addToOutbox('/api/x', 'POST', { a: 1 }, 1)
    const withConflict = await addToOutbox('/api/y', 'POST', { b: 2 }, 1)
    await markSynced(plain.id)
    await markAcked(withConflict.id, { s: 1 })

    await clearSynced()

    const remaining = await readAllPending()
    expect(remaining).toHaveLength(0)
  })
})

describe('recordConflictAudit + getConflictAudit', () => {
  it('records conflict audit entries and returns them sorted by timestamp', async () => {
    await recordConflictAudit({
      item_id: 'item-1',
      url: '/api/x',
      method: 'POST',
      policy: 'manual',
      conflict_data: { server: 42 },
    })
    await recordConflictAudit({
      item_id: 'item-2',
      url: '/api/y',
      method: 'PATCH',
      policy: 'manual',
      conflict_data: { server: 99 },
    })

    const audit = await getConflictAudit()
    expect(audit).toHaveLength(2)
    expect(audit[0].item_id).toBe('item-1')
    expect(audit[1].item_id).toBe('item-2')
    expect(audit[0].policy).toBe('manual')
    expect(audit[1].policy).toBe('manual')
    expect(audit[0].id).toMatch(/^[0-9A-HJKMNP-TV-Z]{26}$/)
    expect(audit[0].ts).toBeGreaterThan(0)
  })
})

describe('inferPriority', () => {
  it('assigns priority 4 to imagery/upload/media URLs', () => {
    expect(inferPriority('/api/imagery', 'POST')).toBe(4)
    expect(inferPriority('/api/upload', 'POST')).toBe(4)
    expect(inferPriority('/api/media', 'POST')).toBe(4)
  })

  it('assigns priority 3 to task status PATCHes', () => {
    expect(inferPriority('/api/tasks/task-123', 'PATCH')).toBe(3)
  })

  it('assigns priority 2 to entity updates', () => {
    expect(inferPriority('/api/incidents/inc-1/entities/roads/r1', 'PATCH')).toBe(2)
  })

  it('assigns priority 1 (default) to all other mutations', () => {
    expect(inferPriority('/api/observations', 'POST')).toBe(1)
    expect(inferPriority('/api/incidents', 'POST')).toBe(1)
  })

  it('does NOT classify task creation (POST) as priority 3 — only PATCHes', () => {
    expect(inferPriority('/api/tasks', 'POST')).toBe(1)
  })
})

describe('getPendingCount', () => {
    it('counts queued, sending, failed, and conflict items but excludes acked', async () => {
    const a = await addToOutbox('/api/a', 'POST', {}, 1)
    const b = await addToOutbox('/api/b', 'POST', {}, 1)
    const c = await addToOutbox('/api/c', 'POST', {}, 1)
    await addToOutbox('/api/d', 'POST', {}, 1)

    await markSynced(a.id)
    await markFailed(b.id, 'err')
    await markConflict(c.id, { x: 1 })

    expect(await getPendingCount()).toBe(3)
  })
})

describe('ULID monotonicity', () => {
  it('generates strictly increasing IDs within the same millisecond', async () => {
    const items = await Promise.all(
      Array.from({ length: 20 }, () => addToOutbox('/api/x', 'POST', { i: 1 }, 1)),
    )
    const ids = items.map(i => i.id)
    const sorted = [...ids].sort()
    expect(ids).toEqual(sorted)
    expect(new Set(ids).size).toBe(20)
  })
})

describe('recovery and key lifecycle', () => {
  it('recovers a durable sending item to visible failed state after restart', async () => {
    const item = await addToOutbox('/api/recovery', 'POST', { value: 1 }, 1)
    await markSending(item.id)
    expect(await recoverSendingItems()).toBe(1)
    const recovered = (await getAllOutboxItems())[0]
    expect(recovered.status).toBe('failed')
    expect(recovered.error).toBe('recovered_after_restart')
  })

  it('rotates the encryption key without losing queued data', async () => {
    await addToOutbox('/api/rotate', 'POST', { sensitive: true }, 1)
    await rotateOutboxKey()
    expect(await getOutboxKeyStatus()).toBe('active')
    expect((await getAllOutboxItems())[0].body).toEqual({ sensitive: true })
  })

  it('fails closed after local key revocation', async () => {
    await addToOutbox('/api/revoke', 'POST', { sensitive: true }, 1)
    await revokeOutboxKey()
    expect(await getOutboxKeyStatus()).toBe('revoked')
    await expect(addToOutbox('/api/revoke', 'POST', { next: true }, 1)).rejects.toThrow('encryption key revoked')
  })

  it('records every durable lifecycle transition in append-only audit state', async () => {
    const item = await addToOutbox('/api/audit', 'POST', { value: 1 }, 1)
    await markSending(item.id)
    await markAcked(item.id, { accepted: true })
    const transitions = (await getOutboxAudit()).filter(entry => entry.item_id === item.id && entry.kind === 'transition')
    expect(transitions.map(entry => entry.to)).toEqual(['queued', 'sending', 'acked'])
  })

  it('allocates unique monotonic device sequences for concurrent enqueue calls', async () => {
    const items = await Promise.all(
      Array.from({ length: 8 }, (_, index) => addToOutbox('/api/sequence', 'POST', { index }, 1)),
    )

    expect(new Set(items.map(item => item.device_sequence)).size).toBe(8)
    expect(items.map(item => item.device_sequence).sort((a, b) => a - b)).toEqual(
      Array.from({ length: 8 }, (_, index) => index + 1),
    )
  })

  it('does not return expired items for replay', async () => {
    const item = await addToOutbox('/api/expired', 'POST', { safety: true }, 1)
    const request = indexedDB.open(DB_NAME)
    await new Promise<void>((resolve, reject) => {
      request.onerror = () => reject(request.error)
      request.onsuccess = () => {
        const db = request.result
        const tx = db.transaction('pending', 'readwrite')
        const get = tx.objectStore('pending').get(item.id)
        get.onsuccess = () => {
          const stored = get.result as OutboxItem
          tx.objectStore('pending').put({ ...stored, created_at: Date.now() - 25 * 60 * 60 * 1000 })
        }
        tx.oncomplete = () => { db.close(); resolve() }
        tx.onerror = () => reject(tx.error)
      }
    })

    const pending = await getPendingItems()
    expect(pending).toHaveLength(0)
    expect((await getAllOutboxItems())[0].error).toBe('queue_expired')
  })

  it('revokes retired keys as well as the active key', async () => {
    await addToOutbox('/api/key', 'POST', { value: 1 }, 1)
    await rotateOutboxKey()
    await revokeOutboxKey()

    expect(await getOutboxKeyStatus()).toBe('revoked')
  })
})
