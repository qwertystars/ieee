import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { FeedHealth, FeedStatus } from '../api/types'
import { useLowBandwidth } from '../context/LowBandwidthContext'
import { LoadingState, ErrorState, EmptyState } from './state'

interface FeedHealthPanelProps {
  incidentId: string
}

function statusStyles(status: FeedStatus): string {
  switch (status) {
    case 'healthy':
      return 'text-green-400 bg-green-500/10 border-green-500/30'
    case 'degraded':
      return 'text-amber-400 bg-amber-500/10 border-amber-500/30'
    case 'down':
      return 'text-red-400 bg-red-500/10 border-red-500/30'
  }
}

function statusIcon(status: FeedStatus): string {
  switch (status) {
    case 'healthy':
      return '●'
    case 'degraded':
      return '▲'
    case 'down':
      return '✕'
  }
}

function formatAge(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3_600) return `${Math.round(seconds / 60)}m`
  if (seconds < 86_400) return `${Math.round(seconds / 3_600)}h`
  return `${Math.round(seconds / 86_400)}d`
}

function FeedRow({ feed }: { feed: FeedHealth }) {
  const ageLabel = feed.status === 'down' && feed.data_age_seconds > 86_400
    ? 'unavailable'
    : `${formatAge(feed.data_age_seconds)} ago`
  const rowLabel = `Feed ${feed.feed_name}, status ${feed.status}, data age ${ageLabel}`
  return (
    <div
      className={`flex items-center justify-between rounded border px-2 py-1.5 text-xs ${statusStyles(feed.status)}`}
      role="listitem"
      aria-label={rowLabel}
    >
      <div className="flex min-w-0 items-center gap-1.5">
        <span aria-hidden="true">{statusIcon(feed.status)}</span>
        <span className="truncate font-mono text-[11px]">{feed.feed_name}</span>
      </div>
      <div className="flex flex-shrink-0 items-center gap-2">
        <span className="text-[10px] uppercase">{feed.status}</span>
        <span className="text-[10px] opacity-80">{ageLabel}</span>
      </div>
    </div>
  )
}

export function FeedHealthPanel({ incidentId }: FeedHealthPanelProps) {
  const { refetchInterval } = useLowBandwidth()
  const healthQ = useQuery({
    queryKey: ['feed-health', incidentId],
    queryFn: ({ signal }) => api.getFeedHealth(incidentId, signal),
    enabled: !!incidentId,
    refetchInterval,
  })

  if (healthQ.isLoading) {
    return (
      <section className="rounded-lg border border-gray-700 bg-gray-900/95 p-3 shadow-lg" aria-label="Feed Health">
        <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-300">Feed Health</h2>
        <LoadingState message="Checking feed health…" />
      </section>
    )
  }
  if (healthQ.isError) {
    return (
      <section className="rounded-lg border border-gray-700 bg-gray-900/95 p-3 shadow-lg" aria-label="Feed Health">
        <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-300">Feed Health</h2>
        <ErrorState message="Feed health unavailable" onRetry={() => healthQ.refetch()} />
      </section>
    )
  }

  const data = healthQ.data
  if (!data) return null

  const feeds = data.feeds
  const isOutage = data.total_feeds > 0 && data.healthy_feeds === 0
  const summaryLabel = isOutage
    ? `Data stale — ${data.total_feeds} feeds down`
    : `${data.healthy_feeds}/${data.total_feeds} feeds healthy`

  return (
    <section
      className="rounded-lg border border-gray-700 bg-gray-900/95 p-3 shadow-lg"
      aria-label="Feed Health"
      role="region"
    >
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-xs font-bold uppercase tracking-wider text-gray-300">Feed Health</h2>
        <span
          role="status"
          aria-live="polite"
          aria-label={summaryLabel}
          className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
            isOutage
              ? 'bg-red-500/10 text-red-400'
              : data.healthy_feeds < data.total_feeds
                ? 'bg-amber-500/10 text-amber-400'
                : 'bg-green-500/10 text-green-400'
          }`}
        >
          {summaryLabel}
        </span>
      </div>

      {isOutage && (
        <div
          className="mb-2 rounded border border-red-500/40 bg-red-500/10 px-2 py-1.5 text-xs text-red-300"
          role="alert"
          aria-label="Data stale or unavailable — all feeds are down"
        >
          Data stale — all feeds are down. Showing last known values.
        </div>
      )}

      {feeds.length === 0 ? (
        <EmptyState message="No feed data" />
      ) : (
        <div className="flex max-h-48 flex-col gap-1 overflow-y-auto" role="list">
          {feeds.slice(0, 12).map(f => <FeedRow key={f.feed_name} feed={f} />)}
          {feeds.length > 12 && (
            <p className="text-center text-[10px] text-gray-500">+{feeds.length - 12} more feeds</p>
          )}
        </div>
      )}
    </section>
  )
}
