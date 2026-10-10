import { useClock } from '../../hooks/useClock'

interface StaleStateProps {
  message?: string
  lastUpdated?: number
}

function formatAge(ms: number): string {
  if (ms < 60_000) return `${Math.round(ms / 1000)}s ago`
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m ago`
  return `${Math.round(ms / 3_600_000)}h ago`
}

export function StaleState({ message, lastUpdated }: StaleStateProps) {
  const now = useClock()
  const age = lastUpdated ? formatAge(now - lastUpdated) : null
  const label = message ?? (age ? `Data may be stale (last updated ${age})` : 'Data may be stale')
  return (
    <div
      className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/10 px-2.5 py-1 text-xs text-amber-400"
      role="status"
      aria-live="polite"
      aria-label={label}
    >
      <svg
        className="h-3.5 w-3.5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
      <span>{label}</span>
    </div>
  )
}
