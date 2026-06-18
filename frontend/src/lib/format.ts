// Formatting helpers

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

export function formatRelative(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const diffMin = Math.floor(diffMs / 60_000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  return `${Math.floor(diffHr / 24)}d ago`
}

export function formatConfidence(score: number): string {
  return `${Math.round(score * 100)}%`
}

export function formatCapacity(current: number, total: number): string {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0
  return `${current}/${total} (${pct}%)`
}

export const PRIORITY_COLORS: Record<string, string> = {
  critical: 'text-red-600 bg-red-50 border-red-200',
  high: 'text-orange-600 bg-orange-50 border-orange-200',
  medium: 'text-yellow-600 bg-yellow-50 border-yellow-200',
  low: 'text-green-600 bg-green-50 border-green-200',
  monitoring: 'text-blue-600 bg-blue-50 border-blue-200',
  unknown: 'text-gray-600 bg-gray-50 border-gray-200',
}

export const URGENCY_COLORS: Record<string, string> = {
  critical: 'text-red-700 bg-red-100',
  high: 'text-orange-700 bg-orange-100',
  medium: 'text-yellow-700 bg-yellow-100',
  low: 'text-green-700 bg-green-100',
}
