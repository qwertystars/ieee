import { useCallback, useEffect, useState } from 'react'
import { ApiError, request } from '../api/client'
import {
  type OutboxPriority,
  addToOutbox,
  getPendingCount,
  getPendingItems,
  markConflict,
  markFailed,
  markSynced,
  recordConflictAudit,
} from '../lib/outbox'

export interface UseOutboxResult {
  pendingCount: number
  isOnline: boolean
  addToOutbox: (
    url: string,
    method: 'POST' | 'PATCH' | 'PUT' | 'DELETE',
    body: unknown,
    priority: OutboxPriority,
  ) => Promise<void>
  syncOutbox: () => Promise<void>
}

const MUTATION_METHODS = new Set(['POST', 'PATCH', 'PUT', 'DELETE'])

export function useOutbox(): UseOutboxResult {
  const [pendingCount, setPendingCount] = useState(0)
  const [isOnline, setIsOnline] = useState(
    typeof navigator !== 'undefined' ? navigator.onLine : true,
  )

  const refreshCount = useCallback(async () => {
    try {
      setPendingCount(await getPendingCount())
    } catch {
      // IndexedDB may be unavailable; keep last known count.
    }
  }, [])

  const add = useCallback(async (
    url: string,
    method: 'POST' | 'PATCH' | 'PUT' | 'DELETE',
    body: unknown,
    priority: OutboxPriority,
  ) => {
    await addToOutbox(url, method, body, priority)
    await refreshCount()
  }, [refreshCount])

  const syncOutbox = useCallback(async () => {
    if (typeof navigator !== 'undefined' && !navigator.onLine) return
    const items = await getPendingItems()
    for (const item of items) {
      try {
        await request(item.url, {
          method: item.method,
          body: item.body,
          headers: { 'Idempotency-Key': item.idempotency_key },
          _skipOutbox: true,
        })
        await markSynced(item.id)
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          if (item.priority < 4) {
            // Non-critical: last-write-wins — resolve in favor of new data.
            await markSynced(item.id, { policy: 'last_write_wins', data: err.detail })
            await recordConflictAudit({
              item_id: item.id, url: item.url, method: item.method,
              policy: 'last_write_wins', conflict_data: err.detail,
            })
          } else {
            // Critical: manual resolution — keep in outbox for human review.
            await markConflict(item.id, err.detail)
            await recordConflictAudit({
              item_id: item.id, url: item.url, method: item.method,
              policy: 'manual', conflict_data: err.detail,
            })
          }
        } else {
          // Network error or other failure — keep for retry.
          await markFailed(item.id, err instanceof Error ? err.message : 'unknown error')
        }
      }
    }
    await refreshCount()
  }, [refreshCount])

  useEffect(() => {
    refreshCount()
    if (typeof navigator !== 'undefined' && navigator.onLine) {
      syncOutbox()
    }
    const goOnline = () => { setIsOnline(true); void syncOutbox() }
    const goOffline = () => setIsOnline(false)
    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
    window.addEventListener('outbox-changed', refreshCount)
    return () => {
      window.removeEventListener('online', goOnline)
      window.removeEventListener('offline', goOffline)
      window.removeEventListener('outbox-changed', refreshCount)
    }
  }, [refreshCount, syncOutbox])

  return { pendingCount, isOnline, addToOutbox: add, syncOutbox }
}

export function isMutationMethod(method: string): boolean {
  return MUTATION_METHODS.has(method)
}
