import React, { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/AuthContext'
import { eventsApi, sheltersApi } from '../api/client'
import type { ShelterRead, ShelterStatus } from '../types'
import {
  Building2,
  Users,
  Accessibility,
  Stethoscope,
  Search,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  CheckCircle,
} from 'lucide-react'

type SortField = 'name' | 'capacity' | 'occupancy' | 'status'
type SortDir = 'asc' | 'desc'

const STATUS_STYLES: Record<ShelterStatus, string> = {
  open: 'bg-green-500/10 text-green-400 border-green-500/20',
  full: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  closed: 'bg-red-500/10 text-red-400 border-red-500/20',
  evacuated: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
}

function getOccupancyColor(pct: number): string {
  if (pct >= 90) return 'bg-red-500'
  if (pct >= 70) return 'bg-yellow-500'
  return 'bg-green-500'
}

function SortIcon({ field, sortField, sortDir }: { field: SortField; sortField: SortField; sortDir: SortDir }) {
  if (sortField !== field) return <span className="text-slate-600 ml-1">&#8693;</span>
  return sortDir === 'asc' ? <span className="text-slate-300 ml-1">&#8593;</span> : <span className="text-slate-300 ml-1">&#8595;</span>
}

export default function Shelters() {
  const { user } = useAuth()
  const queryClient = useQueryClient()

  // ── Event selection ──────────────────────────────────────────────────────
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

  // ── List state ───────────────────────────────────────────────────────────
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [sortField, setSortField] = useState<SortField>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  // ── Data ─────────────────────────────────────────────────────────────────
  const { data: shelters, isLoading, error } = useQuery({
    queryKey: ['shelters', eventId],
    queryFn: () => sheltersApi.list(eventId!),
    enabled: !!eventId,
    staleTime: 15_000,
  })

  const patchMutation = useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string
      data: { status: ShelterStatus; current_occupancy: number }
    }) => sheltersApi.patchStatus(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shelters', eventId] })
    },
  })

  const filtered = useMemo(() => {
    let list = shelters ?? []
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter((s) => s.name.toLowerCase().includes(q))
    }
    if (statusFilter) {
      list = list.filter((s) => s.status === statusFilter)
    }
    list = [...list].sort((a, b) => {
      let cmp = 0
      if (sortField === 'capacity') {
        cmp = a.total_capacity - b.total_capacity
      } else if (sortField === 'occupancy') {
        cmp = a.current_occupancy - b.current_occupancy
      } else if (sortField === 'status') {
        cmp = a.status.localeCompare(b.status)
      } else {
        cmp = a.name.localeCompare(b.name)
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
    return list
  }, [shelters, search, statusFilter, sortField, sortDir])

  function handleSort(field: SortField) {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  const currentEvent = events?.find((e) => e.id === eventId)

  if (isLoading) {
    return (
      <div className="p-6 space-y-4">
        <div className="h-8 w-40 bg-slate-800 rounded animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-slate-900 rounded-lg border border-slate-800 p-4 animate-pulse space-y-3">
              <div className="h-5 w-32 bg-slate-800 rounded" />
              <div className="h-2 w-full bg-slate-800 rounded-full" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-6">Shelters</h1>
        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400">
          Failed to load shelters.
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-4">
      {/* ── Header ───────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Shelters</h1>

          <select
            value={eventId ?? ''}
            onChange={(e) => setEventId(e.target.value)}
            className="text-sm bg-slate-800 border border-slate-700 rounded px-2 py-1 text-white focus:outline-none focus:border-red-500"
          >
            {!events && <option value="">Loading events…</option>}
            {events?.map((ev) => (
              <option key={ev.id} value={ev.id}>
                {ev.name} ({ev.status})
              </option>
            ))}
          </select>

          {currentEvent && (
            <span className="text-sm px-2 py-0.5 bg-slate-800 rounded-full text-slate-400">
              {(shelters ?? []).length}
            </span>
          )}
        </div>

        <span className="text-xs text-slate-400">
          {user?.name} · <span className="text-slate-300">{user?.role?.replace('_', ' ')}</span>
        </span>
      </div>

      {/* ── Filters ──────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3 bg-slate-900 rounded-lg border border-slate-800 p-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search shelters..."
            className="w-full pl-9 pr-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500"
          />
        </div>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500"
        >
          <option value="">All Statuses</option>
          <option value="open">Open</option>
          <option value="full">Full</option>
          <option value="closed">Closed</option>
          <option value="evacuated">Evacuated</option>
        </select>

        <div className="flex items-center gap-1 bg-slate-800 rounded-lg border border-slate-700 p-0.5">
          {(
            [
              ['name', 'Name'],
              ['capacity', 'Capacity'],
              ['occupancy', 'Occupancy'],
              ['status', 'Status'],
            ] as [SortField, string][]
          ).map(([field, label]) => (
            <button
              key={field}
              onClick={() => handleSort(field)}
              className={`flex items-center px-3 py-1.5 rounded text-xs transition-colors ${
                sortField === field ? 'bg-red-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              {label} <SortIcon field={field} sortField={sortField} sortDir={sortDir} />
            </button>
          ))}
        </div>
      </div>

      {patchMutation.isSuccess && (
        <div className="p-3 bg-green-500/10 border border-green-500/20 rounded-lg text-green-400 text-sm flex items-center gap-2">
          <CheckCircle size={14} />
          Shelter updated successfully.
        </div>
      )}

      {patchMutation.isError && (
        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
          Failed to update shelter.
        </div>
      )}

      {/* ── Cards ──────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((shelter) => {
          const pct = shelter.total_capacity > 0 ? Math.round((shelter.current_occupancy / shelter.total_capacity) * 100) : 0
          const isExpanded = expandedId === shelter.id
          return (
            <div
              key={shelter.id}
              className="bg-slate-900 rounded-lg border border-slate-800 p-4 hover:border-slate-700 transition-colors"
            >
              <div className="flex items-start justify-between mb-3">
                <div
                  className="flex items-center gap-2 cursor-pointer"
                  onClick={() => setExpandedId(isExpanded ? null : shelter.id)}
                >
                  <Building2 size={18} className="text-green-500" />
                  <h3 className="font-semibold">{shelter.name}</h3>
                  {isExpanded ? (
                    <ChevronDown size={14} className="text-slate-500" />
                  ) : (
                    <ChevronRight size={14} className="text-slate-500" />
                  )}
                </div>
                <span
                  className={`text-xs px-2 py-0.5 rounded border capitalize ${
                    STATUS_STYLES[shelter.status] ?? 'bg-slate-500/10 text-slate-400 border-slate-500/20'
                  }`}
                >
                  {shelter.status}
                </span>
              </div>

              <div className="mb-3">
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-slate-400 flex items-center gap-1">
                    <Users size={14} /> Capacity
                  </span>
                  <span className="font-medium">
                    {shelter.current_occupancy} / {shelter.total_capacity}
                  </span>
                </div>
                <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${getOccupancyColor(pct)}`}
                    style={{ width: `${Math.min(100, pct)}%` }}
                  />
                </div>
                <p className="text-xs text-slate-500 mt-1 text-right">{pct}% occupied</p>
              </div>

              <div className="flex gap-2 flex-wrap mb-2">
                {shelter.accessibility_support && (
                  <span className="flex items-center gap-1 text-xs text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded">
                    <Accessibility size={12} /> Accessible
                  </span>
                )}
                {shelter.medical_support && (
                  <span className="flex items-center gap-1 text-xs text-red-400 bg-red-500/10 px-2 py-0.5 rounded">
                    <Stethoscope size={12} /> Medical
                  </span>
                )}
              </div>

              {pct >= 90 && (
                <div className="flex items-center gap-2 p-2 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-xs">
                  <AlertTriangle size={14} />
                  <span>Overcrowding alert: shelter is at {pct}% capacity</span>
                </div>
              )}

              {isExpanded && (
                <div className="mt-4 pt-4 border-t border-slate-800 space-y-3">
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-slate-500">Available</span>
                      <p className="text-slate-300">{shelter.available_capacity}</p>
                    </div>
                    <div>
                      <span className="text-slate-500">Food</span>
                      <p className="capitalize text-slate-300">{shelter.food_status}</p>
                    </div>
                    <div>
                      <span className="text-slate-500">Water</span>
                      <p className="capitalize text-slate-300">{shelter.water_status}</p>
                    </div>
                    <div>
                      <span className="text-slate-500">Updated</span>
                      <p className="text-slate-300">
                        {new Date(shelter.updated_at).toLocaleString()}
                      </p>
                    </div>
                  </div>

                  <ShelterEditForm
                    shelter={shelter}
                    isPending={patchMutation.isPending}
                    onSave={(data) => {
                      patchMutation.mutate({ id: shelter.id, data })
                    }}
                  />
                </div>
              )}
            </div>
          )
        })}
        {filtered.length === 0 && (
          <div className="col-span-full p-8 text-center text-slate-500 bg-slate-900 rounded-lg border border-slate-800">
            No shelters found.
          </div>
        )}
      </div>
    </div>
  )
}

function ShelterEditForm({
  shelter,
  isPending,
  onSave,
}: {
  shelter: ShelterRead
  isPending: boolean
  onSave: (data: { status: ShelterStatus; current_occupancy: number }) => void
}) {
  const [status, setStatus] = useState<ShelterStatus>(shelter.status)
  const [occupancy, setOccupancy] = useState(String(shelter.current_occupancy))

  // Reset when the underlying shelter changes after a successful update
  useEffect(() => {
    setStatus(shelter.status)
    setOccupancy(String(shelter.current_occupancy))
  }, [shelter.status, shelter.current_occupancy])

  const occupancyNum = Number(occupancy)
  const isInvalid = Number.isNaN(occupancyNum) || occupancyNum < 0 || occupancyNum > shelter.total_capacity

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-slate-500 mb-1">Status</label>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as ShelterStatus)}
            className="w-full px-2 py-1.5 bg-slate-800 border border-slate-700 rounded text-sm text-slate-100 focus:outline-none focus:border-red-500"
          >
            <option value="open">Open</option>
            <option value="full">Full</option>
            <option value="closed">Closed</option>
            <option value="evacuated">Evacuated</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Current Occupancy</label>
          <input
            type="number"
            min={0}
            max={shelter.total_capacity}
            value={occupancy}
            onChange={(e) => setOccupancy(e.target.value)}
            className="w-full px-2 py-1.5 bg-slate-800 border border-slate-700 rounded text-sm text-slate-100 focus:outline-none focus:border-red-500"
          />
        </div>
      </div>
      {isInvalid && (
        <p className="text-xs text-red-400">
          Occupancy must be between 0 and {shelter.total_capacity}.
        </p>
      )}
      <button
        onClick={() => onSave({ status, current_occupancy: isInvalid ? shelter.current_occupancy : occupancyNum })}
        disabled={isPending || isInvalid}
        className="px-3 py-1.5 bg-red-600 hover:bg-red-700 disabled:opacity-50 rounded text-white text-xs transition-colors"
      >
        {isPending ? 'Saving…' : 'Update Shelter'}
      </button>
    </div>
  )
}
