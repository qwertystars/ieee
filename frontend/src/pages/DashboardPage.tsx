import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import MapView from '../components/MapView'
import { LoadingState, ErrorState, EmptyState, StaleState } from '../components/state'

function severityColor(sev: string): string {
  const m: Record<string, string> = {
    extreme: 'text-red-400 bg-red-500/10',
    severe: 'text-red-400 bg-red-500/10',
    high: 'text-orange-400 bg-orange-500/10',
    moderate: 'text-amber-400 bg-amber-500/10',
    minor: 'text-blue-400 bg-blue-500/10',
  }
  return m[sev.toLowerCase()] ?? 'text-gray-400 bg-gray-500/10'
}

function statusColor(status: string): string {
  const m: Record<string, string> = {
    pending: 'text-gray-400', in_progress: 'text-blue-400',
    completed: 'text-green-400', cancelled: 'text-gray-500',
    blocked: 'text-red-400', approved: 'text-green-400',
    dismissed: 'text-gray-500', draft: 'text-amber-400',
  }
  return m[status] ?? 'text-gray-400'
}

function Panel({ title, children, stale }: {
  title: string; children: React.ReactNode; stale?: boolean
}) {
  return (
    <section className="rounded-lg border border-gray-700 bg-gray-900/95 p-3 shadow-lg" aria-label={title}>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-xs font-bold uppercase tracking-wider text-gray-300">{title}</h2>
        {stale && <StaleState />}
      </div>
      {children}
    </section>
  )
}

