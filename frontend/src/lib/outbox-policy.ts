import type { ConflictClass, OutboxPriority } from './outbox'

export function inferPriority(url: string, method: string): OutboxPriority {
  if (url.includes('/imagery') || url.includes('/upload') || url.includes('/media')) return 4
  if (url.includes('/tasks/') && method === 'PATCH') return 3
  if (url.includes('/alerts/') || url.includes('/resources/')) return 3
  if (url.includes('/entities/')) return 2
  return 1
}

export function inferConflictClass(url: string, method: string, body: unknown): ConflictClass {
  const text = `${url} ${method} ${JSON.stringify(body) ?? ''}`.toLowerCase()
  if (text.includes('assignment') || text.includes('assigned_to')) return 'task_assignment'
  if (text.includes('/tasks/') || text.includes('task_state')) return 'task_state'
  if (text.includes('warning') || text.includes('/alerts/')) return 'public_warning'
  if (text.includes('resource') || text.includes('capacity') || text.includes('commitment')) return 'resource_commitment'
  return 'ordinary'
}
