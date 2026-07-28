import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Task } from '../api/types'
import { LoadingState, ErrorState, EmptyState, StaleState, OfflineState } from '../components/state'
import { QuickReportForm } from '../components/QuickReportForm'

const TASK_STATUSES = ['pending', 'in_progress', 'completed', 'cancelled', 'blocked']

function statusColor(status: string): string {
  const m: Record<string, string> = {
    pending: 'bg-gray-500/10 text-gray-400',
    in_progress: 'bg-blue-500/10 text-blue-400',
    completed: 'bg-green-500/10 text-green-400',
    cancelled: 'bg-gray-500/10 text-gray-500',
    blocked: 'bg-red-500/10 text-red-400',
  }
  return m[status] ?? 'bg-gray-500/10 text-gray-400'
}

export default function FieldPage() {
  const queryClient = useQueryClient()
  const [toast, setToast] = useState<{ msg: string; kind: 'success' | 'error' } | null>(null)
  const [showForm, setShowForm] = useState(false)
  const isOnline = typeof navigator !== 'undefined' ? navigator.onLine : true

  function showToast(msg: string, kind: 'success' | 'error' = 'success') {
    setToast({ msg, kind })
    setTimeout(() => setToast(null), 3000)
  }

  const incidentsQ = useQuery({
    queryKey: ['incidents'],
    queryFn: ({ signal }) => api.getIncidents(signal),
  })
  const incidentId = incidentsQ.data?.incidents?.[0]?.id ?? null

  const tasksQ = useQuery({
    queryKey: ['tasks', incidentId],
    queryFn: ({ signal }) => api.getTasks(incidentId!, signal),
    enabled: !!incidentId,
  })

  const roadsQ = useQuery({
    queryKey: ['entities', incidentId, 'roads'],
    queryFn: ({ signal }) => api.getEntities(incidentId!, 'roads', signal),
    enabled: !!incidentId,
  })

  function invalidateAll() {
    queryClient.invalidateQueries({ queryKey: ['tasks', incidentId] })
    queryClient.invalidateQueries({ queryKey: ['entities', incidentId] })
  }

  const statusMut = useMutation({
    mutationFn: (vars: { taskId: string; status: string }) =>
      api.updateTaskStatus(vars.taskId, { status: vars.status }),
    networkMode: 'always',
    onMutate: (vars) => {
      queryClient.cancelQueries({ queryKey: ['tasks', incidentId] })
      const prev = queryClient.getQueryData<{ tasks: Task[] }>(['tasks', incidentId])
      if (prev) {
        const updated = prev.tasks.map(t =>
          t.id === vars.taskId ? { ...t, status: vars.status } : t
        )
        queryClient.setQueryData(['tasks', incidentId], { ...prev, tasks: updated })
      }
      return { prev }
    },
    onError: (_e, _vars, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(['tasks', incidentId], ctx.prev)
      showToast('Status update failed — rolled back', 'error')
    },
    onSuccess: (_d, vars) => {
      showToast(`Task marked ${vars.status}`)
      invalidateAll()
    },
  })

  const roadMut = useMutation({
    mutationFn: (vars: { roadId: string; status: string }) =>
      api.updateEntity(incidentId!, 'roads', vars.roadId, { status: vars.status }),
    networkMode: 'always',
    onMutate: (vars) => {
      const key = ['entities', incidentId, 'roads']
      queryClient.cancelQueries({ queryKey: key })
      type RoadFC = { features: Array<{ properties: { id: string; status?: string } }> }
      const prev = queryClient.getQueryData<RoadFC>(key)
      if (prev) {
        const updated = prev.features.map(f =>
          f.properties.id === vars.roadId
            ? { ...f, properties: { ...f.properties, status: vars.status } }
            : f
        )
        queryClient.setQueryData(key, { ...prev, features: updated })
      }
      return { prev }
    },
    onError: (_e, _vars, ctx) => {
      const key = ['entities', incidentId, 'roads']
      if (ctx?.prev) queryClient.setQueryData(key, ctx.prev)
      showToast('Road update failed — rolled back', 'error')
    },
    onSuccess: (_d, vars) => {
      showToast(`Road marked ${vars.status}`)
      invalidateAll()
    },
  })

  if (incidentsQ.isLoading) {
    return <div className="flex h-full items-center justify-center"><LoadingState message="Loading…" /></div>
  }
  if (incidentsQ.isError) {
    return <div className="p-4"><ErrorState message="Failed to load incidents" onRetry={() => incidentsQ.refetch()} /></div>
  }
  if (!incidentId) {
    return <div className="p-4"><EmptyState message="No active incidents" /></div>
  }

  const tasks = tasksQ.data?.tasks ?? []
  const roads = roadsQ.data?.features ?? []
  const pending = statusMut.isPending || roadMut.isPending

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-3 p-3" aria-label="Field responder page">
      <div className="flex items-center justify-between">
        <h1 className="text-base font-bold text-gray-100">Field Responder</h1>
        <div className="flex items-center gap-1.5">
          {!isOnline && <OfflineState />}
          {tasksQ.isStale && <StaleState />}
        </div>
      </div>

      {toast && (
        <div role="alert" aria-live="assertive"
          className={`rounded-lg border px-3 py-2 text-xs ${toast.kind === 'success' ? 'border-green-600 bg-green-900/95 text-green-200' : 'border-red-600 bg-red-900/95 text-red-200'}`}>
          {toast.msg}
        </div>
      )}

      <button
        onClick={() => setShowForm(s => !s)}
        className="min-h-[44px] rounded-lg bg-blue-600 px-4 py-3 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
        aria-label="Toggle quick report form"
      >
        {showForm ? 'Cancel Report' : '+ Quick Report'}
      </button>

      {showForm && (
        <QuickReportForm incidentId={incidentId} onDone={() => setShowForm(false)} showToast={showToast} />
      )}

      <section aria-label="Assigned tasks">
        <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-400">My Tasks</h2>
        {tasksQ.isLoading && <LoadingState message="Loading tasks…" />}
        {tasksQ.isError && <ErrorState message="Failed to load tasks" onRetry={() => tasksQ.refetch()} />}
        {tasksQ.data && tasks.length === 0 && <EmptyState message="No tasks assigned" />}
        <div className="flex flex-col gap-2" role="list">
          {tasks.map(t => (
            <div key={t.id} role="listitem" data-testid="task-card" className="rounded-lg border border-gray-700 bg-gray-900/95 p-3">
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-sm font-medium text-gray-100">{t.title}</h3>
                <span className={`rounded px-1.5 py-0.5 text-[10px] ${statusColor(t.status)}`} aria-label={`Status: ${t.status}`}>
                  {t.status}
                </span>
              </div>
              {t.priority && (
                <p className="mt-1 text-[11px] text-amber-400" aria-label={`Priority: ${t.priority}`}>
                  Priority: {t.priority}
                </p>
              )}
              <select value={t.status}
                onChange={(e) => statusMut.mutate({ taskId: t.id, status: e.target.value })}
                disabled={pending}
                className="mt-2 min-h-[44px] w-full rounded border border-gray-600 bg-gray-800 px-3 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                aria-label={`Update status for task ${t.title}`}>
                {TASK_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          ))}
        </div>
      </section>

      {roads.length > 0 && (
        <section aria-label="Road status">
          <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-400">Roads</h2>
          <div className="flex flex-col gap-2" role="list">
            {roads.map(r => {
              const rid = (r.properties as { id?: string }).id ?? ''
              const rstatus = (r.properties as { status?: string }).status ?? 'unknown'
              return (
                <div key={rid} role="listitem" className="rounded-lg border border-gray-700 bg-gray-900/95 p-3">
                  <p className="text-sm text-gray-200">
                    {(r.properties as { name?: string }).name ?? rid}
                  </p>
                  <span className="text-[11px] text-gray-500" aria-label={`Road status: ${rstatus}`}>
                    {rstatus}
                  </span>
                  <div className="mt-2 flex gap-2">
                    <button onClick={() => roadMut.mutate({ roadId: rid, status: 'blocked' })}
                      disabled={pending}
                      className="min-h-[44px] flex-1 rounded-lg bg-red-600 px-3 py-2 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-red-500"
                      aria-label={`Mark road ${rid} as blocked`}>
                      Block
                    </button>
                    <button onClick={() => roadMut.mutate({ roadId: rid, status: 'open' })}
                      disabled={pending}
                      className="min-h-[44px] flex-1 rounded-lg bg-green-600 px-3 py-2 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-green-500"
                      aria-label={`Mark road ${rid} as open`}>
                      Open
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {pending && (
        <div className="fixed bottom-4 right-4 z-50" role="status" aria-live="polite" aria-label="Processing">
          <div className="flex items-center gap-2 rounded-lg border border-gray-600 bg-gray-900 px-3 py-2 shadow-xl">
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
