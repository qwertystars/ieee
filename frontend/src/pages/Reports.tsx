import { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FileText, ChevronDown, ChevronRight, Download, Eye, Plus, X,
  Send, MessageSquare, Search, Calendar, ArrowUpCircle, Loader2,
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { eventsApi, reportsApi } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { IncidentReportRead, Urgency, VerificationStatus } from '../types'

const URGENCY_ORDER: Record<Urgency, number> = { low: 0, medium: 1, high: 2, critical: 3 }

const CATEGORY_LABELS: Record<string, string> = {
  trapped_person: 'Trapped Person',
  road_blocked: 'Road Blocked',
  flooding: 'Flooding',
  power_outage: 'Power Outage',
  shelter_need: 'Shelter Need',
  medical_emergency: 'Medical Emergency',
  infrastructure_damage: 'Infrastructure Damage',
  other: 'Other',
}

const REPORTER_LABELS: Record<string, string> = {
  citizen: 'Citizen',
  field_responder: 'Field Responder',
  automated_sensor: 'Automated Sensor',
  official: 'Official',
}

const urgencyColors: Record<Urgency, string> = {
  low: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  medium: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  high: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
  critical: 'bg-red-500/10 text-red-400 border-red-500/20',
}

const verificationColors: Record<VerificationStatus, string> = {
  unverified: 'bg-slate-500/10 text-slate-400',
  low: 'bg-yellow-500/10 text-yellow-400',
  medium: 'bg-blue-500/10 text-blue-400',
  high: 'bg-green-500/10 text-green-400',
}

export default function Reports() {
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
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [showGenerate, setShowGenerate] = useState(false)
  const [showComments, setShowComments] = useState<string | null>(null)
  const [commentText, setCommentText] = useState('')
  const [search, setSearch] = useState('')
  const [verificationFilter, setVerificationFilter] = useState<VerificationStatus | ''>('')
  const [categoryFilter, setCategoryFilter] = useState<string>('')
  const [urgencyFilter, setUrgencyFilter] = useState<Urgency | ''>('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const [form, setForm] = useState({
    category: 'flooding',
    title: '',
    description: '',
  })

  // ── Data queries ─────────────────────────────────────────────────────────
  const { data: reports, isLoading, error } = useQuery<IncidentReportRead[]>({
    queryKey: ['reports', eventId],
    queryFn: () => reportsApi.list(eventId!, { limit: 200 }),
    enabled: !!eventId,
    staleTime: 30_000,
  })

  const verifyMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: VerificationStatus }) =>
      reportsApi.verify(id, { verification_status: status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['reports', eventId] }),
  })

  const generateMutation = useMutation({
    mutationFn: () =>
      // TODO: no backend equivalent for AI/sectioned report generation
      Promise.reject(new Error('Report generation is not supported by the current backend')),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reports', eventId] })
      closeGenerate()
    },
  })

  function closeGenerate() {
    setShowGenerate(false)
    setForm({ category: 'flooding', title: '', description: '' })
  }

  const filtered = useMemo(() => {
    let list = reports ?? []
    if (search) list = list.filter((r) => r.description.toLowerCase().includes(search.toLowerCase()))
    if (verificationFilter) list = list.filter((r) => r.verification_status === verificationFilter)
    if (categoryFilter) list = list.filter((r) => r.report_category === categoryFilter)
    if (urgencyFilter) list = list.filter((r) => r.urgency === urgencyFilter)
    if (dateFrom) list = list.filter((r) => new Date(r.created_at) >= new Date(dateFrom))
    if (dateTo) list = list.filter((r) => new Date(r.created_at) <= new Date(dateTo + 'T23:59:59'))
    list = [...list].sort((a, b) => {
      const aUrgency = URGENCY_ORDER[a.urgency] ?? 0
      const bUrgency = URGENCY_ORDER[b.urgency] ?? 0
      if (aUrgency !== bUrgency) return bUrgency - aUrgency
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })
    return list
  }, [reports, search, verificationFilter, categoryFilter, urgencyFilter, dateFrom, dateTo])

  function getNextVerification(status: VerificationStatus): VerificationStatus | null {
    const flow: VerificationStatus[] = ['unverified', 'low', 'medium', 'high']
    const idx = flow.indexOf(status)
    return idx >= 0 && idx < flow.length - 1 ? flow[idx + 1] : null
  }

  const demoComments: { id: string; report_id: string; user: string; content: string; created_at: string }[] = []

  if (isLoading || eventsLoading) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-6">Reports</h1>
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-16 bg-slate-900 rounded-lg border border-slate-800 animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-6">Reports</h1>
        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400">
          Failed to load reports.
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Reports</h1>
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
          onClick={() => setShowGenerate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-white text-sm transition-colors"
        >
          <Plus size={16} /> Generate Report
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3 bg-slate-900 rounded-lg border border-slate-800 p-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search reports..."
            className="w-full pl-9 pr-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500"
          />
        </div>
        <select
          value={verificationFilter}
          onChange={(e) => setVerificationFilter(e.target.value as VerificationStatus | '')}
          className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500"
        >
          <option value="">All Verification Levels</option>
          {Object.keys(verificationColors).map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500"
        >
          <option value="">All Categories</option>
          {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
        <select
          value={urgencyFilter}
          onChange={(e) => setUrgencyFilter(e.target.value as Urgency | '')}
          className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500"
        >
          <option value="">All Urgencies</option>
          {(['low', 'medium', 'high', 'critical'] as Urgency[]).map((u) => (
            <option key={u} value={u}>{u}</option>
          ))}
        </select>
        <div className="flex items-center gap-1">
          <Calendar size={14} className="text-slate-500" />
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="px-2 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500" />
          <span className="text-slate-500 text-xs">to</span>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="px-2 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500" />
        </div>
      </div>

      <div className="bg-slate-900 rounded-lg border border-slate-800 overflow-hidden">
        {filtered.length === 0 ? (
          <div className="p-8 text-center text-slate-500">
            <FileText size={32} className="mx-auto mb-2 text-slate-600" />
            <p>No reports found for this event.</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-800">
            {filtered.map((report) => {
              const isExpanded = expandedId === report.id
              const nextVerification = getNextVerification(report.verification_status)
              return (
                <div key={report.id}>
                  <div
                    className="p-4 flex items-center gap-4 hover:bg-slate-800/30 transition-colors cursor-pointer"
                    onClick={() => setExpandedId(isExpanded ? null : report.id)}
                  >
                    <div className="flex-shrink-0">
                      {isExpanded ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
                    </div>
                    <FileText size={18} className="text-purple-500 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">
                        {CATEGORY_LABELS[report.report_category] ?? report.report_category}
                      </p>
                      <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
                        <span className="capitalize">{REPORTER_LABELS[report.reporter_type] ?? report.reporter_type}</span>
                        <span>•</span>
                        <span>{formatDistanceToNow(new Date(report.created_at), { addSuffix: true })}</span>
                        <span>•</span>
                        <span>{report.geometry.coordinates[1].toFixed(4)}, {report.geometry.coordinates[0].toFixed(4)}</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className={`text-xs px-2 py-0.5 rounded capitalize border ${urgencyColors[report.urgency]}`}>
                        {report.urgency}
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded capitalize ${verificationColors[report.verification_status]}`}>
                        {report.verification_status}
                      </span>
                    </div>

                    <div className="flex items-center gap-1 flex-shrink-0">
                      <button
                        className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded"
                        title="View"
                        onClick={(e) => { e.stopPropagation(); setExpandedId(isExpanded ? null : report.id) }}
                      >
                        <Eye size={14} />
                      </button>
                      <button
                        className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded"
                        title="Comments"
                        onClick={(e) => { e.stopPropagation(); setShowComments(showComments === report.id ? null : report.id) }}
                      >
                        <MessageSquare size={14} />
                      </button>
                      <button
                        className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded"
                        title="Download"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Download size={14} />
                      </button>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="px-4 pb-4 pt-0">
                      <div className="ml-10 p-4 bg-slate-800 rounded-lg border border-slate-700 space-y-4">
                        <div className="flex items-center gap-4 text-xs text-slate-500 flex-wrap">
                          <span>Event: {report.event_id}</span>
                          <span>•</span>
                          <span>Reporter: {REPORTER_LABELS[report.reporter_type] ?? report.reporter_type}</span>
                          <span>•</span>
                          <span>Confidence: {(report.confidence_score * 100).toFixed(0)}%</span>
                        </div>
                        <p className="prose prose-invert prose-sm max-w-none text-slate-300 whitespace-pre-wrap text-sm">
                          {report.description}
                        </p>
                        {report.pii_redacted_text && (
                          <p className="text-xs text-slate-500 italic">Redacted: {report.pii_redacted_text}</p>
                        )}

                        {nextVerification && (
                          <div className="flex items-center gap-2 pt-2">
                            <button
                              onClick={() => verifyMutation.mutate({ id: report.id, status: nextVerification })}
                              disabled={verifyMutation.isPending}
                              className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600/20 hover:bg-green-600/30 border border-green-500/30 rounded text-green-400 text-xs transition-colors disabled:opacity-50"
                            >
                              <ArrowUpCircle size={14} />
                              Verify as {nextVerification}
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {showComments === report.id && (
                    <div className="px-4 pb-4 pt-0">
                      <div className="ml-10 p-4 bg-slate-800 rounded-lg border border-slate-700">
                        <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
                          <MessageSquare size={14} /> Comments
                        </h3>
                        <div className="space-y-2 mb-3">
                          {demoComments.length === 0 ? (
                            <p className="text-sm text-slate-500 italic">
                              // TODO: no backend equivalent — comments are not supported by the current reports API.
                            </p>
                          ) : (
                            demoComments.map((c) => (
                              <div key={c.id} className="p-2 bg-slate-900 rounded">
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="text-xs font-medium text-slate-300">{c.user}</span>
                                  <span className="text-xs text-slate-500">{formatDistanceToNow(new Date(c.created_at), { addSuffix: true })}</span>
                                </div>
                                <p className="text-sm text-slate-400">{c.content}</p>
                              </div>
                            ))
                          )}
                        </div>
                        <div className="flex gap-2">
                          <input
                            value={commentText}
                            onChange={(e) => setCommentText(e.target.value)}
                            placeholder="Add a comment..."
                            className="flex-1 px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500"
                          />
                          <button className="px-3 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-white text-sm transition-colors">
                            <Send size={14} />
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {showGenerate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={(e) => { if (e.target === e.currentTarget) closeGenerate() }}>
          <div className="w-full max-w-2xl bg-slate-900 rounded-lg border border-slate-800 shadow-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-4 border-b border-slate-800 sticky top-0 bg-slate-900">
              <h2 className="text-lg font-semibold">Generate Report</h2>
              <button onClick={closeGenerate} className="text-slate-400 hover:text-white"><X size={20} /></button>
            </div>
            <div className="p-6 space-y-4">
              <p className="text-sm text-slate-400">
                // TODO: no backend equivalent — AI/sectioned report generation is not supported by the current reports API.
                This feature is stubbed.
              </p>
              {generateMutation.isError && <p className="text-red-400 text-sm">Failed to generate report. This feature is not available.</p>}
            </div>
            <div className="flex items-center justify-end gap-3 p-4 border-t border-slate-800 sticky bottom-0 bg-slate-900">
              <button onClick={closeGenerate} className="px-4 py-2 text-slate-400 hover:text-white text-sm transition-colors">Cancel</button>
              <button
                onClick={() => generateMutation.mutate()}
                disabled={generateMutation.isPending}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
              >
                {generateMutation.isPending ? (
                  <><Loader2 size={14} className="animate-spin" /> Generating...</>
                ) : (
                  <><FileText size={14} /> Generate Report</>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
