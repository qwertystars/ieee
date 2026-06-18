import { useEffect, useMemo, useState, type ElementType } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { eventsApi } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { DisasterEventRead, EventStatus, DisasterType } from '../types'
import {
  Plus, X, Search, ChevronUp, ChevronDown, Eye, Pencil, Trash2,
  Flame, Droplets, Wind, Mountain, Waves, Tornado, CloudLightning, TriangleAlert,
  Layers, Snowflake, Sun, Thermometer, ThermometerSnowflake, Factory,
  FlaskConical, Atom, Bug, Building, Skull, Shield, ChevronLeft, ChevronRight,
  ChevronsUpDown, Calendar,
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

const DISASTER_TYPES = [
  'flood', 'earthquake', 'fire', 'hurricane', 'landslide', 'other',
] as const

const STATUSES = ['active', 'monitoring', 'resolved', 'archived'] as const

const TYPE_ICONS: Record<string, ElementType> = {
  fire: Flame,
  flood: Droplets,
  hurricane: Wind,
  earthquake: Mountain,
  landslide: Layers,
  other: TriangleAlert,
}

const TYPE_COLORS: Record<string, string> = {
  fire: 'border-orange-500/40 bg-orange-500/10 text-orange-400',
  flood: 'border-blue-500/40 bg-blue-500/10 text-blue-400',
  hurricane: 'border-cyan-500/40 bg-cyan-500/10 text-cyan-400',
  earthquake: 'border-amber-500/40 bg-amber-500/10 text-amber-400',
  landslide: 'border-yellow-600/40 bg-yellow-600/10 text-yellow-500',
  other: 'border-slate-400/40 bg-slate-400/10 text-slate-300',
}

const statusColors: Record<string, string> = {
  active: 'bg-red-500/10 text-red-400',
  monitoring: 'bg-yellow-500/10 text-yellow-400',
  resolved: 'bg-green-500/10 text-green-400',
  archived: 'bg-slate-500/10 text-slate-400',
}

type SortField = 'name' | 'type' | 'status' | 'created_at'
type SortDir = 'asc' | 'desc'

export default function Incidents() {
  useAuth()
  const queryClient = useQueryClient()

  // ── Event selection (event-scoped data) ─────────────────────────────────
  const [eventId, setEventId] = useState<string | null>(null)
  const { data: events, isLoading: eventsLoading } = useQuery({
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

  // ── Local State ──────────────────────────────────────────────────────────
  const [showCreate, setShowCreate] = useState(false)
  const [typeFilter, setTypeFilter] = useState<DisasterType | ''>('')
  const [statusFilter, setStatusFilter] = useState<EventStatus | ''>('')
  const [search, setSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [sortField, setSortField] = useState<SortField>('created_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  // ── Data queries ─────────────────────────────────────────────────────────
  const { data: incidents, isLoading } = useQuery<DisasterEventRead[]>({
    queryKey: ['events', eventId],
    queryFn: () => eventsApi.list({ limit: 200 }),
    enabled: true,
    staleTime: 30_000,
  })

  const createMutation = useMutation({
    mutationFn: () =>
      // TODO: no backend equivalent for direct event creation from this page
      Promise.reject(new Error('Create incident not supported by current backend')),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['events'] })
      closeCreate()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => eventsApi.patch(id, { status: 'archived' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['events'] }),
  })

  function closeCreate() {
    setShowCreate(false)
  }

  function handleSort(field: SortField) {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  const filtered = useMemo(() => {
    let list = incidents ?? []
    if (search) list = list.filter((i) => i.name.toLowerCase().includes(search.toLowerCase()))
    if (typeFilter) list = list.filter((i) => i.type === typeFilter)
    if (statusFilter) list = list.filter((i) => i.status === statusFilter)
    if (dateFrom) list = list.filter((i) => new Date(i.created_at) >= new Date(dateFrom))
    if (dateTo) list = list.filter((i) => new Date(i.created_at) <= new Date(dateTo + 'T23:59:59'))
    list = [...list].sort((a, b) => {
      let cmp = 0
      if (sortField === 'created_at') {
        cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      } else {
        cmp = String(a[sortField] ?? '').localeCompare(String(b[sortField] ?? ''))
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
    return list
  }, [incidents, search, typeFilter, statusFilter, dateFrom, dateTo, sortField, sortDir])

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const paged = filtered.slice((page - 1) * pageSize, page * pageSize)

  function SortIcon({ field }: { field: SortField }) {
    if (sortField !== field) return <ChevronsUpDown size={14} className="text-slate-600" />
    return sortDir === 'asc' ? <ChevronUp size={14} className="text-slate-300" /> : <ChevronDown size={14} className="text-slate-300" />
  }

  if (isLoading || eventsLoading) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-6">Incidents</h1>
        <div className="space-y-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-14 bg-slate-900 rounded-lg border border-slate-800 animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Incidents</h1>
          <span className="text-sm px-2 py-0.5 bg-slate-800 rounded-full text-slate-400">{filtered.length}</span>
        </div>

        {/* Event selector */}
        <div className="flex items-center gap-3">
          <select
            value={eventId ?? ''}
            onChange={(e) => setEventId(e.target.value)}
            className="text-sm bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white focus:outline-none focus:border-gray-500 min-w-[180px]"
          >
            {!events && <option value="">Loading events…</option>}
            {events?.map((ev) => (
              <option key={ev.id} value={ev.id}>
                {ev.name} ({ev.status})
              </option>
            ))}
          </select>

          {currentEvent && (
            <span
              className={`text-xs px-2 py-1 rounded-full ${
                currentEvent.status === 'active'
                  ? 'bg-red-600 text-white animate-pulse'
                  : 'bg-gray-700 text-gray-300'
              }`}
            >
              {currentEvent.status.toUpperCase()}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between">
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-white text-sm font-medium transition-colors"
        >
          <Plus size={18} />
          Create Incident
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3 bg-slate-900 rounded-lg border border-slate-800 p-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            placeholder="Search by name..."
            className="w-full pl-9 pr-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500"
          />
        </div>
        <select
          value={typeFilter}
          onChange={(e) => { setTypeFilter(e.target.value as DisasterType | ''); setPage(1) }}
          className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500"
        >
          <option value="">All Types</option>
          {DISASTER_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value as EventStatus | ''); setPage(1) }}
          className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500"
        >
          <option value="">All Statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <div className="flex items-center gap-1">
          <Calendar size={14} className="text-slate-500" />
          <input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1) }} className="px-2 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500" />
          <span className="text-slate-500 text-xs">to</span>
          <input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1) }} className="px-2 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500" />
        </div>
      </div>

      <div className="bg-slate-900 rounded-lg border border-slate-800 overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-slate-800">
              {([['name', 'Name'], ['type', 'Type'], ['status', 'Status']] as [SortField, string][]).map(([f, label]) => (
                <th key={f} className="text-left p-4">
                  <button onClick={() => handleSort(f)} className="flex items-center gap-1 text-slate-400 font-medium text-sm hover:text-slate-200 transition-colors">
                    {label} <SortIcon field={f} />
                  </button>
                </th>
              ))}
              <th className="text-left p-4">
                <button onClick={() => handleSort('created_at')} className="flex items-center gap-1 text-slate-400 font-medium text-sm hover:text-slate-200 transition-colors">
                  Created <SortIcon field="created_at" />
                </button>
              </th>
              <th className="text-left p-4 text-slate-400 font-medium text-sm">Region</th>
              <th className="text-left p-4 text-slate-400 font-medium text-sm">Actions</th>
            </tr>
          </thead>
          <tbody>
            {paged.map((incident) => (
              <tr key={incident.id} className="border-b border-slate-800 hover:bg-slate-800/50 transition-colors">
                <td className="p-4">
                  <Link to={`/incidents/${incident.id}`} className="text-red-400 hover:underline font-medium">
                    {incident.name}
                  </Link>
                </td>
                <td className="p-4">
                  <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs border ${TYPE_COLORS[incident.type] ?? 'bg-slate-500/10 text-slate-400 border-slate-500/20'}`}>
                    {(() => { const I = TYPE_ICONS[incident.type]; return I ? <I size={12} /> : null })()}
                    {incident.type}
                  </span>
                </td>
                <td className="p-4">
                  <span className={`px-2 py-1 rounded text-xs ${statusColors[incident.status] ?? 'bg-slate-500/10 text-slate-400'}`}>
                    {incident.status}
                  </span>
                </td>
                <td className="p-4 text-sm text-slate-400" title={new Date(incident.created_at).toLocaleString()}>
                  {formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}
                </td>
                <td className="p-4 text-sm text-slate-300">{incident.affected_region ? 'Defined' : '—'}</td>
                <td className="p-4">
                  <div className="flex items-center gap-1">
                    <Link to={`/incidents/${incident.id}`} className="p-1.5 rounded hover:bg-slate-700 text-slate-400 hover:text-white transition-colors" title="View">
                      <Eye size={16} />
                    </Link>
                    <Link to={`/incidents/${incident.id}?edit=true`} className="p-1.5 rounded hover:bg-slate-700 text-slate-400 hover:text-white transition-colors" title="Edit">
                      <Pencil size={16} />
                    </Link>
                    <button onClick={() => { if (confirm('Archive this incident?')) deleteMutation.mutate(incident.id) }} className="p-1.5 rounded hover:bg-slate-700 text-slate-400 hover:text-red-400 transition-colors" title="Archive">
                      <Trash2 size={16} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {paged.length === 0 && (
              <tr>
                <td colSpan={6} className="p-8 text-center text-slate-500">No incidents found</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <span>Show</span>
          <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1) }} className="px-2 py-1 bg-slate-800 border border-slate-700 rounded text-sm text-slate-100 focus:outline-none">
            {[10, 20, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <span>of {filtered.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
            <ChevronLeft size={16} />
          </button>
          <span className="text-sm text-slate-400">Page {page} of {totalPages}</span>
          <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={(e) => { if (e.target === e.currentTarget) closeCreate() }}>
          <div className="w-full max-w-xl bg-slate-900 rounded-lg border border-slate-800 shadow-2xl p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Create Incident</h2>
              <button onClick={closeCreate} className="text-slate-400 hover:text-white"><X size={20} /></button>
            </div>
            <p className="text-sm text-slate-400">
              // TODO: no backend equivalent — incident creation is not supported by the current events API.
              This feature is stubbed.
            </p>
            {createMutation.isError && (
              <p className="text-red-400 text-sm">Failed to create incident. This feature is not available.</p>
            )}
            <div className="flex justify-end">
              <button onClick={closeCreate} className="px-4 py-2 text-slate-400 hover:text-white text-sm transition-colors">Close</button>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
