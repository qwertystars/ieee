// Command Center view — ported from p4 and adapted to the current typed API client.
// Aggregates dashboard summary, map layers, recommendations, alerts, and tasks for the selected event.

import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { useEffect, useRef, useState, useCallback } from 'react'
import { useAuth } from '../auth/AuthContext'
import {
  dashboardApi,
  eventsApi,
  recommendationsApi,
  alertsApi,
  tasksApi,
  tokenStore,
} from '../api/client'
import { DisasterWsClient } from '../lib/ws'
import type { WsEvent, DisasterEventRead, DashboardSummary, RecommendationRead, TaskRead, AlertRead } from '../types'

import {
  AlertTriangle,
  Cloud,
  Users,
  ClipboardList,
  ShieldAlert,
  Building2,
  Activity,
  Radio,
  RefreshCw,
  FileText,
  Bell,
  Monitor,
  Tv,
  Download,
  Handshake,
  Clock,
  CheckCircle,
  XCircle,
  MapPin,
  Thermometer,
  Wind,
  Droplets,
  Zap,
  Package,
  Calendar,
  GitBranch,
} from 'lucide-react'

const POLL_MS = 15_000

const severityColors: Record<string, string> = {
  low: 'text-blue-400',
  medium: 'text-yellow-400',
  high: 'text-orange-400',
  critical: 'text-red-400',
}

const severityBg: Record<string, string> = {
  low: 'bg-blue-500/10 border-blue-500/20',
  medium: 'bg-yellow-500/10 border-yellow-500/20',
  high: 'bg-orange-500/10 border-orange-500/20',
  critical: 'bg-red-500/10 border-red-500/20',
}

const teamStatusColors: Record<string, string> = {
  active: 'bg-green-500/10 text-green-400',
  standby: 'bg-yellow-500/10 text-yellow-400',
  offline: 'bg-slate-500/10 text-slate-400',
  deployed: 'bg-blue-500/10 text-blue-400',
  en_route: 'bg-blue-500/10 text-blue-400',
  on_site: 'bg-green-500/10 text-green-400',
  assigned: 'bg-yellow-500/10 text-yellow-400',
  completed: 'bg-green-500/10 text-green-400',
  blocked: 'bg-red-500/10 text-red-400',
  cancelled: 'bg-slate-500/10 text-slate-400',
}

const priorityOrder: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
}

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const h = Math.floor(m / 60)
  const d = Math.floor(h / 24)
  if (d > 0) return `${d}d ${h % 24}h ${m % 60}m`
  if (h > 0) return `${h}h ${m % 60}m ${s % 60}s`
  return `${m}m ${s % 60}s`
}

function Panel({
  title,
  icon: Icon,
  children,
  onRefresh,
  loading,
  error,
}: {
  title: string
  icon: React.ElementType
  children: React.ReactNode
  onRefresh?: () => void
  loading?: boolean
  error?: boolean
}) {
  return (
    <div className="bg-slate-900 rounded-lg border border-slate-800 p-4 flex flex-col min-h-[200px]">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Icon size={18} className="text-slate-400" />
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">{title}</h2>
        </div>
        {onRefresh && (
          <button onClick={onRefresh} className="p-1 text-slate-500 hover:text-slate-300 transition-colors">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        )}
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        {error ? (
          <div className="flex items-center justify-center h-full text-red-400 text-sm">
            <XCircle size={16} className="mr-2" /> Failed to load
          </div>
        ) : loading ? (
          <div className="space-y-2 animate-pulse">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 bg-slate-800 rounded-lg" />
            ))}
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  )
}

function QuickStat({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <div className="flex flex-col items-center px-4 py-2">
      <span className="text-xs text-slate-500 uppercase tracking-wide">{label}</span>
      <span className={`text-xl font-bold ${color ?? 'text-white'}`}>{value}</span>
      {sub && <span className="text-xs text-slate-500">{sub}</span>}
    </div>
  )
}

