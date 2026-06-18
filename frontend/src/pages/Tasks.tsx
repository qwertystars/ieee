import { useState, useMemo, useCallback, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { tasksApi, teamsApi, eventsApi, recommendationsApi } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type {
  TaskRead,
  TaskCreate,
  TaskUpdate,
  TaskStatus,
  Urgency,
  ResponseTeamRead,
  DisasterEventRead,
  RecommendationRead,
} from '../types'
import {
  AlertTriangle,
  Clock,
  CheckCircle2,
  XCircle,
  GripVertical,
  LayoutGrid,
  Table,
  Plus,
  Search,
  Filter,
  X,
  ChevronUp,
  ChevronDown,
  MapPin,
  Loader2,
  MessageSquare,
  Upload,
} from 'lucide-react'

const ALL_STATUSES: TaskStatus[] = [
  'assigned',
  'accepted',
  'en_route',
  'on_site',
  'completed',
  'blocked',
  'cancelled',
]

const COLUMNS: {
  key: TaskStatus
  label: string
  statuses: TaskStatus[]
  icon: typeof Clock
  color: string
  headerBg: string
  headerBorder: string
}[] = [
  {
    key: 'assigned',
    label: 'Open',
    statuses: ['assigned', 'accepted', 'blocked'],
    icon: Clock,
    color: 'text-blue-400',
    headerBg: 'bg-blue-500/10',
    headerBorder: 'border-blue-500/30',
  },
  {
    key: 'en_route',
    label: 'In Progress',
    statuses: ['en_route', 'on_site'],
    icon: AlertTriangle,
    color: 'text-amber-400',
    headerBg: 'bg-amber-500/10',
    headerBorder: 'border-amber-500/30',
  },
  {
    key: 'completed',
    label: 'Completed',
    statuses: ['completed'],
    icon: CheckCircle2,
    color: 'text-green-400',
    headerBg: 'bg-green-500/10',
    headerBorder: 'border-green-500/30',
  },
  {
    key: 'cancelled',
    label: 'Cancelled',
    statuses: ['cancelled'],
    icon: XCircle,
    color: 'text-gray-400',
    headerBg: 'bg-gray-500/10',
    headerBorder: 'border-gray-500/30',
  },
]

const PRIORITIES: Urgency[] = ['critical', 'high', 'medium', 'low']

const priorityColors: Record<Urgency, string> = {
  low: 'border-l-blue-500',
  medium: 'border-l-blue-400',
  high: 'border-l-amber-500',
  critical: 'border-l-red-500',
}

const priorityBadge: Record<Urgency, string> = {
  low: 'bg-blue-500/10 text-blue-400',
  medium: 'bg-blue-400/10 text-blue-300',
  high: 'bg-amber-500/10 text-amber-400',
  critical: 'bg-red-500/10 text-red-400',
}

const priorityDot: Record<Urgency, string> = {
  low: 'bg-blue-500',
  medium: 'bg-blue-400',
  high: 'bg-amber-500',
  critical: 'bg-red-500',
}

const statusBadge: Record<TaskStatus, string> = {
  assigned: 'bg-blue-500/10 text-blue-400',
  accepted: 'bg-blue-400/10 text-blue-300',
  en_route: 'bg-amber-500/10 text-amber-400',
  on_site: 'bg-orange-500/10 text-orange-400',
  completed: 'bg-green-500/10 text-green-400',
  blocked: 'bg-red-500/10 text-red-400',
  cancelled: 'bg-gray-500/10 text-gray-400',
}

function getInitials(name: string | null | undefined): string {
  if (!name) return '?'
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
}

function Avatar({ name, size = 'sm' }: { name: string | null | undefined; size?: 'sm' | 'md' }) {
  const initials = getInitials(name)
  const sz = size === 'sm' ? 'w-6 h-6 text-[10px]' : 'w-8 h-8 text-xs'
  return (
    <div
      className={`${sz} rounded-full bg-slate-700 text-slate-300 flex items-center justify-center font-medium flex-shrink-0`}
    >
      {initials}
    </div>
  )
}

function DetailField({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode
  label: string
  value: string
}) {
  return (
    <div className="p-2 bg-slate-800/50 rounded-lg">
      <div className="flex items-center gap-1.5 text-xs text-slate-500 mb-0.5">
        {icon}
        {label}
      </div>
      <p className="text-sm text-slate-300">{value}</p>
    </div>
  )
}

function SortableHeader({
  field,
  label,
  sortField,
  sortDir,
  onSort,
}: {
  field: string
  label: string
  sortField: string
  sortDir: 'asc' | 'desc'
  onSort: (f: string) => void
}) {
  const active = sortField === field
  return (
    <th
      className={`text-left p-3 text-xs uppercase tracking-wide cursor-pointer select-none ${
        active ? 'text-slate-200 font-semibold' : 'text-slate-400 font-medium'
      }`}
      onClick={() => onSort(field)}
    >
      <div className="flex items-center gap-1">
        {label}
        {active &&
          (sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
      </div>
    </th>
  )
}

function TaskCard({
  task,
  teamName,
  onDragStart,
  onClick,
}: {
  task: TaskRead
  teamName: string | null
  onDragStart: (id: string, e: React.DragEvent) => void
  onClick: () => void
}) {
  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(task.id, e)}
      onClick={onClick}
      className={`p-3 bg-slate-800 rounded-lg border-l-2 ${
        priorityColors[task.priority] ?? 'border-l-slate-600'
      } cursor-grab active:cursor-grabbing hover:bg-slate-800/80 transition-colors group`}
    >
      <div className="flex items-start gap-2">
        <GripVertical
          size={14}
          className="text-slate-600 mt-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
        />
        <div className="flex-1 min-w-0">
          <p className="font-medium text-sm text-slate-200 truncate">{task.title}</p>
          <div className="flex items-center gap-2 mt-2">
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded capitalize ${
                priorityBadge[task.priority] ?? 'bg-slate-700 text-slate-400'
              }`}
            >
              {task.priority}
            </span>
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded capitalize ${
                statusBadge[task.status] ?? 'bg-slate-700 text-slate-400'
              }`}
            >
              {task.status.replace(/_/g, ' ')}
            </span>
          </div>
          <div className="flex items-center justify-between mt-2">
            <Avatar name={teamName} />
          </div>
        </div>
      </div>
    </div>
  )
}

