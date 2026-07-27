import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Hypothesis } from '../api/types'
import { LoadingState, ErrorState, EmptyState, StaleState } from '../components/state'

function formatAge(ms: number): string {
  if (ms < 60_000) return `${Math.round(ms / 1000)}s ago`
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m ago`
  return `${Math.round(ms / 3_600_000)}h ago`
}

function statusColor(status: string): string {
  const m: Record<string, string> = {
    active: 'bg-blue-500/10 text-blue-400',
    confirmed: 'bg-green-500/10 text-green-400',
    disproved: 'bg-red-500/10 text-red-400',
    superseded: 'bg-gray-500/10 text-gray-400',
  }
  return m[status?.toLowerCase()] ?? 'bg-gray-500/10 text-gray-400'
}

function evidenceItems(ev: Record<string, unknown> | null): { id: string; note: string }[] {
  if (!ev) return []
  const id = typeof ev.observation_id === 'string' ? ev.observation_id : 'N/A'
  const note = typeof ev.note === 'string' ? ev.note
    : typeof ev.source === 'string' ? `Source: ${ev.source}`
    : JSON.stringify(ev)
  return [{ id, note }]
}

function HypothesisCard({ h }: { h: Hypothesis }) {
  const probPct = Math.round(h.probability * 100)
  const supporting = evidenceItems(h.supporting_evidence)
  const contradicting = evidenceItems(h.contradicting_evidence)
  const age = h.data_age_ms != null ? formatAge(h.data_age_ms) : 'Unknown'

  return (
    <article
      className="rounded-lg border border-gray-700 bg-gray-900/95 p-4 shadow-lg"
      aria-label={`Hypothesis: ${h.claim}`}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <h3 className="text-sm font-bold text-gray-100">{h.claim}</h3>
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${statusColor(h.status)}`} aria-label={`Status: ${h.status}`}>
          {h.status}
        </span>
      </div>

      <div className="mb-3 flex items-center gap-3 text-xs">
        <div className="flex items-center gap-1.5" role="progressbar" aria-valuenow={probPct} aria-valuemin={0} aria-valuemax={100} aria-label={`Probability: ${probPct}%`}>
          <div className="h-1.5 w-16 rounded-full bg-gray-700">
            <div className="h-1.5 rounded-full bg-blue-500" style={{ width: `${probPct}%` }} />
          </div>
          <span className="text-gray-300">{probPct}%</span>
        </div>
        <span className="text-gray-500" aria-label={`Data age: ${age}`}>
          Updated {age}
        </span>
        <span className="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-400" aria-label={`Entity type: ${h.entity_type}`}>
          {h.entity_type}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded bg-gray-800/50 p-2" aria-label="Supporting evidence">
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-green-400">Supporting</div>
          {supporting.length === 0 ? (
            <p className="text-[11px] text-gray-500">None</p>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {supporting.map((e, i) => (
                <li key={i} className="text-[11px] text-gray-300">
                  <span className="font-mono text-blue-400">{e.id}</span>
                  <p className="text-gray-400">{e.note}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="rounded bg-gray-800/50 p-2" aria-label="Contradicting evidence">
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-red-400">Contradicting</div>
          {contradicting.length === 0 ? (
            <p className="text-[11px] text-gray-500">None</p>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {contradicting.map((e, i) => (
                <li key={i} className="text-[11px] text-gray-300">
                  <span className="font-mono text-blue-400">{e.id}</span>
                  <p className="text-gray-400">{e.note}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </article>
  )
}

export default function HypothesesPage() {
  const incidentsQ = useQuery({
    queryKey: ['incidents'],
    queryFn: ({ signal }) => api.getIncidents(signal),
  })
  const incidentId = incidentsQ.data?.incidents?.[0]?.id ?? null

  const hypQ = useQuery({
    queryKey: ['hypotheses', incidentId],
    queryFn: ({ signal }) => api.getHypotheses(incidentId!, signal),
    enabled: !!incidentId,
  })

  if (incidentsQ.isLoading) {
    return <div className="flex h-full items-center justify-center"><LoadingState message="Loading incidents…" /></div>
  }
  if (incidentsQ.isError) {
    return <div className="p-6"><ErrorState message="Failed to load incidents" onRetry={() => incidentsQ.refetch()} /></div>
  }
  if (!incidentId) {
    return <div className="p-6"><EmptyState message="No active incidents" hint="Create an incident to see hypotheses." /></div>
  }

  const hypotheses = hypQ.data?.hypotheses ?? []

  return (
    <div className="flex flex-col gap-4 p-6" aria-label="Hypotheses page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-100">Hypotheses</h1>
          <p className="mt-1 text-sm text-gray-500">Competing explanations with confidence and evidence.</p>
        </div>
        {hypQ.isStale && <StaleState />}
      </div>

      {hypQ.isLoading && <LoadingState message="Loading hypotheses…" />}
      {hypQ.isError && <ErrorState message="Failed to load hypotheses" onRetry={() => hypQ.refetch()} />}
      {hypQ.data && hypotheses.length === 0 && (
        <EmptyState message="No hypotheses" hint="Hypotheses are generated as observations accumulate." />
      )}
      {hypotheses.length > 0 && (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2" role="list" aria-label="Hypothesis list">
          {hypotheses.map(h => (
            <div key={h.id} role="listitem">
              <HypothesisCard h={h} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