function OccupancyBar({ current, capacity, label }: { current: number; capacity: number; label: string }) {
  const pct = capacity > 0 ? Math.min(100, Math.round((current / capacity) * 100)) : 0
  const barColor = pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-yellow-500' : 'bg-green-500'
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-slate-300">{label}</span>
        <span className="text-slate-400">{current}/{capacity} ({pct}%)</span>
      </div>
      <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
        <div className={`h-full ${barColor} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function ResourceBar({ available, total, label }: { available: number; total: number; label: string }) {
  const pct = total > 0 ? Math.round((available / total) * 100) : 0
  const barColor = pct < 20 ? 'bg-red-500' : pct < 50 ? 'bg-yellow-500' : 'bg-green-500'
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-slate-300 capitalize">{label}</span>
        <span className="text-slate-400">{available}/{total} available</span>
      </div>
      <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
        <div className={`h-full ${barColor} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function EventSeverityBadge({ event }: { event: DisasterEventRead | undefined }) {
  if (!event) return null
  // Treat event type as severity label for styling.
  const typeLabel = event.type.replace(/_/g, ' ')
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium border ${severityBg[event.type] ?? 'bg-slate-800 border-slate-700'} ${severityColors[event.type] ?? 'text-slate-400'}`}>
      {typeLabel.toUpperCase()}
    </span>
  )
}

function RecommendationActions({ rec, eventId }: { rec: RecommendationRead; eventId: string }) {
  const queryClient = useQueryClient()

  const approveMutation = useMutation({
    mutationFn: () => recommendationsApi.approve(eventId, rec.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['recommendations', eventId] }),
  })

  const dismissMutation = useMutation({
    mutationFn: () => recommendationsApi.dismiss(eventId, rec.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['recommendations', eventId] }),
  })

  if (rec.status !== 'draft' && rec.status !== 'reviewed') return null

  return (
    <div className="flex gap-2 mt-3">
      <button
        onClick={() => approveMutation.mutate()}
        disabled={approveMutation.isPending}
        className="px-3 py-1.5 bg-green-600 hover:bg-green-700 disabled:opacity-50 rounded text-xs font-medium transition-colors"
      >
        <CheckCircle size={12} className="inline mr-1" /> Approve
      </button>
      <button
        onClick={() => dismissMutation.mutate()}
        disabled={dismissMutation.isPending}
        className="px-3 py-1.5 bg-red-600 hover:bg-red-700 disabled:opacity-50 rounded text-xs font-medium transition-colors"
      >
        <XCircle size={12} className="inline mr-1" /> Dismiss
      </button>
    </div>
  )
}

export default function CommandCenter() {
  const { user } = useAuth()
  const queryClient = useQueryClient()

  // ── Event selection (same pattern as Dashboard.tsx) ───────────────────────
  const [eventId, setEventId] = useState<string | null>(null)

  const { data: events } = useQuery({
    queryKey: ['events'],
    queryFn: () => eventsApi.list({ limit: 50 }),
    staleTime: 60_000,
  })

  useEffect(() => {
    if (!eventId && events && events.length > 0) {
      const active = events.find((e) => e.status === 'active') ?? events[0]
      setEventId(active.id)
    }
  }, [events, eventId])

  const currentEvent = events?.find((e) => e.id === eventId)

  // ── Realtime via WebSocket (reuse Dashboard pattern) ──────────────────────
  const wsRef = useRef<DisasterWsClient | null>(null)

  useEffect(() => {
    if (!eventId) return
    const ws = new DisasterWsClient(eventId, tokenStore.get())
    ws.connect()
    const unsub = ws.subscribe((evt: WsEvent) => {
      const invalidateMap = {
        new_observation: ['map-layers'],
        new_report: ['map-layers', 'dashboard-summary'],
        report_verified: ['map-layers'],
        area_priority_changed: ['map-layers', 'dashboard-summary'],
        recommendation_created: ['recommendations'],
        recommendation_approved: ['recommendations'],
        task_assigned: ['dashboard-summary'],
        task_status_changed: ['dashboard-summary'],
        shelter_status_changed: ['map-layers', 'dashboard-summary'],
        road_status_changed: ['map-layers'],
        team_location_updated: ['map-layers'],
        alert_created: ['alerts', 'dashboard-summary'],
      } as const
      const keys = invalidateMap[evt.type] ?? []
      keys.forEach((k) => queryClient.invalidateQueries({ queryKey: [k, eventId] }))
    })
    wsRef.current = ws
    return () => {
      unsub()
      ws.disconnect()
      wsRef.current = null
    }
  }, [eventId, queryClient])

  // ── Data queries ──────────────────────────────────────────────────────────
  const { data: summary, isLoading: summaryLoading, error: summaryError } = useQuery<DashboardSummary>({
    queryKey: ['dashboard-summary', eventId],
    queryFn: () => dashboardApi.summary(eventId!),
    enabled: !!eventId,
    refetchInterval: POLL_MS,
  })

  const { data: mapLayers, isLoading: layersLoading, error: layersError } = useQuery({
    queryKey: ['map-layers', eventId],
    queryFn: () => dashboardApi.mapLayers(eventId!),
    enabled: !!eventId,
    refetchInterval: POLL_MS,
    staleTime: POLL_MS,
  })

  const { data: recommendations, isLoading: recsLoading, error: recsError } = useQuery<RecommendationRead[]>({
    queryKey: ['recommendations', eventId],
    queryFn: () => recommendationsApi.list(eventId!, { limit: 100 }),
    enabled: !!eventId,
    refetchInterval: POLL_MS,
  })

  const { data: alerts, isLoading: alertsLoading, error: alertsError } = useQuery<AlertRead[]>({
    queryKey: ['alerts', eventId],
    queryFn: () => alertsApi.list(eventId!),
    enabled: !!eventId,
    refetchInterval: POLL_MS,
  })

  const { data: tasks, isLoading: tasksLoading, error: tasksError } = useQuery<TaskRead[]>({
    queryKey: ['tasks', eventId],
    queryFn: () => tasksApi.list(eventId!, { limit: 100 }),
    enabled: !!eventId,
    refetchInterval: POLL_MS,
  })

  // ── Elapsed time since event start ────────────────────────────────────────
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!currentEvent?.start_time) {
      setElapsed(0)
      return
    }
    const start = new Date(currentEvent.start_time).getTime()
    const tick = () => setElapsed(Date.now() - start)
    tick()
    const interval = setInterval(tick, 1000)
    return () => clearInterval(interval)
  }, [currentEvent?.start_time])

  // ── UI state ──────────────────────────────────────────────────────────────
  const [briefingMode, setBriefingMode] = useState(false)
  const [warRoom, setWarRoom] = useState(false)
  const [tvDisplay, setTvDisplay] = useState(false)

  const invalidateAll = useCallback(() => {
    if (!eventId) return
    const keys = ['dashboard-summary', 'map-layers', 'recommendations', 'alerts', 'tasks'] as const
    keys.forEach((k) => queryClient.invalidateQueries({ queryKey: [k, eventId] }))
  }, [queryClient, eventId])

  // ── Derived data (adapted to current types) ─────────────────────────────
  const teams = mapLayers?.teams ?? []
  const areas = mapLayers?.areas ?? []
  const shelters = mapLayers?.shelters ?? []
  const sortedTasks = [...(tasks ?? [])].sort(
    (a, b) => (priorityOrder[a.priority] ?? 99) - (priorityOrder[b.priority] ?? 99)
  )
  const sortedRecommendations = [...(recommendations ?? [])].sort(
    (a, b) => (priorityOrder[a.urgency] ?? 99) - (priorityOrder[b.urgency] ?? 99)
  )

  const activeRecommendations = (recommendations ?? []).filter(
    (r) => r.status === 'draft' || r.status === 'reviewed'
  ).length

  const pendingTasks = (tasks ?? []).filter(
    (t) => t.status === 'assigned' || t.status === 'accepted' || t.status === 'en_route' || t.status === 'on_site'
  ).length

  const respondersActive = teams.filter((t) => t.status === 'active' || t.status === 'deployed' || t.status === 'en_route').length
  const respondersTotal = teams.length
  const tasksOpen = pendingTasks
  const tasksCompleted = (tasks ?? []).filter((t) => t.status === 'completed').length
  const sheltersActive = shelters.filter((s) => s.status === 'open').length
  const shelterCapacity = shelters.reduce((sum, s) => sum + s.total_capacity, 0)
  const unacknowledgedAlerts = (alerts ?? []).filter((a) => !a.acknowledged).length
  const alertCount = (alerts ?? []).length

  // Stub resource view built from shelters/teams (no dedicated resource endpoint yet).
  const resourceCategories: Record<string, { available: number; total: number }> = {
    shelter: { available: shelterCapacity - shelters.reduce((sum, s) => sum + s.current_occupancy, 0), total: shelterCapacity },
    teams: { available: respondersTotal - respondersActive, total: respondersTotal },
  }

  const containerClass = tvDisplay ? 'p-8 text-lg' : 'p-6'
  const gridClass = warRoom ? 'grid-cols-1 md:grid-cols-2 xl:grid-cols-4' : 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3'

  return (
    <div className={`${containerClass} space-y-4`}>
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className={`${tvDisplay ? 'text-4xl' : 'text-2xl'} font-bold`}>
            {currentEvent?.name ?? 'Command Center'}
          </h1>
          <div className="flex items-center gap-3 mt-1 flex-wrap">
            {currentEvent && <EventSeverityBadge event={currentEvent} />}
            {currentEvent && (
              <span className="text-sm text-slate-400">
                {currentEvent.status.replace(/_/g, ' ')} • {currentEvent.type.replace(/_/g, ' ')}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          {/* Event selector */}
          <select
            value={eventId ?? ''}
            onChange={(e) => setEventId(e.target.value)}
            className="text-sm bg-slate-800 border border-slate-700 rounded px-2 py-1 text-white focus:outline-none focus:border-slate-500 max-w-[200px] truncate"
          >
            {!events && <option value="">Loading events…</option>}
            {events?.map((ev) => (
              <option key={ev.id} value={ev.id}>
                {ev.name} ({ev.status})
              </option>
            ))}
          </select>

          <div className="flex items-center gap-2 text-xs px-3 py-1.5 bg-slate-800 rounded-lg">
            <Clock size={14} className="text-slate-400" />
            <span className="font-mono text-slate-300">{formatElapsed(elapsed)}</span>
          </div>

          <button onClick={invalidateAll} className="flex items-center gap-2 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-xs text-slate-300 transition-colors">
            <RefreshCw size={14} /> Refresh
          </button>

          <button className="flex items-center gap-2 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-xs text-slate-300 transition-colors">
            <Handshake size={14} />
            Shift Handoff
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between bg-slate-900 rounded-lg border border-slate-800 px-4 py-2">
        <QuickStat label="Responders" value={`${respondersActive}/${respondersTotal}`} sub="Active/Total" color="text-blue-400" />
        <div className="w-px h-8 bg-slate-800 hidden sm:block" />
        <QuickStat label="Tasks" value={`${tasksOpen}/${tasksCompleted}`} sub="Open/Done" color="text-orange-400" />
        <div className="w-px h-8 bg-slate-800 hidden sm:block" />
        <QuickStat label="Shelters" value={`${sheltersActive}/${shelterCapacity}`} sub="Open/Capacity" color="text-green-400" />
        <div className="w-px h-8 bg-slate-800 hidden sm:block" />
        <QuickStat label="Alerts" value={`${unacknowledgedAlerts}/${alertCount}`} sub="Unack/Total" color="text-red-400" />
        <div className="w-px h-8 bg-slate-800 hidden sm:block" />
        <QuickStat label="Recs" value={activeRecommendations} sub="Pending" color="text-purple-400" />
      </div>

      <div className="flex flex-wrap gap-2">
        <button className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-colors">
          <FileText size={16} />
          Generate Sitrep
        </button>
        <button className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-sm font-medium transition-colors">
          <Bell size={16} />
          Send Alert
        </button>
        <button
          onClick={() => setBriefingMode(!briefingMode)}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${briefingMode ? 'bg-yellow-600 text-white' : 'bg-slate-800 hover:bg-slate-700 text-slate-300'}`}
        >
          <Monitor size={16} />
          Briefing Mode
        </button>
        <button
          onClick={() => setWarRoom(!warRoom)}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${warRoom ? 'bg-purple-600 text-white' : 'bg-slate-800 hover:bg-slate-700 text-slate-300'}`}
        >
          <Radio size={16} />
          War Room
        </button>
        <button
          onClick={() => setTvDisplay(!tvDisplay)}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tvDisplay ? 'bg-teal-600 text-white' : 'bg-slate-800 hover:bg-slate-700 text-slate-300'}`}
        >
          <Tv size={16} />
          TV Display
        </button>
        <button className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm text-slate-300 transition-colors">
          <Download size={16} />
          Export
        </button>
      </div>

      <div className={`grid ${gridClass} gap-4`}>
        <Panel title="Overview" icon={Activity} loading={summaryLoading} error={!!summaryError}>
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 bg-slate-800 rounded-lg text-center">
              <p className="text-lg font-bold capitalize">{currentEvent?.status ?? '—'}</p>
              <p className="text-xs text-slate-400">Status</p>
            </div>
            <div className="p-3 bg-slate-800 rounded-lg text-center">
              <p className="text-lg font-bold capitalize">{currentEvent?.type?.replace(/_/g, ' ') ?? '—'}</p>
              <p className="text-xs text-slate-400">Type</p>
            </div>
            <div className="p-3 bg-slate-800 rounded-lg text-center">
              <p className="text-lg font-bold">{areas.length}</p>
              <p className="text-xs text-slate-400">Priority Areas</p>
            </div>
            <div className="p-3 bg-slate-800 rounded-lg text-center">
              <p className="text-lg font-bold">{teams.length}</p>
              <p className="text-xs text-slate-400">Field Teams</p>
            </div>
          </div>
          <div className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-500">Commander</span>
              <span className="text-slate-300">{user?.name ?? '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Start Time</span>
              <span className="text-slate-300">{currentEvent?.start_time ? new Date(currentEvent.start_time).toLocaleString() : '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Last Updated</span>
              <span className="text-slate-300">{summary?.last_updated ? new Date(summary.last_updated).toLocaleString() : '—'}</span>
            </div>
          </div>
        </Panel>

        <Panel title="Priority Areas" icon={ShieldAlert} loading={layersLoading} error={!!layersError} onRefresh={() => queryClient.invalidateQueries({ queryKey: ['map-layers', eventId] })}>
          {areas.length === 0 ? (
            <p className="text-slate-500 text-sm text-center py-4">No priority areas</p>
          ) : (
            <div className="space-y-2">
              {areas.slice(0, 8).map((a) => (
                <div key={a.id} className={`p-3 rounded-lg border ${severityBg[a.priority_level] ?? 'bg-slate-800 border-slate-700'}`}>
                  <div className="flex justify-between items-center">
                    <span className="text-sm font-medium">{a.area_name}</span>
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded ${severityColors[a.priority_level] ?? 'text-slate-400'} bg-black/20`}>
                      {a.priority_level}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1 line-clamp-2">{a.summary ?? 'No summary'}</p>
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Field Teams" icon={Users} loading={layersLoading} error={!!layersError} onRefresh={() => queryClient.invalidateQueries({ queryKey: ['map-layers', eventId] })}>
          {teams.length === 0 ? (
            <p className="text-slate-500 text-sm text-center py-4">No field teams deployed</p>
          ) : (
            <div className="space-y-2">
              {teams.map((team) => (
                <div key={team.id} className="p-3 bg-slate-800 rounded-lg">
                  <div className="flex justify-between items-center">
                    <span className="text-sm font-medium">{team.name}</span>
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${teamStatusColors[team.status] ?? 'bg-slate-700 text-slate-400'}`}>
                      {team.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-1 text-xs text-slate-400">
                    <span className="capitalize">{team.team_type}</span>
                    <span>•</span>
                    <MapPin size={12} />
                    <span>Lat {team.current_location.coordinates[1].toFixed(3)}, Lng {team.current_location.coordinates[0].toFixed(3)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Weather Snapshot" icon={Cloud} loading={summaryLoading || layersLoading} error={!!(summaryError || layersError)} onRefresh={() => queryClient.invalidateQueries({ queryKey: ['map-layers', eventId] })}>
          {/* There is no dedicated weather endpoint yet; show a friendly empty state. */}
          <div className="space-y-3">
            <p className="text-xs text-slate-500">Weather data is not provided by the current API.</p>
            <div className="grid grid-cols-3 gap-2">
              <div className="p-2 bg-slate-800 rounded-lg text-center">
                <Thermometer size={16} className="mx-auto text-orange-400 mb-1" />
                <p className="text-sm font-bold">—</p>
                <p className="text-xs text-slate-500">Temp</p>
              </div>
              <div className="p-2 bg-slate-800 rounded-lg text-center">
                <Wind size={16} className="mx-auto text-blue-400 mb-1" />
                <p className="text-sm font-bold">—</p>
                <p className="text-xs text-slate-500">Wind</p>
              </div>
              <div className="p-2 bg-slate-800 rounded-lg text-center">
                <Droplets size={16} className="mx-auto text-cyan-400 mb-1" />
                <p className="text-sm font-bold">—</p>
                <p className="text-xs text-slate-500">Precip</p>
              </div>
            </div>
          </div>
        </Panel>

        <Panel title="Open Tasks" icon={ClipboardList} loading={tasksLoading} error={!!tasksError} onRefresh={() => queryClient.invalidateQueries({ queryKey: ['tasks', eventId] })}>
          {sortedTasks.length === 0 ? (
            <p className="text-slate-500 text-sm text-center py-4">No open tasks</p>
          ) : (
            <div className="space-y-2">
              {sortedTasks.slice(0, 8).map((task) => (
                <div key={task.id} className={`p-3 rounded-lg border ${task.status === 'blocked' ? 'bg-red-500/5 border-red-500/20' : 'bg-slate-800 border-slate-700'}`}>
                  <div className="flex justify-between items-start">
                    <p className="text-sm font-medium">{task.title}</p>
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded ${severityColors[task.priority] ?? 'text-slate-400'} bg-black/20`}>
                      {task.priority}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1 line-clamp-2">{task.description}</p>
                  <div className="flex items-center gap-2 mt-1 text-xs text-slate-400">
                    <span className="capitalize">{task.status.replace(/_/g, ' ')}</span>
                    {task.assigned_team_id && (
                      <>
                        <span>•</span>
                        <Users size={12} />
                        <span>Team {task.assigned_team_id.slice(0, 8)}</span>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Critical Alerts" icon={AlertTriangle} loading={alertsLoading} error={!!alertsError} onRefresh={() => queryClient.invalidateQueries({ queryKey: ['alerts', eventId] })}>
          {(alerts ?? []).length === 0 ? (
            <p className="text-slate-500 text-sm text-center py-4">No critical alerts</p>
          ) : (
            <div className="space-y-2">
              {(alerts ?? []).slice(0, 6).map((alert) => (
                <div key={alert.id} className={`p-3 rounded-lg border ${alert.severity === 'critical' ? 'bg-red-500/10 border-red-500/20' : 'bg-amber-500/10 border-amber-500/20'}`}>
                  <div className="flex items-start gap-2">
                    {alert.severity === 'critical' ? (
                      <AlertTriangle size={16} className="text-red-400 mt-0.5 flex-shrink-0" />
                    ) : (
                      <Zap size={16} className="text-amber-400 mt-0.5 flex-shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-medium ${alert.severity === 'critical' ? 'text-red-400' : 'text-amber-400'}`}>{alert.title}</p>
                      <p className="text-xs text-slate-400 line-clamp-2">{alert.message}</p>
                      <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
                        <span className="capitalize">{alert.alert_type}</span>
                        <span>•</span>
                        <span>{alert.acknowledged ? 'Acknowledged' : 'Unacknowledged'}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Resources" icon={Package} loading={layersLoading} error={!!layersError} onRefresh={() => queryClient.invalidateQueries({ queryKey: ['map-layers', eventId] })}>
          {Object.keys(resourceCategories).length === 0 ? (
            <p className="text-slate-500 text-sm text-center py-4">No resource data</p>
          ) : (
            <div className="space-y-3">
              {Object.entries(resourceCategories).map(([cat, data]) => (
                <ResourceBar key={cat} label={cat} available={data.available} total={data.total} />
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Shelters" icon={Building2} loading={layersLoading} error={!!layersError} onRefresh={() => queryClient.invalidateQueries({ queryKey: ['map-layers', eventId] })}>
          {shelters.length === 0 ? (
            <p className="text-slate-500 text-sm text-center py-4">No shelter data</p>
          ) : (
            <div className="space-y-3">
              {shelters.map((s) => (
                <div key={s.id} className="p-3 bg-slate-800 rounded-lg">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-sm font-medium">{s.name}</span>
                    <span className={`text-xs px-2 py-0.5 rounded ${s.status === 'open' ? 'bg-green-500/10 text-green-400' : 'bg-slate-700 text-slate-400'}`}>
                      {s.status}
                    </span>
                  </div>
                  <OccupancyBar current={s.current_occupancy} capacity={s.total_capacity} label={`Capacity at ${s.name}`} />
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Timeline" icon={Calendar} loading={summaryLoading || layersLoading} error={!!(summaryError || layersError)}>
          {(alerts ?? []).length === 0 && (tasks ?? []).length === 0 ? (
            <p className="text-slate-500 text-sm text-center py-4">No events recorded</p>
          ) : (
            <div className="relative pl-4 space-y-3 before:absolute before:left-[7px] before:top-2 before:bottom-2 before:w-px before:bg-slate-700">
              {[
                ...(alerts ?? []).map((a) => ({ id: `alert-${a.id}`, timestamp: a.created_at, description: a.title, event_type: a.alert_type, actor: 'System' })),
                ...(tasks ?? []).map((t) => ({ id: `task-${t.id}`, timestamp: t.created_at, description: t.title, event_type: 'task', actor: t.assigned_team_id ? `Team ${t.assigned_team_id.slice(0, 8)}` : 'Unassigned' })),
              ]
                .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
                .slice(0, 10)
                .map((ev) => (
                  <div key={ev.id} className="relative">
                    <div className="absolute -left-4 top-1.5 w-3 h-3 rounded-full bg-slate-700 border-2 border-slate-600" />
                    <div className="ml-2">
                      <p className="text-xs text-slate-500">{new Date(ev.timestamp).toLocaleString()}</p>
                      <p className="text-sm text-slate-300">{ev.description}</p>
                      <p className="text-xs text-slate-500 capitalize">{ev.event_type} • {ev.actor}</p>
                    </div>
                  </div>
                ))}
            </div>
          )}
        </Panel>

        <Panel title="Pending Recommendations" icon={GitBranch} loading={recsLoading} error={!!recsError} onRefresh={() => queryClient.invalidateQueries({ queryKey: ['recommendations', eventId] })}>
          {sortedRecommendations.length === 0 ? (
            <p className="text-slate-500 text-sm text-center py-4">No pending recommendations</p>
          ) : (
            <div className="space-y-3">
              {sortedRecommendations.map((rec) => (
                <div key={rec.id} className={`p-3 rounded-lg border ${severityBg[rec.urgency] ?? 'bg-slate-800 border-slate-700'}`}>
                  <div className="flex justify-between items-start">
                    <p className="text-sm font-medium">{rec.title}</p>
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded ${severityColors[rec.urgency] ?? 'text-slate-400'} bg-black/20`}>
                      {rec.urgency}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1">{rec.description}</p>
                  <p className="text-xs text-slate-500 mt-1 line-clamp-1">{rec.reasoning}</p>
                  {eventId && <RecommendationActions rec={rec} eventId={eventId} />}
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}
