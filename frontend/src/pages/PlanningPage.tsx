import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { ActionCard, alertToActionCard } from '../components/ActionCard'
import { LoadingState, ErrorState, EmptyState, StaleState } from '../components/state'

interface Toast {
  message: string
  kind: 'success' | 'error'
}

export default function PlanningPage() {
  const queryClient = useQueryClient()
  const [toast, setToast] = useState<Toast | null>(null)
  const [dispatchPendingAlertIds, setDispatchPendingAlertIds] = useState<Set<string>>(new Set())

  const incidentsQ = useQuery({
    queryKey: ['incidents'],
    queryFn: ({ signal }) => api.getIncidents(signal),
  })
  const incidentId = incidentsQ.data?.incidents?.[0]?.id ?? null

  const alertsQ = useQuery({
    queryKey: ['alerts', incidentId],
    queryFn: ({ signal }) => api.getAlerts(incidentId!, signal),
    enabled: !!incidentId,
    refetchInterval: 5000,
  })

  const tasksQ = useQuery({
    queryKey: ['tasks', incidentId],
    queryFn: ({ signal }) => api.getTasks(incidentId!, signal),
    enabled: !!incidentId,
    refetchInterval: 5000,
  })

  function showToast(message: string, kind: 'success' | 'error' = 'success') {
    setToast({ message, kind })
    setTimeout(() => setToast(null), 3000)
  }

  function invalidateAfterDecision() {
    queryClient.invalidateQueries({ queryKey: ['alerts', incidentId] })
    queryClient.invalidateQueries({ queryKey: ['tasks', incidentId] })
  }

  const approveMut = useMutation({
    mutationFn: (vars: { alertId: string; rationale: string }) =>
      api.approveAlert(incidentId!, vars.alertId, vars.rationale),
    onSuccess: (result) => {
      showToast(result === undefined ? 'Approval queued for reconnect' : 'Alert approved successfully')
      invalidateAfterDecision()
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : 'Approval failed'
      showToast(msg, 'error')
    },
  })

  const dismissMut = useMutation({
    mutationFn: (vars: { alertId: string; rationale: string }) =>
      api.dismissAlert(incidentId!, vars.alertId, vars.rationale),
    onSuccess: () => {
      showToast('Alert dismissed')
      invalidateAfterDecision()
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : 'Dismissal failed'
      showToast(msg, 'error')
    },
  })

  const modifyMut = useMutation({
    mutationFn: (vars: { alertId: string; action: string }) =>
      api.modifyAlert(incidentId!, vars.alertId, { recommended_action: vars.action }),
    onSuccess: () => {
      showToast('Alert modified — ready for review')
      invalidateAfterDecision()
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : 'Modify failed'
      showToast(msg, 'error')
    },
  })

  function handleApprove(alertId: string) {
    approveMut.mutate({ alertId, rationale: 'Approved from planning view' })
  }

  function handleDismiss(alertId: string) {
    const rationale = window.prompt('Enter dismissal rationale (required):')
    if (rationale) dismissMut.mutate({ alertId, rationale })
  }

  function handleModify(alertId: string) {
    const action = window.prompt('Enter new recommended action:')
    if (action) modifyMut.mutate({ alertId, action })
  }

  function handleDispatchRequest(alertId: string) {
    setDispatchPendingAlertIds(current => new Set(current).add(alertId))
    showToast('Dispatch pending dual approval — no task created')
  }

  if (incidentsQ.isLoading) {
    return <div className="flex h-full items-center justify-center"><LoadingState message="Loading incidents…" /></div>
  }
  if (incidentsQ.isError) {
    return <div className="p-6"><ErrorState message="Failed to load incidents" onRetry={() => incidentsQ.refetch()} /></div>
  }
  if (!incidentId) {
    return <div className="p-6"><EmptyState message="No active incidents" hint="Create an incident to see action proposals." /></div>
  }

  const alerts = alertsQ.data?.alerts ?? []
  const proposals = alerts.filter(a => a.status === 'draft' || a.status === 'modified')
  const reviewed = alerts.filter(a => a.status === 'approved' || a.status === 'dismissed')
  const pending = approveMut.isPending || dismissMut.isPending || modifyMut.isPending
  const tasks = tasksQ.data?.tasks ?? []

  return (
    <div className="flex flex-col gap-4 p-6" aria-label="Planning page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-100">Planning</h1>
          <p className="mt-1 text-sm text-gray-500">
            Action proposals pending review. Approve, modify, or dismiss each recommendation.
          </p>
        </div>
        {alertsQ.isStale && <StaleState />}
      </div>

      {toast && (
        <div
          role="alert"
          aria-live="assertive"
          className={`fixed right-6 top-20 z-50 rounded-lg border px-4 py-3 shadow-xl ${
            toast.kind === 'success'
              ? 'border-green-600 bg-green-900/95 text-green-200'
              : 'border-red-600 bg-red-900/95 text-red-200'
          }`}
        >
          {toast.message}
        </div>
      )}

      {alertsQ.isLoading && <LoadingState message="Loading action proposals…" />}
      {alertsQ.isError && <ErrorState message="Failed to load alerts" onRetry={() => alertsQ.refetch()} />}
      {tasksQ.isError && <ErrorState message="Failed to load task status" onRetry={() => tasksQ.refetch()} />}

      {tasks.length > 0 && (
        <section aria-label="Alert task status">
          <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-400">
            Alert Tasks ({tasks.length})
          </h2>
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-2" role="list">
            {tasks.slice(0, 6).map(task => (
              <div key={task.id} role="listitem" className="rounded border border-gray-700 bg-gray-900/70 px-3 py-2 text-xs text-gray-300">
                <span className="font-medium text-gray-100">{task.title}</span>
                <span className="ml-2 rounded bg-gray-800 px-1.5 py-0.5 text-gray-400" data-testid="task-status">
                  {task.status}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {alertsQ.data && proposals.length === 0 && reviewed.length === 0 && (
        <EmptyState message="No action proposals" hint="Alerts will appear here when the system generates recommendations." />
      )}

      {proposals.length > 0 && (
        <section aria-label="Pending proposals">
          <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-400">
            Pending Review ({proposals.length})
          </h2>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2" role="list" aria-label="Action proposals">
            {proposals.map(a => (
              <div key={a.id} role="listitem" data-testid="alert-card">
                <ActionCard
                  action={alertToActionCard(a)}
                  status={a.status}
                  onApprove={handleApprove}
                  onDismiss={handleDismiss}
                  onModify={handleModify}
                  onDispatchRequest={handleDispatchRequest}
                  dispatchPending={dispatchPendingAlertIds.has(a.id)}
                />
              </div>
            ))}
          </div>
        </section>
      )}

      {reviewed.length > 0 && (
        <section aria-label="Reviewed alerts" className="mt-2">
          <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-500">
            Recently Reviewed ({reviewed.length})
          </h2>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 opacity-60" role="list" aria-label="Reviewed alerts">
            {reviewed.slice(0, 4).map(a => (
              <div key={a.id} role="listitem" data-testid="alert-card">
                <ActionCard
                  action={alertToActionCard(a)}
                  status={a.status}
                  onApprove={handleApprove}
                  onDismiss={handleDismiss}
                  onModify={handleModify}
                />
              </div>
            ))}
          </div>
        </section>
      )}

      {pending && (
        <div className="fixed bottom-6 right-6 z-50" role="status" aria-live="polite" aria-label="Processing decision">
          <div className="flex items-center gap-2 rounded-lg border border-gray-600 bg-gray-900 px-4 py-2 shadow-xl">
            <svg className="h-4 w-4 animate-spin text-blue-400" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="text-xs text-gray-300">Processing…</span>
          </div>
        </div>
      )}
    </div>
  )
}
