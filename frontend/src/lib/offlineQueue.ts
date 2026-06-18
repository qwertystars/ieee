// Offline submission queue — persists to localStorage, flushes on reconnect

import type { IncidentReportCreate } from '../types'

export interface QueuedReport {
  id: string
  eventId: string
  data: IncidentReportCreate
  timestamp: string
}

const QUEUE_KEY = 'field_offline_queue'

export function getQueue(): QueuedReport[] {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) ?? '[]') as QueuedReport[]
  } catch {
    return []
  }
}

export function enqueueReport(eventId: string, data: IncidentReportCreate): QueuedReport {
  const item: QueuedReport = {
    id: crypto.randomUUID(),
    eventId,
    data,
    timestamp: new Date().toISOString(),
  }
  const queue = getQueue()
  queue.push(item)
  localStorage.setItem(QUEUE_KEY, JSON.stringify(queue))
  return item
}

export function removeFromQueue(id: string): void {
  const updated = getQueue().filter((item) => item.id !== id)
  localStorage.setItem(QUEUE_KEY, JSON.stringify(updated))
}

export async function flushQueue(
  submitFn: (eventId: string, data: IncidentReportCreate) => Promise<unknown>,
): Promise<{ succeeded: number; failed: number }> {
  const queue = getQueue()
  let succeeded = 0
  let failed = 0
  for (const item of queue) {
    try {
      await submitFn(item.eventId, item.data)
      removeFromQueue(item.id)
      succeeded++
    } catch {
      failed++
    }
  }
  return { succeeded, failed }
}
