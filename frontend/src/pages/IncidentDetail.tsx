import { useState, useEffect, useCallback } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  eventsApi,
  tasksApi,
  sheltersApi,
  reportsApi,
  alertsApi,
  recommendationsApi,
  dashboardApi,
} from '../api/client'
import {
  AlertTriangle, ClipboardList, Building2, MapPin, Radio, FileText,
  ChevronRight, Pencil, Trash2, Copy, GitMerge, Scissors, Download,
  Plus, Send, Settings, ChevronLeft, Eye, X, Map as MapIcon, Layers,
  LayoutGrid, List,
} from 'lucide-react'
import { formatDistanceToNow, format } from 'date-fns'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { clsx, type ClassValue } from 'clsx'
import MapContainer from '../components/Map/MapContainer'
import { geometryCentroid } from '../lib/geo'
import type {
  DisasterEventRead,
  TaskRead,
  ShelterRead,
  AlertRead,
  IncidentReportRead,
  RecommendationRead,
  DashboardSummary,
} from '../types'

// TODO: backend has no event delete, merge/split, escalation, or alert-create endpoints.

const TABS = ['Overview', 'Tasks', 'Shelters', 'Map', 'Communications', 'Reports', 'Recommendations', 'Sub-Incidents', 'Settings'] as const
type Tab = (typeof TABS)[number]

const TAB_ICONS: Record<Tab, React.ElementType> = {
  Overview: Eye,
  Tasks: ClipboardList,
  Shelters: Building2,
  Map: MapIcon,
  Communications: Radio,
  Reports: FileText,
  Recommendations: AlertTriangle,
  'Sub-Incidents': Layers,
  Settings: Settings,
}

const severityColors: Record<string, string> = {
  low: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  medium: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  high: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
  critical: 'bg-red-500/10 text-red-400 border-red-500/20',
}

const statusColors: Record<string, string> = {
  active: 'bg-red-500/10 text-red-400',
  monitoring: 'bg-blue-500/10 text-blue-400',
  resolved: 'bg-green-500/10 text-green-400',
  archived: 'bg-slate-500/10 text-slate-400',
  closed: 'bg-slate-500/10 text-slate-400',
  merged: 'bg-purple-500/10 text-purple-400',
}

const priorityColors: Record<string, string> = {
  low: 'text-blue-400',
  medium: 'text-yellow-400',
  high: 'text-orange-400',
  critical: 'text-red-400',
}

const priorityBadge: Record<string, string> = {
  low: 'bg-blue-500/10 text-blue-400',
  medium: 'bg-yellow-500/10 text-yellow-400',
  high: 'bg-orange-500/10 text-orange-400',
  critical: 'bg-red-500/10 text-red-400',
}

const TASK_STATUSES: TaskRead['status'][] = [
  'assigned',
  'accepted',
  'en_route',
  'on_site',
  'completed',
  'blocked',
  'cancelled',
]

function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

function deriveSeverity(summary: DashboardSummary | undefined): string {
  if (!summary) return 'medium'
  if (summary.critical_areas > 0 || summary.alerts_active > 5) return 'critical'
  if (summary.high_areas > 0) return 'high'
  if (summary.medium_areas > 0) return 'medium'
  return 'low'
}

function eventCentroid(event: DisasterEventRead): [number, number] {
  if (event.affected_region) {
    try {
      return geometryCentroid(event.affected_region)
    } catch {
      // fall through to default
    }
  }
  return [77.59, 12.97]
}

function formatStatus(status: TaskRead['status']): string {
  return status.replace(/_/g, ' ')
}

interface EventMarkerProps {
  map: maplibregl.Map
  center: [number, number]
  title: string
}

function EventMarker({ map, center, title }: EventMarkerProps) {
  useEffect(() => {
    const marker = new maplibregl.Marker({ color: '#ef4444' })
      .setLngLat(center)
      .setPopup(new maplibregl.Popup().setHTML(`<strong>${title}</strong>`))
      .addTo(map)
    return () => {
      marker.remove()
    }
  }, [map, center, title])
  return null
}