function CreateTaskModal({
  onClose,
  eventId,
  teams,
  recommendations,
}: {
  onClose: () => void
  eventId: string
  teams: ResponseTeamRead[]
  recommendations: RecommendationRead[]
}) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<{
    title: string
    description: string
    priority: Urgency
    assigned_team_id: string
    recommendation_id: string
    location_lat: string
    location_lng: string
  }>({
    title: '',
    description: '',
    priority: 'medium',
    assigned_team_id: '',
    recommendation_id: '',
    location_lat: '',
    location_lng: '',
  })

  const createMutation = useMutation({
    mutationFn: (body: TaskCreate) => tasksApi.create(eventId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tasks', eventId] })
      onClose()
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const lat = parseFloat(form.location_lat)
    const lng = parseFloat(form.location_lng)
    if (Number.isNaN(lat) || Number.isNaN(lng)) return

    const body: TaskCreate = {
      event_id: eventId,
      title: form.title,
      description: form.description,
      priority: form.priority,
      location: { type: 'Point', coordinates: [lng, lat] },
    }
    if (form.assigned_team_id) body.assigned_team_id = form.assigned_team_id
    if (form.recommendation_id) body.recommendation_id = form.recommendation_id
    createMutation.mutate(body)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="w-full max-w-lg bg-slate-900 rounded-lg border border-slate-800 shadow-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center p-4 border-b border-slate-800">
          <h2 className="text-lg font-semibold">Create Task</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X size={20} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">Title *</label>
            <input
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-red-500"
              required
            />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Description *</label>
            <textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-red-500 h-20 resize-none"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">Priority</label>
              <select
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: e.target.value as Urgency })}
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-red-500"
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p} className="capitalize">
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Assign Team</label>
              <select
                value={form.assigned_team_id}
                onChange={(e) => setForm({ ...form, assigned_team_id: e.target.value })}
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-red-500"
              >
                <option value="">Unassigned</option>
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Recommendation</label>
            <select
              value={form.recommendation_id}
              onChange={(e) => setForm({ ...form, recommendation_id: e.target.value })}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-red-500"
            >
              <option value="">None</option>
              {recommendations.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.title}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">Latitude *</label>
              <input
                type="number"
                step="any"
                value={form.location_lat}
                onChange={(e) => setForm({ ...form, location_lat: e.target.value })}
                placeholder="e.g. 28.6139"
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-red-500"
                required
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Longitude *</label>
              <input
                type="number"
                step="any"
                value={form.location_lng}
                onChange={(e) => setForm({ ...form, location_lng: e.target.value })}
                placeholder="e.g. 77.2090"
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-red-500"
                required
              />
            </div>
          </div>
          {createMutation.isError && (
            <p className="text-red-400 text-sm">Failed to create task. Please try again.</p>
          )}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-slate-400 hover:text-white">
              Cancel
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending || !form.title}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-white disabled:opacity-50 flex items-center gap-2"
            >
              {createMutation.isPending && <Loader2 size={14} className="animate-spin" />}
              {createMutation.isPending ? 'Creating...' : 'Create Task'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function TaskDetailSidebar({
  task,
  onClose,
  teams,
  events,
}: {
  task: TaskRead
  onClose: () => void
  teams: ResponseTeamRead[]
  events: DisasterEventRead[]
}) {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<'details' | 'comments' | 'attachments' | 'activity'>('details')
  const [editMode, setEditMode] = useState(false)
  const [editForm, setEditForm] = useState({
    status: task.status,
    assigned_team_id: task.assigned_team_id ?? '',
    description: task.description,
  })

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [onClose])

  const updateMutation = useMutation({
    mutationFn: (body: TaskUpdate) => tasksApi.patch(task.id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
      setEditMode(false)
    },
  })

  const handleSaveEdit = () => {
    const body: TaskUpdate = {
      status: editForm.status,
      description: editForm.description || undefined,
    }
    if (editForm.assigned_team_id) body.assigned_team_id = editForm.assigned_team_id
    updateMutation.mutate(body)
  }

  const handleStatusChange = (newStatus: TaskStatus) => {
    updateMutation.mutate({ status: newStatus })
  }

  const tabs = [
    { key: 'details', label: 'Details' },
    { key: 'comments', label: 'Comments' },
    { key: 'attachments', label: 'Attachments' },
    { key: 'activity', label: 'Activity' },
  ] as const

  const assignedTeamName = teams.find((t) => t.id === task.assigned_team_id)?.name ?? 'Unassigned'
  const eventName = events.find((e) => e.id === task.event_id)?.name ?? '—'

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} />
      <div
        className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-md bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4 border-b border-slate-800">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${priorityDot[task.priority]}`} />
              <span className={`text-xs px-2 py-0.5 rounded capitalize ${priorityBadge[task.priority]}`}>
                {task.priority}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded capitalize ${statusBadge[task.status]}`}>
                {task.status.replace(/_/g, ' ')}
              </span>
            </div>
            <button onClick={onClose} className="text-slate-400 hover:text-white">
              <X size={20} />
            </button>
          </div>
          <h2 className="text-lg font-semibold text-slate-100">{task.title}</h2>

          <div className="flex items-center gap-1.5 mt-3">
            <span className="text-xs text-slate-500 mr-1">Move to:</span>
            {ALL_STATUSES.filter((s) => s !== task.status).map((s) => (
              <button
                key={s}
                onClick={() => handleStatusChange(s)}
                className="px-2 py-1 text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300 rounded transition-colors capitalize"
              >
                {s.replace(/_/g, ' ')}
              </button>
            ))}
          </div>
        </div>

        <div className="flex border-b border-slate-800 px-4">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`px-3 py-2.5 text-xs font-medium border-b-2 transition-colors ${
                activeTab === t.key
                  ? 'border-red-500 text-white'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {activeTab === 'details' && (
            <div className="space-y-4">
              {editMode ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Status</label>
                      <select
                        value={editForm.status}
                        onChange={(e) =>
                          setEditForm({ ...editForm, status: e.target.value as TaskStatus })
                        }
                        className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none"
                      >
                        {ALL_STATUSES.map((s) => (
                          <option key={s} value={s}>
                            {s.replace(/_/g, ' ')}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Assign Team</label>
                      <select
                        value={editForm.assigned_team_id}
                        onChange={(e) =>
                          setEditForm({ ...editForm, assigned_team_id: e.target.value })
                        }
                        className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none"
                      >
                        <option value="">Unassigned</option>
                        {teams.map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Description</label>
                    <textarea
                      value={editForm.description}
                      onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                      className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500 h-20 resize-none"
                    />
                  </div>
                  <div className="flex gap-2 pt-2">
                    <button
                      onClick={handleSaveEdit}
                      disabled={updateMutation.isPending}
                      className="px-3 py-1.5 bg-red-600 hover:bg-red-700 rounded-lg text-sm text-white disabled:opacity-50"
                    >
                      {updateMutation.isPending ? 'Saving...' : 'Save'}
                    </button>
                    <button
                      onClick={() => setEditMode(false)}
                      className="px-3 py-1.5 text-sm text-slate-400 hover:text-white"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <button
                    onClick={() => setEditMode(true)}
                    className="px-3 py-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg"
                  >
                    Edit Details
                  </button>

                  {task.description && (
                    <div>
                      <h3 className="text-xs text-slate-500 uppercase tracking-wide mb-1">
                        Description
                      </h3>
                      <p className="text-sm text-slate-300 whitespace-pre-wrap">{task.description}</p>
                    </div>
                  )}

                  <div className="grid grid-cols-2 gap-3">
                    <DetailField
                      icon={<Clock size={13} />}
                      label="Status"
                      value={task.status.replace(/_/g, ' ')}
                    />
                    <DetailField icon={<Clock size={13} />} label="Assignee" value={assignedTeamName} />
                    <DetailField icon={<MapPin size={13} />} label="Event" value={eventName} />
                    <DetailField
                      icon={<MapPin size={13} />}
                      label="Location"
                      value={`${task.location.coordinates[1].toFixed(4)}, ${task.location.coordinates[0].toFixed(4)}`}
                    />
                  </div>

                  {task.recommendation_id && (
                    <p className="text-xs text-slate-500">
                      Linked recommendation: {task.recommendation_id}
                    </p>
                  )}
                </>
              )}
            </div>
          )}

          {activeTab === 'comments' && (
            <>
              {/* TODO: no backend equivalent */}
              <div className="space-y-4">
                <p className="text-sm text-slate-400">Comments are not available in this version.</p>
                <div className="flex gap-2">
                  <input
                    disabled
                    placeholder="Add a comment..."
                    className="flex-1 px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500 disabled:opacity-40"
                  />
                  <button
                    disabled
                    className="px-3 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-white text-sm disabled:opacity-40"
                  >
                    <MessageSquare size={16} />
                  </button>
                </div>
              </div>
            </>
          )}

          {activeTab === 'attachments' && (
            <div className="space-y-4">
              {/* TODO: no backend equivalent */}
              <p className="text-sm text-slate-400">Attachments are not available in this version.</p>
              <div className="border-2 border-dashed border-slate-700 rounded-lg p-6 text-center">
                <Upload size={24} className="mx-auto text-slate-600 mb-2" />
                <p className="text-sm text-slate-400">Feature not available</p>
              </div>
            </div>
          )}

          {activeTab === 'activity' && (
            <div className="space-y-3">
              {/* TODO: no backend equivalent */}
              <div className="p-3 bg-slate-800 rounded-lg">
                <p className="text-xs text-slate-500">Activity log is not available in this version.</p>
              </div>
              <div className="text-xs text-slate-600">
                <p>Created: {new Date(task.created_at).toLocaleString()}</p>
                <p>Updated: {new Date(task.updated_at).toLocaleString()}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

export default function Tasks() {
  useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()

  const [eventId, setEventId] = useState<string | null>(null)

  const [view, setView] = useState<'kanban' | 'table'>('kanban')
  const [draggedTask, setDraggedTask] = useState<string | null>(null)
  const [dragOverCol, setDragOverCol] = useState<TaskStatus | null>(null)
  const [showFilters, setShowFilters] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [selectedTask, setSelectedTask] = useState<TaskRead | null>(null)
  const [sortField, setSortField] = useState<string>('created_at')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const searchQuery = searchParams.get('search') ?? ''
  const filterPriority = (searchParams.get('priority') as Urgency | '') ?? ''
  const filterStatus = (searchParams.get('status') as TaskStatus | '') ?? ''
  const filterTeam = searchParams.get('team') ?? ''

  const setParam = useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(searchParams)
      if (value) next.set(key, value)
      else next.delete(key)
      setSearchParams(next, { replace: true })
    },
    [searchParams, setSearchParams]
  )

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

  const { data: tasks, isLoading } = useQuery({
    queryKey: ['tasks', eventId],
    queryFn: () => tasksApi.list(eventId!, { limit: 200 }),
    enabled: !!eventId,
  })

  const { data: teams } = useQuery({
    queryKey: ['teams', eventId],
    queryFn: () => teamsApi.list(eventId!, { limit: 200 }),
    enabled: !!eventId,
  })

  const { data: recommendations } = useQuery({
    queryKey: ['recommendations', eventId],
    queryFn: () => recommendationsApi.list(eventId!, { limit: 200 }),
    enabled: !!eventId,
  })

  const teamList = teams ?? []
  const eventList = events ?? []
  const recommendationList = recommendations ?? []

  const teamName = useCallback(
    (id: string | null) => teamList.find((t) => t.id === id)?.name ?? null,
    [teamList]
  )

  const updateMutation = useMutation({
    mutationFn: ({ taskId, body }: { taskId: string; body: TaskUpdate }) =>
      tasksApi.patch(taskId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
  })

  const filteredTasks = useMemo(() => {
    const list = tasks ?? []
    return list.filter((t) => {
      if (searchQuery && !t.title.toLowerCase().includes(searchQuery.toLowerCase())) return false
      if (filterPriority && t.priority !== filterPriority) return false
      if (filterStatus && t.status !== filterStatus) return false
      if (filterTeam && t.assigned_team_id !== filterTeam) return false
      return true
    })
  }, [tasks, searchQuery, filterPriority, filterStatus, filterTeam])

  const grouped = useMemo(() => {
    return COLUMNS.reduce<Record<string, TaskRead[]>>((acc, col) => {
      acc[col.key] = filteredTasks.filter((t) => col.statuses.includes(t.status))
      return acc
    }, {})
  }, [filteredTasks])

  const sortedTasks = useMemo(() => {
    const sorted = [...filteredTasks]
    sorted.sort((a, b) => {
      let cmp = 0
      switch (sortField) {
        case 'title':
          cmp = a.title.localeCompare(b.title)
          break
        case 'priority':
          cmp =
            PRIORITIES.indexOf(a.priority ?? 'low') -
            PRIORITIES.indexOf(b.priority ?? 'low')
          break
        case 'status':
          cmp = a.status.localeCompare(b.status)
          break
        case 'team':
          cmp = (teamName(a.assigned_team_id) ?? '').localeCompare(
            teamName(b.assigned_team_id) ?? ''
          )
          break
        case 'created_at':
          cmp = a.created_at.localeCompare(b.created_at)
          break
        default:
          cmp = 0
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
    return sorted
  }, [filteredTasks, sortField, sortDir, teamName])

  const handleDragStart = useCallback((taskId: string, e: React.DragEvent) => {
    setDraggedTask(taskId)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', taskId)
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const handleDragEnter = useCallback((colKey: TaskStatus) => {
    setDragOverCol(colKey)
  }, [])

  const handleDragLeave = useCallback(() => {
    setDragOverCol(null)
  }, [])

  const handleDrop = useCallback(
    (status: TaskStatus) => {
      if (draggedTask) {
        updateMutation.mutate({ taskId: draggedTask, body: { status } })
        setDraggedTask(null)
        setDragOverCol(null)
      }
    },
    [draggedTask, updateMutation]
  )

  const toggleSort = useCallback(
    (field: string) => {
      if (sortField === field) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
      } else {
        setSortField(field)
        setSortDir('asc')
      }
    },
    [sortField]
  )

  const hasActiveFilters = filterPriority || filterStatus || filterTeam

  if (isLoading) {
    return (
      <div className="p-6 bg-gray-950 text-white h-full">
        <h1 className="text-2xl font-bold mb-6">Tasks</h1>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {COLUMNS.map((col) => (
            <div key={col.key} className="bg-slate-900 rounded-lg border border-slate-800 p-4">
              <div className="h-6 w-24 bg-slate-800 rounded animate-pulse mb-4" />
              <div className="space-y-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="h-20 bg-slate-800 rounded-lg animate-pulse" />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 flex flex-col h-full bg-gray-950 text-white">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold">Tasks</h1>
          <span className="text-sm text-slate-400">
            {filteredTasks.length} of {tasks?.length ?? 0} tasks
          </span>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={eventId ?? ''}
            onChange={(e) => setEventId(e.target.value)}
            className="text-sm bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white focus:outline-none focus:border-gray-500"
          >
            {!events && <option value="">Loading events…</option>}
            {events?.map((ev) => (
              <option key={ev.id} value={ev.id}>
                {ev.name} ({ev.status})
              </option>
            ))}
          </select>
          <button
            onClick={() => setShowCreateModal(true)}
            disabled={!eventId}
            className="flex items-center gap-2 px-3 py-1.5 bg-red-600 hover:bg-red-700 disabled:opacity-40 rounded-lg text-white text-sm"
          >
            <Plus size={16} />
            New Task
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="flex items-center bg-slate-900 rounded-lg border border-slate-800 p-0.5">
          <button
            onClick={() => setView('kanban')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm ${
              view === 'kanban'
                ? 'bg-slate-800 text-white'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <LayoutGrid size={15} />
            Board
          </button>
          <button
            onClick={() => setView('table')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm ${
              view === 'table'
                ? 'bg-slate-800 text-white'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Table size={15} />
            Table
          </button>
        </div>

        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={searchQuery}
            onChange={(e) => setParam('search', e.target.value)}
            placeholder="Search tasks..."
            className="w-full pl-9 pr-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-slate-600"
          />
        </div>

        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border ${
            showFilters || hasActiveFilters
              ? 'bg-slate-800 border-slate-600 text-white'
              : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200'
          }`}
        >
          <Filter size={15} />
          Filters
          {hasActiveFilters && (
            <span className="w-4 h-4 bg-red-500 text-white text-[10px] rounded-full flex items-center justify-center">
              {[filterPriority, filterStatus, filterTeam].filter(Boolean).length}
            </span>
          )}
        </button>
      </div>

      {showFilters && (
        <div className="flex flex-wrap items-center gap-3 mb-4 p-3 bg-slate-900 border border-slate-800 rounded-lg">
          <select
            value={filterPriority}
            onChange={(e) => setParam('priority', e.target.value)}
            className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none"
          >
            <option value="">All Priorities</option>
            {PRIORITIES.map((p) => (
              <option key={p} value={p} className="capitalize">
                {p}
              </option>
            ))}
          </select>
          <select
            value={filterStatus}
            onChange={(e) => setParam('status', e.target.value)}
            className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none"
          >
            <option value="">All Statuses</option>
            {ALL_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
          <select
            value={filterTeam}
            onChange={(e) => setParam('team', e.target.value)}
            className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none"
          >
            <option value="">All Teams</option>
            {teamList.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          {hasActiveFilters && (
            <button
              onClick={() => {
                setParam('priority', '')
                setParam('status', '')
                setParam('team', '')
              }}
              className="px-3 py-1.5 text-sm text-slate-400 hover:text-white"
            >
              Clear
            </button>
          )}
        </div>
      )}

      {view === 'kanban' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 flex-1 min-h-0">
          {COLUMNS.map((col) => {
            const Icon = col.icon
            const columnTasks = grouped[col.key] ?? []
            const isDragOver = dragOverCol === col.key
            return (
              <div
                key={col.key}
                className={`bg-slate-900 rounded-lg border flex flex-col transition-colors ${
                  isDragOver ? 'border-slate-500' : 'border-slate-800'
                }`}
                onDragOver={handleDragOver}
                onDragEnter={() => handleDragEnter(col.key)}
                onDragLeave={handleDragLeave}
                onDrop={() => handleDrop(col.key)}
              >
                <div
                  className={`flex items-center gap-2 p-3 rounded-t-lg border-b ${col.headerBg} ${col.headerBorder}`}
                >
                  <Icon size={16} className={col.color} />
                  <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wide">
                    {col.label}
                  </h2>
                  <span className="ml-auto text-xs bg-slate-800/60 px-2 py-0.5 rounded-full text-slate-400">
                    {columnTasks.length}
                  </span>
                </div>
                <div className="space-y-2 p-3 flex-1 min-h-[120px] overflow-y-auto">
                  {columnTasks.map((task) => (
                    <TaskCard
                      key={task.id}
                      task={task}
                      teamName={teamName(task.assigned_team_id)}
                      onDragStart={handleDragStart}
                      onClick={() => setSelectedTask(task)}
                    />
                  ))}
                  {columnTasks.length === 0 && (
                    <div className="p-4 text-center text-slate-600 text-xs border border-dashed border-slate-800 rounded-lg">
                      Drag tasks here
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="bg-slate-900 rounded-lg border border-slate-800 overflow-hidden flex-1">
          <div className="overflow-auto h-full">
            <table className="w-full">
              <thead className="sticky top-0 bg-slate-900 z-10">
                <tr className="border-b border-slate-800">
                  <SortableHeader field="title" label="Title" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
                  <SortableHeader field="priority" label="Priority" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
                  <SortableHeader field="status" label="Status" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
                  <SortableHeader field="team" label="Team" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
                  <SortableHeader field="created_at" label="Created" sortField={sortField} sortDir={sortDir} onSort={toggleSort} />
                </tr>
              </thead>
              <tbody>
                {sortedTasks.map((task) => (
                  <tr
                    key={task.id}
                    className="border-b border-slate-800 hover:bg-slate-800/50 cursor-pointer"
                    onClick={() => setSelectedTask(task)}
                  >
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${priorityDot[task.priority]}`} />
                        <span className="text-sm font-medium text-slate-200 truncate max-w-[200px]">
                          {task.title}
                        </span>
                      </div>
                    </td>
                    <td className="p-3">
                      <span
                        className={`text-xs px-2 py-0.5 rounded capitalize ${
                          priorityBadge[task.priority] ?? 'bg-slate-700 text-slate-400'
                        }`}
                      >
                        {task.priority}
                      </span>
                    </td>
                    <td className="p-3">
                      <span
                        className={`text-xs px-2 py-0.5 rounded capitalize ${
                          statusBadge[task.status] ?? 'bg-slate-700 text-slate-400'
                        }`}
                      >
                        {task.status.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <Avatar name={teamName(task.assigned_team_id)} />
                        <span className="text-sm text-slate-300 truncate max-w-[120px]">
                          {teamName(task.assigned_team_id) ?? '—'}
                        </span>
                      </div>
                    </td>
                    <td className="p-3 text-xs text-slate-500">
                      {new Date(task.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
                {sortedTasks.length === 0 && (
                  <tr>
                    <td colSpan={5} className="p-8 text-center text-slate-500">
                      No tasks found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showCreateModal && eventId && (
        <CreateTaskModal
          onClose={() => setShowCreateModal(false)}
          eventId={eventId}
          teams={teamList}
          recommendations={recommendationList}
        />
      )}

      {selectedTask && (
        <TaskDetailSidebar
          task={selectedTask}
          onClose={() => setSelectedTask(null)}
          teams={teamList}
          events={eventList}
        />
      )}

      {/* TODO: no backend equivalent — removed: task swimlanes, WIP limits, geofence auto-completion,
          task auto-assignment, task auto-prioritization, task dependencies, task templates,
          task batch creation, task risk/impact/urgency scores, bulk status update, comments, attachments. */}
    </div>
  )
}
