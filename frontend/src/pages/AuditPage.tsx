import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { AuditLog } from '../api/types'
import { LoadingState, ErrorState, EmptyState, StaleState, OfflineState } from '../components/state'

function fmtTime(ms: number): string {
  if (!ms) return '—'
  return new Date(ms).toISOString().slice(0, 19) + 'Z'
}

function shortHash(h: string): string {
  if (!h) return '—'
  return h.length > 12 ? `${h.slice(0, 8)}…${h.slice(-4)}` : h
}

function actionColor(action: string): string {
  if (action.includes('approve')) return 'bg-green-500/10 text-green-400'
  if (action.includes('dismiss')) return 'bg-red-500/10 text-red-400'
  if (action.includes('create')) return 'bg-blue-500/10 text-blue-400'
  if (action.includes('update')) return 'bg-amber-500/10 text-amber-400'
  return 'bg-gray-500/10 text-gray-400'
}

function AuditRow({ log, index }: { log: AuditLog; index: number }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="rounded border border-gray-700 bg-gray-900/95 p-2 text-xs">
      <button
        onClick={() => setExpanded(e => !e)}
        className="flex w-full items-center justify-between gap-2 text-left focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
        aria-label={`Audit entry ${index + 1}: ${log.action} by ${log.actor}`}
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-gray-500">#{index + 1}</span>
          <span className={`rounded px-1.5 py-0.5 text-[10px] ${actionColor(log.action)}`} aria-label={`Action: ${log.action}`}>
            {log.action}
          </span>
        </div>
        <span className="text-[10px] text-gray-500" aria-label={`Timestamp: ${fmtTime(log.ts)}`}>
          {fmtTime(log.ts)}
        </span>
      </button>
      {expanded && (
        <div className="mt-2 flex flex-col gap-1 border-t border-gray-800 pt-2">
          <div className="flex justify-between">
            <span className="text-gray-500">Actor:</span>
            <span className="text-gray-300">{log.actor}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Entity:</span>
            <span className="font-mono text-blue-400">{log.entity}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">prev_hash:</span>
            <span className="font-mono text-gray-400" aria-label={`Previous hash: ${log.prev_hash}`}>
              {shortHash(log.prev_hash)}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">hash:</span>
            <span className="font-mono text-green-400" aria-label={`Hash: ${log.hash}`}>
              {shortHash(log.hash)}
            </span>
          </div>
          {log.before && (
            <details className="mt-1">
              <summary className="cursor-pointer text-[10px] text-gray-500" aria-label="Show before state">
                before
              </summary>
              <pre className="mt-1 overflow-x-auto rounded bg-gray-800 p-1 text-[10px] text-gray-400">
                {JSON.stringify(log.before, null, 2)}
              </pre>
            </details>
          )}
          {log.after && (
            <details className="mt-1">
              <summary className="cursor-pointer text-[10px] text-gray-500" aria-label="Show after state">
                after
              </summary>
              <pre className="mt-1 overflow-x-auto rounded bg-gray-800 p-1 text-[10px] text-gray-400">
                {JSON.stringify(log.after, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  )
}

export default function AuditPage() {
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null)
  const isOnline = typeof navigator !== 'undefined' ? navigator.onLine : true

  const incidentsQ = useQuery({
    queryKey: ['incidents'],
    queryFn: ({ signal }) => api.getIncidents(signal),
  })
  const incidentId = incidentsQ.data?.incidents?.[0]?.id ?? null

  const auditQ = useQuery({
    queryKey: ['audit-logs', incidentId],
    queryFn: ({ signal }) => api.getAuditLogs(incidentId!, signal),
    enabled: !!incidentId,
  })

  const verifyQ = useQuery({
    queryKey: ['audit-verify'],
    queryFn: ({ signal }) => api.getAuditVerify(signal),
    enabled: !!incidentId,
  })

  const provQ = useQuery({
    queryKey: ['provenance', selectedEntity],
    queryFn: ({ signal }) => api.getDecisionProvenance(selectedEntity!, signal),
    enabled: !!selectedEntity,
    retry: false,
  })

  if (incidentsQ.isLoading) {
    return <div className="flex h-full items-center justify-center"><LoadingState message="Loading…" /></div>
  }
  if (incidentsQ.isError) {
    return <div className="p-6"><ErrorState message="Failed to load incidents" onRetry={() => incidentsQ.refetch()} /></div>
  }
  if (!incidentId) {
    return <div className="p-6"><EmptyState message="No active incidents" /></div>
  }

  const logs = auditQ.data?.logs ?? []
  const verifyResult = verifyQ.data
  const provEntries = provQ.data?.entries ?? []

  return (
    <div className="flex flex-col gap-4 p-6" aria-label="Audit page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-100">Audit Log</h1>
          <p className="mt-1 text-sm text-gray-500">Hash-chained append-only event log.</p>
        </div>
        <div className="flex items-center gap-2">
          {!isOnline && <OfflineState />}
          {auditQ.isStale && <StaleState />}
        </div>
      </div>

      <section className="rounded-lg border border-gray-700 bg-gray-900/95 p-4" aria-label="Chain verification">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-wider text-gray-300">Chain Verification</h2>
          <button
            onClick={() => verifyQ.refetch()}
            disabled={verifyQ.isFetching}
            className="min-h-[44px] rounded-md border border-gray-600 bg-gray-800 px-4 py-2 text-xs font-medium text-gray-200 hover:bg-gray-700 disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-blue-500"
            aria-label="Verify audit chain"
          >
            {verifyQ.isFetching ? 'Verifying…' : 'Verify Chain'}
          </button>
        </div>
        {verifyQ.isLoading && <LoadingState message="Verifying chain…" />}
        {verifyQ.isError && (
          <ErrorState message="Failed to verify chain" onRetry={() => verifyQ.refetch()} />
        )}
        {verifyResult && (
          <div className="mt-2 flex items-center gap-2" role="status" aria-live="polite">
            {verifyResult.valid ? (
              <>
                <span className="text-green-400" aria-hidden="true">✓</span>
                <span className="text-sm text-green-400" aria-label="Chain is valid">
                  Chain is valid — all hashes match
                </span>
              </>
            ) : (
              <>
                <span className="text-red-400" aria-hidden="true">✗</span>
                <span className="text-sm text-red-400" aria-label={`Chain broken at index ${verifyResult.first_broken_index ?? '?'}`}>
                  Chain broken at index {verifyResult.first_broken_index ?? '?'}
                </span>
              </>
            )}
          </div>
        )}
      </section>

      <section className="rounded-lg border border-gray-700 bg-gray-900/95 p-4" aria-label="Audit log entries">
        <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-300">
          Events ({logs.length})
        </h2>
        {auditQ.isLoading && <LoadingState message="Loading audit log…" />}
        {auditQ.isError && <ErrorState message="Failed to load audit log" onRetry={() => auditQ.refetch()} />}
        {auditQ.data && logs.length === 0 && (
          <EmptyState message="No audit entries" hint="Events will appear as actions are taken." />
        )}
        {logs.length > 0 && (
          <div className="flex flex-col gap-1.5" role="list" aria-label="Audit entries">
            {logs.map((log, i) => (
              <div key={log.id} role="listitem">
                <AuditRow log={log} index={i} />
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-lg border border-gray-700 bg-gray-900/95 p-4" aria-label="Provenance chain viewer">
        <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-300">Provenance Chain</h2>
        <p className="mb-2 text-[11px] text-gray-500">
          Select an entity ID from the audit log to view its full provenance chain.
        </p>
        <div className="flex flex-wrap gap-1.5">
          {logs.slice(0, 10).map(log => (
            <button
              key={log.id}
              onClick={() => setSelectedEntity(log.entity)}
              className={`rounded border px-2 py-1 text-[10px] font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                selectedEntity === log.entity
                  ? 'border-blue-600 bg-blue-900/30 text-blue-300'
                  : 'border-gray-600 bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
              aria-label={`View provenance for entity ${log.entity}`}
            >
              {log.entity.slice(0, 16)}…
            </button>
          ))}
        </div>

        {selectedEntity && provQ.isLoading && <LoadingState message="Loading provenance…" />}
        {selectedEntity && provQ.isError && (
          <ErrorState message="No provenance found for this entity" detail="This entity may not have a decision provenance chain." />
        )}
        {provEntries.length > 0 && (
          <div className="mt-3 flex flex-col gap-1.5" role="list" aria-label="Provenance entries">
            <div className="mb-1 flex items-center gap-2">
              <span className="text-[10px] text-gray-500">Verified:</span>
              <span className={`text-[10px] ${provQ.data?.verified ? 'text-green-400' : 'text-red-400'}`}>
                {provQ.data?.verified ? 'Yes' : 'No'}
              </span>
            </div>
            {provEntries.map((e, i) => (
              <div key={e.id} role="listitem" className="rounded border border-gray-700 p-2 text-[11px]">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-gray-500">#{i + 1}</span>
                  <span className="text-gray-500">{fmtTime(e.ts)}</span>
                </div>
                <div className="mt-1 flex justify-between">
                  <span className="font-mono text-gray-400">prev: {shortHash(e.prev_hash)}</span>
                  <span className="font-mono text-green-400">hash: {shortHash(e.hash)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