export default function DashboardPage() {
  const incidentsQ = useQuery({
    queryKey: ['incidents'],
    queryFn: ({ signal }) => api.getIncidents(signal),
  })
  const incidentId = incidentsQ.data?.incidents?.[0]?.id ?? null
  const incident = incidentsQ.data?.incidents?.[0]

  const sitRepQ = useQuery({
    queryKey: ['situation-report', incidentId],
    queryFn: ({ signal }) => api.getSituationReport(incidentId!, signal),
    enabled: !!incidentId,
  })
  const alertsQ = useQuery({
    queryKey: ['alerts', incidentId],
    queryFn: ({ signal }) => api.getAlerts(incidentId!, signal),
    enabled: !!incidentId,
  })
  const tasksQ = useQuery({
    queryKey: ['tasks', incidentId],
    queryFn: ({ signal }) => api.getTasks(incidentId!, signal),
    enabled: !!incidentId,
  })

  if (incidentsQ.isLoading) {
    return <div className="flex h-full items-center justify-center"><LoadingState message="Loading incident data…" /></div>
  }
  if (incidentsQ.isError) {
    return <div className="p-6"><ErrorState message="Failed to load incidents" onRetry={() => incidentsQ.refetch()} /></div>
  }
  if (!incident) {
    return <div className="p-6"><EmptyState message="No active incidents" hint="Create an incident to see the dashboard." /></div>
  }

  const alerts = alertsQ.data?.alerts ?? []
  const tasks = tasksQ.data?.tasks ?? []
  const sitRep = sitRepQ.data
  const obsCount = sitRep?.observations?.length ?? 0
  const hazardCount = sitRep?.hazards?.length ?? 0
  const hypCount = sitRep?.hypotheses?.length ?? 0

  return (
    <div className="flex h-[calc(100vh-3.5rem)] w-full overflow-hidden">
      {/* Map — left/main area */}
      <div className="flex-1 relative" role="application" aria-label="Situation awareness map">
        <MapView />
      </div>

      {/* Right sidebar — situation report, alerts, tasks */}
      <aside className="w-96 flex-shrink-0 overflow-y-auto border-l border-gray-800 bg-gray-950 p-3" aria-label="Situation panels">
        {/* Incident header */}
        <div className="mb-3 rounded-lg border border-gray-700 bg-gray-900 p-3">
          <h1 className="text-sm font-bold text-gray-100">{incident.title}</h1>
          <div className="mt-1 flex flex-wrap gap-2 text-xs">
            <span className="rounded bg-gray-800 px-1.5 py-0.5 text-gray-300">{incident.disaster_type}</span>
            <span className="rounded bg-gray-800 px-1.5 py-0.5 text-gray-300">Severity: {incident.severity}</span>
            <span className="rounded bg-gray-800 px-1.5 py-0.5 text-gray-300">Status: {incident.status}</span>
          </div>
        </div>

        {/* Situation report summary */}
        <div className="mb-3">
          {sitRepQ.isLoading && <Panel title="Situation Report"><LoadingState message="Generating report…" /></Panel>}
          {sitRepQ.isError && <Panel title="Situation Report"><ErrorState message="Failed to load report" onRetry={() => sitRepQ.refetch()} /></Panel>}
          {sitRep && (
            <Panel title="Situation Report" stale={sitRepQ.isStale}>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="rounded bg-gray-800/50 p-2">
                  <div className="text-lg font-bold text-blue-400">{obsCount}</div>
                  <div className="text-gray-500">Observations</div>
                </div>
                <div className="rounded bg-gray-800/50 p-2">
                  <div className="text-lg font-bold text-orange-400">{hazardCount}</div>
                  <div className="text-gray-500">Hazards</div>
                </div>
                <div className="rounded bg-gray-800/50 p-2">
                  <div className="text-lg font-bold text-purple-400">{hypCount}</div>
                  <div className="text-gray-500">Hypotheses</div>
                </div>
                <div className="rounded bg-gray-800/50 p-2">
                  <div className="text-lg font-bold text-cyan-400">{alerts.length}</div>
                  <div className="text-gray-500">Alerts</div>
                </div>
              </div>
            </Panel>
          )}
        </div>

        {/* Alert summary */}
        <div className="mb-3">
          {alertsQ.isLoading && <Panel title="Alerts"><LoadingState message="Loading alerts…" /></Panel>}
          {alertsQ.isError && <Panel title="Alerts"><ErrorState message="Failed to load alerts" onRetry={() => alertsQ.refetch()} /></Panel>}
          {alertsQ.data && alerts.length === 0 && <Panel title="Alerts"><EmptyState message="No active alerts" /></Panel>}
          {alerts.length > 0 && (
            <Panel title="Alerts" stale={alertsQ.isStale}>
              <div className="flex flex-col gap-2">
                {alerts.slice(0, 5).map(a => (
                  <div key={a.id} className="rounded border border-gray-700 p-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-200">{a.title}</span>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] ${severityColor(a.severity)}`}>{a.severity}</span>
                    </div>
                    <p className="mt-1 text-gray-400">{a.message}</p>
                    {a.recommended_action && (
                      <p className="mt-1 text-amber-400">→ {a.recommended_action}</p>
                    )}
                    <div className="mt-1 flex items-center gap-2">
                      <span className={`text-[10px] ${statusColor(a.status)}`}>{a.status}</span>
                    </div>
                  </div>
                ))}
                {alerts.length > 5 && (
                  <p className="text-center text-[10px] text-gray-500">+{alerts.length - 5} more alerts</p>
                )}
              </div>
            </Panel>
          )}
        </div>

        {/* Task summary */}
        <div className="mb-3">
          {tasksQ.isLoading && <Panel title="Tasks"><LoadingState message="Loading tasks…" /></Panel>}
          {tasksQ.isError && <Panel title="Tasks"><ErrorState message="Failed to load tasks" onRetry={() => tasksQ.refetch()} /></Panel>}
          {tasksQ.data && tasks.length === 0 && <Panel title="Tasks"><EmptyState message="No tasks" /></Panel>}
          {tasks.length > 0 && (
            <Panel title="Tasks" stale={tasksQ.isStale}>
              <div className="flex flex-col gap-1.5">
                {tasks.slice(0, 8).map(t => (
                  <div key={t.id} className="flex items-center justify-between rounded border border-gray-700 p-1.5 text-xs">
                    <span className="truncate text-gray-200">{t.title}</span>
                    <div className="flex items-center gap-1.5">
                      {t.priority && (
                        <span className="text-[10px] text-amber-400">{t.priority}</span>
                      )}
                      <span className={`text-[10px] ${statusColor(t.status)}`}>{t.status}</span>
                    </div>
                  </div>
                ))}
                {tasks.length > 8 && (
                  <p className="text-center text-[10px] text-gray-500">+{tasks.length - 8} more tasks</p>
                )}
              </div>
            </Panel>
          )}
        </div>
      </aside>
    </div>
  )
}
