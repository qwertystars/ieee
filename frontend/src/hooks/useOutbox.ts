import { useCallback, useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, request } from '../api/client'
import {
  type OutboxStatus,
  type OutboxPriority,
  addToOutbox,
  getPendingItems,
  getStatusCounts,
  markConflict,
  markFailed,
  markSending,
  markAcked,
} from '../lib/outbox'

let syncInFlight: Promise<void> | null = null

export interface UseOutboxResult {
  pendingCount: number
  failedCount: number
  conflictCount: number
  isOnline: boolean
  addToOutbox: (url: string, method: 'POST' | 'PATCH' | 'PUT' | 'DELETE', body: unknown, priority: OutboxPriority) => Promise<void>
  syncOutbox: () => Promise<void>
}

export function useOutbox(): UseOutboxResult {
  const queryClient = useQueryClient()
  const statusQuery = useQuery<Record<OutboxStatus, number>>({ queryKey: ['outbox-status-counts'], queryFn: getStatusCounts, networkMode: 'always' })
  const [localStatusCounts, setLocalStatusCounts] = useState<Record<OutboxStatus, number> | undefined>(undefined)
  const statusCounts = localStatusCounts ?? statusQuery.data ?? (statusQuery.isError
    ? { queued: 0, sending: 0, acked: 0, failed: 1, conflict: 0 }
    : { queued: 0, sending: 0, acked: 0, failed: 0, conflict: 0 })
  const pendingCount = statusCounts.queued + statusCounts.sending + statusCounts.failed + statusCounts.conflict
  const [isOnline, setIsOnline] = useState(() => typeof navigator === 'undefined' || navigator.onLine)
  const refreshCount = useCallback(async () => {
    setLocalStatusCounts(await getStatusCounts())
    await queryClient.invalidateQueries({ queryKey: ['outbox-status-counts'] })
  }, [queryClient])
  const add = useCallback(async (url: string, method: 'POST' | 'PATCH' | 'PUT' | 'DELETE', body: unknown, priority: OutboxPriority) => {
    await addToOutbox(url, method, body, priority)
    await refreshCount()
  }, [refreshCount])
  const syncOutbox = useCallback(() => {
    if (syncInFlight) return syncInFlight
    const run = async () => {
      if (typeof navigator !== 'undefined' && !navigator.onLine) return
      for (const item of await getPendingItems()) {
        if (!(await markSending(item.id))) continue
        try {
          const acknowledgement = await request<unknown>(item.url, {
            method: item.method,
            body: item.body,
            headers: {
              'Idempotency-Key': item.idempotency_key,
              'X-Device-Id': item.device_id,
              'X-Device-Sequence': String(item.device_sequence),
              'X-Client-Created-At': String(item.created_at),
              'X-Content-Hash': item.content_hash,
              ...(item.reinstalled ? { 'X-Device-Reinstalled': 'true' } : {}),
            },
            _skipOutbox: true,
          })
          await markAcked(item.id, acknowledgement)
        } catch (error) {
          if (error instanceof ApiError && error.status === 409) await markConflict(item.id, error.detail)
          else await markFailed(item.id, error instanceof Error ? error.message : 'sync failed')
        }
      }
      await refreshCount()
    }
    const synchronized: Promise<void> = typeof navigator !== 'undefined' && 'locks' in navigator
      ? navigator.locks.request('resqnet-outbox-sync', () => run()).then(() => undefined)
      : run()
    syncInFlight = synchronized.finally(() => { syncInFlight = null })
    return synchronized
  }, [refreshCount])
  useEffect(() => {
    if (typeof navigator !== 'undefined' && navigator.onLine) globalThis.queueMicrotask(() => void syncOutbox())
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
  return { pendingCount, failedCount: statusCounts.failed, conflictCount: statusCounts.conflict, isOnline, addToOutbox: add, syncOutbox }
}

export function isMutationMethod(method: string): boolean { return method === 'POST' || method === 'PATCH' || method === 'PUT' || method === 'DELETE' }