export default function IncidentDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<Tab>('Overview')
  const [taskView, setTaskView] = useState<'list' | 'kanban'>('list')
  const [taskFilter, setTaskFilter] = useState('')
  const [showSendAlert, setShowSendAlert] = useState(false)
  const [alertForm, setAlertForm] = useState({ title: '', content: '', channel: 'sms' })

  const eventId = id ?? null

  const { data: incident, isLoading } = useQuery({
    queryKey: ['event', eventId],
    queryFn: () => eventsApi.get(eventId!),
    enabled: !!eventId,
  })

  const derivedEventId = incident?.id ?? null

  const { data: summary } = useQuery({
    queryKey: ['dashboard-summary', derivedEventId],
    queryFn: () => dashboardApi.summary(derivedEventId!),
    enabled: !!derivedEventId,
    refetchInterval: 15_000,
  })

  const { data: tasksData } = useQuery({
    queryKey: ['tasks', derivedEventId],
    queryFn: () => tasksApi.list(derivedEventId!, { limit: 200 }),
    enabled: !!derivedEventId && (activeTab === 'Tasks' || activeTab === 'Overview'),
    refetchInterval: 15_000,
  })

  const { data: sheltersData } = useQuery({
    queryKey: ['shelters', derivedEventId],
    queryFn: () => sheltersApi.list(derivedEventId!, { limit: 200 }),
    enabled: !!derivedEventId && (activeTab === 'Shelters' || activeTab === 'Overview'),
    refetchInterval: 15_000,
  })

  const { data: commsData } = useQuery({
    queryKey: ['alerts', derivedEventId],
    queryFn: () => alertsApi.list(derivedEventId!),
    enabled: !!derivedEventId && (activeTab === 'Communications' || activeTab === 'Overview'),
    refetchInterval: 15_000,
  })

  const { data: reportsData } = useQuery({
    queryKey: ['reports', derivedEventId],
    queryFn: () => reportsApi.list(derivedEventId!, { limit: 200 }),
    enabled: !!derivedEventId && (activeTab === 'Reports' || activeTab === 'Overview'),
    refetchInterval: 15_000,
  })

  const { data: recommendationsData } = useQuery({
    queryKey: ['recommendations', derivedEventId],
    queryFn: () => recommendationsApi.list(derivedEventId!, { limit: 200 }),
    enabled: !!derivedEventId && (activeTab === 'Recommendations' || activeTab === 'Overview'),
    refetchInterval: 15_000,
  })

  const { data: mapLayers } = useQuery({
    queryKey: ['map-layers', derivedEventId],
    queryFn: () => dashboardApi.mapLayers(derivedEventId!, { limit: 500 }),
    enabled: !!derivedEventId && activeTab === 'Map',
    refetchInterval: 15_000,
  })

  const deleteMutation = useMutation({
    mutationFn: async () => {
      // TODO: no backend endpoint for deleting events
      throw new Error('Event deletion is not supported by the current backend')
    },
  })

  const escalateMutation = useMutation({
    mutationFn: async () => {
      // TODO: no backend endpoint / field for escalation levels
      throw new Error('Escalation is not supported by the current backend')
    },
  })

  const cloneMutation = useMutation({
    mutationFn: async () => {
      if (!incident) throw new Error('Incident not loaded')
      return eventsApi.create({
        name: `${incident.name} (Copy)`,
        type: incident.type,
        status: incident.status,
        start_time: incident.start_time,
        description: incident.description ?? undefined,
        affected_region: incident.affected_region ?? undefined,
      })
    },
    onSuccess: (newEvent) => {
      queryClient.invalidateQueries({ queryKey: ['events'] })
      navigate(`/incidents/${newEvent.id}`)
    },
  })

  const sendAlertMutation = useMutation({
    mutationFn: async () => {
      // TODO: no backend endpoint for creating alerts
      throw new Error('Alert creation is not supported by the current backend')
    },
    onSuccess: () => {
      setShowSendAlert(false)
      setAlertForm({ title: '', content: '', channel: 'sms' })
    },
  })

  const handleAction = useCallback((label: string) => {
    if (label === 'Delete') {
      if (confirm('Delete this incident?')) deleteMutation.mutate()
    } else if (label === 'Escalate') {
      escalateMutation.mutate()
    } else if (label === 'Clone') {
      cloneMutation.mutate()
    } else if (label === 'Edit') {
      // TODO: edit page not yet ported
      navigate(`/incidents/${id}?edit=true`)
    } else if (label === 'Merge' || label === 'Split') {
      alert('Event merge/split is not supported by the current backend')
    }
  }, [deleteMutation, escalateMutation, cloneMutation, navigate, id])

  const severity = deriveSeverity(summary)
  const centroid = incident ? eventCentroid(incident) : ([77.59, 12.97] as [number, number])

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="h-8 w-64 bg-slate-800 rounded animate-pulse mb-6" />
        <div className="h-64 bg-slate-900 rounded-lg border border-slate-800 animate-pulse" />
      </div>
    )
  }

  if (!incident) {
    return (
      <div className="p-6">
        <p className="text-red-400">Incident not found.</p>
        <Link to="/incidents" className="text-sm text-slate-400 hover:text-white mt-2 inline-block">Back to incidents</Link>
      </div>
    )
  }

  const tasks = tasksData ?? []
  const filteredTasks = taskFilter ? tasks.filter((t) => t.status === taskFilter) : tasks
  const openTasks = tasks.filter((t) => t.status !== 'completed' && t.status !== 'cancelled').length
  const activeShelters = (sheltersData ?? []).filter((s) => s.status === 'open').length
  const alertsSent = (commsData ?? []).length

  return (
    <div className="p-6">
      <div className="mb-2">
        <Link to="/incidents" className="text-sm text-slate-500 hover:text-slate-300 flex items-center gap-1">
          <ChevronLeft size={14} /> Incidents
        </Link>
      </div>

      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-3 mb-2 flex-wrap">
            <h1 className="text-2xl font-bold">{incident.name}</h1>
            <span className={cn('px-2 py-1 rounded text-xs border', severityColors[severity] ?? '')}>{severity}</span>
            <span className={cn('px-2 py-1 rounded text-xs', statusColors[incident.status] ?? 'bg-slate-500/10 text-slate-400')}>
              {incident.status}
            </span>
            <span className="px-2 py-1 rounded text-xs bg-slate-700 text-slate-300 capitalize">{incident.type.replace(/_/g, ' ')}</span>
          </div>
          <p className="text-sm text-slate-400">
            Created {formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}
            {incident.updated_at !== incident.created_at && <> &middot; Updated {formatDistanceToNow(new Date(incident.updated_at), { addSuffix: true })}</>}
            <>{' '}&middot; <MapPin size={12} className="inline" />{' '}{incident.affected_region ? 'Affected region defined' : '—'}</>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/dashboard"
            className="flex items-center gap-1.5 px-3 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-white text-sm font-medium transition-colors"
          >
            Command Center <ChevronRight size={14} />
          </Link>
        </div>
      </div>

      <div className="flex items-center gap-1 mb-6 flex-wrap">
        {([
          ['Edit', Pencil],
          ['Escalate', AlertTriangle],
          ['Clone', Copy],
          ['Merge', GitMerge],
          ['Split', Scissors],
          ['Export', Download],
          ['Delete', Trash2],
        ] as [string, React.ElementType][]).map(([label, Icon]) => (
          <button
            key={label}
            onClick={() => handleAction(label)}
            disabled={cloneMutation.isPending || escalateMutation.isPending || deleteMutation.isPending}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50',
              label === 'Delete'
                ? 'bg-red-500/10 text-red-400 hover:bg-red-500/20'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700'
            )}
          >
            <Icon size={14} />{label}
          </button>
        ))}
      </div>
      {(deleteMutation.isError || escalateMutation.isError || cloneMutation.isError || sendAlertMutation.isError) && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-sm text-red-400">
          {(deleteMutation.error ?? escalateMutation.error ?? cloneMutation.error ?? sendAlertMutation.error)?.message}
        </div>
      )}

      <div className="flex gap-1 border-b border-slate-800 mb-6 overflow-x-auto">
        {TABS.map((tab) => {
          const Icon = TAB_ICONS[tab]
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 whitespace-nowrap transition-colors',
                activeTab === tab ? 'border-red-500 text-white' : 'border-transparent text-slate-400 hover:text-slate-200'
              )}
            >
              <Icon size={15} />{tab}
            </button>
          )
        })}
      </div>

      <div className="flex gap-6">
        <div className="flex-1 min-w-0">
          {activeTab === 'Overview' && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 space-y-6">
                <div className="bg-slate-900 rounded-lg border border-slate-800 p-4">
                  <h2 className="text-lg font-semibold mb-3">Description</h2>
                  <p className="text-slate-300 whitespace-pre-wrap">{incident.description || 'No description provided.'}</p>
                </div>
                <div className="bg-slate-900 rounded-lg border border-slate-800 p-4">
                  <h2 className="text-lg font-semibold mb-3">Metadata</h2>
                  <dl className="grid grid-cols-2 gap-3 text-sm">
                    <div><dt className="text-slate-500">Type</dt><dd className="capitalize mt-0.5">{incident.type.replace(/_/g, ' ')}</dd></div>
                    <div><dt className="text-slate-500">Severity</dt><dd className="mt-0.5"><span className={cn('px-2 py-0.5 rounded text-xs border', severityColors[severity])}>{severity}</span></dd></div>
                    <div><dt className="text-slate-500">Status</dt><dd className="mt-0.5"><span className={cn('px-2 py-0.5 rounded text-xs', statusColors[incident.status])}>{incident.status}</span></dd></div>
                    <div><dt className="text-slate-500">Start Time</dt><dd className="mt-0.5">{format(new Date(incident.start_time), 'PPp')}</dd></div>
                    <div><dt className="text-slate-500">Created</dt><dd className="mt-0.5">{format(new Date(incident.created_at), 'PPp')}</dd></div>
                    {incident.updated_at !== incident.created_at && <div><dt className="text-slate-500">Updated</dt><dd className="mt-0.5">{format(new Date(incident.updated_at), 'PPp')}</dd></div>}
                    <div><dt className="text-slate-500">Location</dt><dd className="mt-0.5">{incident.affected_region ? `${centroid[1].toFixed(4)}, ${centroid[0].toFixed(4)}` : '—'}</dd></div>
                  </dl>
                </div>
                <div className="bg-slate-900 rounded-lg border border-slate-800 p-4">
                  <h2 className="text-lg font-semibold mb-3">Timeline</h2>
                  <div className="space-y-3">
                    <div className="flex items-start gap-3">
                      <div className="w-2 h-2 mt-1.5 rounded-full bg-red-500 flex-shrink-0" />
                      <div>
                        <p className="text-sm font-medium">Incident created</p>
                        <p className="text-xs text-slate-500">{format(new Date(incident.created_at), 'PPp')}</p>
                      </div>
                    </div>
                    {incident.updated_at !== incident.created_at && (
                      <div className="flex items-start gap-3">
                        <div className="w-2 h-2 mt-1.5 rounded-full bg-blue-500 flex-shrink-0" />
                        <div>
                          <p className="text-sm font-medium">Last updated</p>
                          <p className="text-xs text-slate-500">{format(new Date(incident.updated_at), 'PPp')}</p>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
              <div className="space-y-6">
                <div className="bg-slate-900 rounded-lg border border-slate-800 p-4">
                  <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">Quick Stats</h2>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-slate-400">Open Tasks</span>
                      <span className="text-lg font-bold">{openTasks}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-slate-400">Active Shelters</span>
                      <span className="text-lg font-bold">{activeShelters}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-slate-400">Alerts Sent</span>
                      <span className="text-lg font-bold">{alertsSent}</span>
                    </div>
                  </div>
                </div>
                <div className="bg-slate-900 rounded-lg border border-slate-800 p-4">
                  <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">Recommendations</h2>
                  {(recommendationsData ?? []).length === 0 ? (
                    <p className="text-slate-500 text-sm">No recommendations</p>
                  ) : (
                    <div className="space-y-2">
                      {(recommendationsData ?? []).slice(0, 4).map((rec) => (
                        <div key={rec.id} className="text-sm text-slate-300 truncate">{rec.title}</div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'Tasks' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <select
                    value={taskFilter}
                    onChange={(e) => setTaskFilter(e.target.value)}
                    className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none"
                  >
                    <option value="">All Statuses</option>
                    {TASK_STATUSES.map((s) => (
                      <option key={s} value={s}>{formatStatus(s)}</option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => setTaskView('list')} className={cn('p-1.5 rounded', taskView === 'list' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300')}><List size={16} /></button>
                  <button onClick={() => setTaskView('kanban')} className={cn('p-1.5 rounded', taskView === 'kanban' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300')}><LayoutGrid size={16} /></button>
                  <button className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 rounded-lg text-white text-sm font-medium transition-colors"><Plus size={14} />New Task</button>
                </div>
              </div>
              {taskView === 'list' ? (
                <div className="space-y-2">
                  {filteredTasks.length === 0 ? (
                    <div className="p-8 text-center text-slate-500 bg-slate-900 rounded-lg border border-slate-800">No tasks found.</div>
                  ) : (
                    filteredTasks.map((task) => (
                      <div key={task.id} className="bg-slate-900 rounded-lg border border-slate-800 p-4 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <ClipboardList className={priorityColors[task.priority] ?? 'text-slate-400'} size={18} />
                          <div>
                            <p className="font-medium">{task.title}</p>
                            <p className="text-xs text-slate-500">
                              {formatStatus(task.status)}{' '}
                              {task.updated_at && `· Updated ${format(new Date(task.updated_at), 'PP')}`}
                            </p>
                          </div>
                        </div>
                        <span className={cn('text-xs px-2 py-1 rounded', priorityBadge[task.priority] ?? 'bg-slate-700 text-slate-400')}>{task.priority}</span>
                      </div>
                    ))
                  )}
                </div>
              ) : (
                <div className="grid grid-cols-3 md:grid-cols-4 gap-4">
                  {TASK_STATUSES.map((col) => {
                    const colTasks = filteredTasks.filter((t) => t.status === col)
                    return (
                      <div key={col} className="bg-slate-900 rounded-lg border border-slate-800 p-3">
                        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3 flex items-center justify-between">
                          {formatStatus(col)}<span className="bg-slate-800 px-1.5 py-0.5 rounded-full">{colTasks.length}</span>
                        </h3>
                        <div className="space-y-2 min-h-[60px]">
                          {colTasks.map((task) => (
                            <div key={task.id} className="p-2.5 bg-slate-800 rounded-lg border-l-2 border-l-slate-600">
                              <p className="text-sm font-medium truncate">{task.title}</p>
                              <span className={cn('text-xs', priorityColors[task.priority])}>{task.priority}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {activeTab === 'Shelters' && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {(sheltersData ?? []).length === 0 ? (
                <div className="col-span-full p-8 text-center text-slate-500 bg-slate-900 rounded-lg border border-slate-800">No shelters linked to this event.</div>
              ) : (
                (sheltersData ?? []).map((shelter) => {
                  const pct = shelter.total_capacity > 0
                    ? Math.min(100, (shelter.current_occupancy / shelter.total_capacity) * 100)
                    : 0
                  const barColor = pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-yellow-500' : 'bg-green-500'
                  return (
                    <div key={shelter.id} className="bg-slate-900 rounded-lg border border-slate-800 p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <Building2 size={18} className="text-green-500" />
                        <h3 className="font-semibold">{shelter.name}</h3>
                        <span className={cn(
                          'ml-auto text-xs px-2 py-0.5 rounded capitalize',
                          shelter.status === 'open' ? 'bg-green-500/10 text-green-400' : 'bg-slate-700 text-slate-400'
                        )}>{shelter.status}</span>
                      </div>
                      <div className="flex justify-between text-sm mb-1.5">
                        <span className="text-slate-400">Capacity</span>
                        <span className="font-medium">{shelter.current_occupancy} / {shelter.total_capacity}</span>
                      </div>
                      <div className="w-full h-2.5 bg-slate-800 rounded-full overflow-hidden">
                        <div className={cn('h-full rounded-full transition-all', barColor)} style={{ width: `${pct}%` }} />
                      </div>
                      <p className="text-right text-xs text-slate-500 mt-1">{pct.toFixed(0)}% full</p>
                    </div>
                  )
                })
              )}
            </div>
          )}

          {activeTab === 'Map' && (
            <div className="bg-slate-900 rounded-lg border border-slate-800 overflow-hidden h-[500px]">
              <MapContainer>
                {(map) => <EventMarker map={map} center={centroid} title={incident.name} />}
              </MapContainer>
            </div>
          )}

          {activeTab === 'Communications' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Alert History</h2>
                <button
                  onClick={() => setShowSendAlert(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 rounded-lg text-white text-sm font-medium transition-colors"
                ><Send size={14} />Send Alert</button>
              </div>
              {(commsData ?? []).length === 0 ? (
                <div className="p-8 text-center text-slate-500 bg-slate-900 rounded-lg border border-slate-800">No alerts for this event.</div>
              ) : (
                (commsData ?? []).map((comm) => (
                  <div key={comm.id} className="bg-slate-900 rounded-lg border border-slate-800 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Radio size={16} className="text-blue-500" />
                        <span className="font-medium">{comm.title}</span>
                      </div>
                      <span className={cn('text-xs px-2 py-1 rounded capitalize', severityColors[comm.severity])}>{comm.severity}</span>
                    </div>
                    <p className="text-sm text-slate-300 line-clamp-2">{comm.message}</p>
                    <div className="flex gap-3 mt-2 text-xs text-slate-500">
                      <span className="capitalize">{comm.alert_type.replace(/_/g, ' ')}</span>
                      <span>&middot;</span>
                      <span>{format(new Date(comm.created_at), 'PPp')}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'Reports' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Reports</h2>
                <button className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 rounded-lg text-white text-sm font-medium transition-colors"><Plus size={14} />Generate Report</button>
              </div>
              {(reportsData ?? []).length === 0 ? (
                <div className="p-8 text-center text-slate-500 bg-slate-900 rounded-lg border border-slate-800">No reports for this event.</div>
              ) : (
                (reportsData ?? []).map((report) => (
                  <div key={report.id} className="bg-slate-900 rounded-lg border border-slate-800 p-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <FileText size={18} className="text-purple-500" />
                      <div className="min-w-0">
                        <p className="font-medium truncate">{report.description}</p>
                        <p className="text-xs text-slate-500 capitalize">{report.report_category.replace(/_/g, ' ')}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 flex-shrink-0">
                      <span className="text-xs px-2 py-1 bg-slate-800 rounded capitalize">{report.verification_status}</span>
                      <span className="text-xs text-slate-500">{format(new Date(report.created_at), 'PP')}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'Recommendations' && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Recommendations</h2>
              {(recommendationsData ?? []).length === 0 ? (
                <div className="p-8 text-center text-slate-500 bg-slate-900 rounded-lg border border-slate-800">No recommendations for this event.</div>
              ) : (
                (recommendationsData ?? []).map((rec) => (
                  <div key={rec.id} className="bg-slate-900 rounded-lg border border-slate-800 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium">{rec.title}</span>
                      <span className={cn('text-xs px-2 py-1 rounded capitalize', severityColors[rec.urgency])}>{rec.urgency}</span>
                    </div>
                    <p className="text-sm text-slate-300 line-clamp-2">{rec.description}</p>
                    <div className="flex gap-3 mt-2 text-xs text-slate-500">
                      <span className="capitalize">{rec.recommendation_type.replace(/_/g, ' ')}</span>
                      <span>&middot;</span>
                      <span className="capitalize">{rec.status}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'Sub-Incidents' && (
            <div className="p-8 text-center text-slate-500 bg-slate-900 rounded-lg border border-slate-800">
              <Layers size={32} className="mx-auto mb-2 text-slate-600" />
              <p>Sub-incidents are not supported by the current backend.</p>
            </div>
          )}

          {activeTab === 'Settings' && (
            <div className="bg-slate-900 rounded-lg border border-slate-800 p-6 max-w-xl">
              <h2 className="text-lg font-semibold mb-4">Incident Settings</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Status</label>
                  <select defaultValue={incident.status} className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-red-500">
                    {(['active', 'monitoring', 'resolved', 'archived'] as const).map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Type</label>
                  <select disabled defaultValue={incident.type} className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none disabled:opacity-50">
                    <option value={incident.type}>{incident.type.replace(/_/g, ' ')}</option>
                  </select>
                  <p className="text-xs text-slate-500 mt-1">Event type cannot be changed.</p>
                </div>
                <p className="text-sm text-amber-400/80 bg-amber-950/30 border border-amber-700/40 rounded p-3">
                  Full settings mutation not implemented — event patching is available in the API client but not wired here.
                </p>
                <button className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-white text-sm font-medium transition-colors">Save Changes</button>
              </div>
            </div>
          )}
        </div>

        <div className="w-64 flex-shrink-0 space-y-4 hidden lg:block">
          <div className="bg-slate-900 rounded-lg border border-slate-800 p-4">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Quick Stats</h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">Open Tasks</span>
                <span className="text-lg font-bold">{openTasks}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">Active Shelters</span>
                <span className="text-lg font-bold">{activeShelters}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">Alerts Sent</span>
                <span className="text-lg font-bold">{alertsSent}</span>
              </div>
            </div>
          </div>
          <div className="bg-slate-900 rounded-lg border border-slate-800 p-4">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Last Updated</h3>
            <p className="text-sm">{formatDistanceToNow(new Date(incident.updated_at), { addSuffix: true })}</p>
          </div>
        </div>
      </div>

      {showSendAlert && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={(e) => { if (e.target === e.currentTarget) setShowSendAlert(false); }}>
          <div className="w-full max-w-md bg-slate-900 rounded-lg border border-slate-800 shadow-2xl">
            <div className="flex items-center justify-between p-4 border-b border-slate-800">
              <h2 className="text-lg font-semibold">Send Alert</h2>
              <button onClick={() => setShowSendAlert(false)} className="text-slate-400 hover:text-white"><X size={20} /></button>
            </div>
            <form onSubmit={(e) => { e.preventDefault(); sendAlertMutation.mutate(); }} className="p-4 space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Title</label>
                <input
                  value={alertForm.title}
                  onChange={(e) => setAlertForm({ ...alertForm, title: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-red-500"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Content</label>
                <textarea
                  value={alertForm.content}
                  onChange={(e) => setAlertForm({ ...alertForm, content: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-red-500 h-24 resize-none"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Channel</label>
                <select
                  value={alertForm.channel}
                  onChange={(e) => setAlertForm({ ...alertForm, channel: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-red-500"
                >
                  {['sms', 'email', 'push', 'radio', 'social_media'].map((c) => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
                </select>
              </div>
              <div className="bg-amber-950/30 border border-amber-700/40 rounded p-2 text-xs text-amber-200/80">
                Alert creation is not supported by the current backend.
              </div>
              <div className="flex justify-end gap-3">
                <button type="button" onClick={() => setShowSendAlert(false)} className="px-4 py-2 text-slate-400 hover:text-white text-sm">Cancel</button>
                <button type="submit" disabled={sendAlertMutation.isPending} className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-white text-sm font-medium disabled:opacity-50">
                  {sendAlertMutation.isPending ? 'Sending...' : 'Send'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
