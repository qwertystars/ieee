import { useState, useMemo, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { eventsApi, alertsApi } from '../api/client'
import {
  Send, X, Radio, CheckCircle2, Clock, AlertTriangle, XCircle,
  Mail, MessageSquare, Phone, Globe, Smartphone, Search, Filter,
  ChevronDown, ChevronRight, Eye, RefreshCw, FileText, Calendar,
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import type { AlertRead, Urgency } from '../types'
import { clsx, type ClassValue } from 'clsx'

// TODO: no backend endpoint for creating alerts — create/send features are stubbed.

const ALL_CHANNELS = ['sms', 'email', 'whatsapp', 'push', 'radio', 'social', 'web'] as const
const CHANNEL_ICONS: Record<string, React.ElementType> = {
  sms: Phone, email: Mail, whatsapp: MessageSquare, push: Smartphone,
  radio: Radio, social: Globe, web: Globe,
}

const severityConfig: Record<Urgency, { icon: React.ElementType; color: string; bg: string }> = {
  low: { icon: Clock, color: 'text-slate-400', bg: 'bg-slate-500/10' },
  medium: { icon: Clock, color: 'text-yellow-400', bg: 'bg-yellow-500/10' },
  high: { icon: AlertTriangle, color: 'text-orange-400', bg: 'bg-orange-500/10' },
  critical: { icon: XCircle, color: 'text-red-400', bg: 'bg-red-500/10' },
}

const DEMO_TEMPLATES = [
  { id: '1', name: 'Evacuation Notice', type: 'evacuation', content: 'Immediate evacuation required for affected area. Proceed to nearest shelter.', channel: 'sms' },
  { id: '2', name: 'Shelter Update', type: 'status-update', content: 'Shelter status and capacity information has been updated.', channel: 'sms' },
  { id: '3', name: 'Weather Warning', type: 'weather', content: 'Severe weather alert issued. Take precautions immediately.', channel: 'all' },
  { id: '4', name: 'Resource Request', type: 'resource', content: 'Urgent resources needed. Contact dispatch for coordination.', channel: 'radio' },
]

function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

export default function Communications() {
  const [eventId, setEventId] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [severityFilter, setSeverityFilter] = useState<Urgency | ''>('')
  const [channelFilter, setChannelFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const [form, setForm] = useState({
    title: '',
    content: '',
    channel: 'sms',
    type: 'public-alert',
    channels: ['sms'] as string[],
    audience: 'all',
    language: 'en',
    schedule: 'now',
    scheduledTime: '',
  })

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

  const { data: alerts, isLoading } = useQuery({
    queryKey: ['alerts', eventId],
    queryFn: () => alertsApi.list(eventId!),
    enabled: !!eventId,
    refetchInterval: 15_000,
  })

  function closeCreate() {
    setShowCreate(false)
    setForm({
      title: '', content: '', channel: 'sms', type: 'public-alert',
      channels: ['sms'], audience: 'all', language: 'en', schedule: 'now', scheduledTime: '',
    })
  }

  function toggleChannel(ch: string) {
    setForm((prev) => ({
      ...prev,
      channels: prev.channels.includes(ch)
        ? prev.channels.filter((c) => c !== ch)
        : [...prev.channels, ch],
    }))
  }

  function useTemplate(tmpl: typeof DEMO_TEMPLATES[number]) {
    setForm((prev) => ({
      ...prev,
      title: tmpl.name,
      content: tmpl.content,
      channel: tmpl.channel,
      channels: tmpl.channel === 'all' ? [...ALL_CHANNELS] : [tmpl.channel],
    }))
    setShowTemplates(false)
    setShowCreate(true)
  }

  const filtered = useMemo(() => {
    let list = alerts ?? []
    if (search) {
      list = list.filter((a) =>
        a.title.toLowerCase().includes(search.toLowerCase()) ||
        a.message.toLowerCase().includes(search.toLowerCase())
      )
    }
    if (severityFilter) list = list.filter((a) => a.severity === severityFilter)
    if (dateFrom) list = list.filter((a) => new Date(a.created_at) >= new Date(dateFrom))
    if (dateTo) list = list.filter((a) => new Date(a.created_at) <= new Date(dateTo + 'T23:59:59'))
    return list
  }, [alerts, search, severityFilter, dateFrom, dateTo])

  if (isLoading) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-6">Communications</h1>
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-20 bg-slate-900 rounded-lg border border-slate-800 animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Communications</h1>
        <div className="flex items-center gap-2">
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
          <button
            onClick={() => setShowTemplates(true)}
            className="flex items-center gap-2 px-3 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-slate-300 text-sm transition-colors"
          >
            <FileText size={16} /> Templates
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-white text-sm transition-colors"
          >
            <Send size={16} /> Create Alert
          </button>
        </div>
      </div>

      <div className="bg-amber-950/30 border border-amber-700/40 rounded-lg p-3 flex items-start gap-3">
        <AlertTriangle size={18} className="text-amber-500 flex-shrink-0 mt-0.5" />
        <p className="text-sm text-amber-200/80">
          Alert sending is currently unavailable — the backend has no alert creation endpoint.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 bg-slate-900 rounded-lg border border-slate-800 p-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search alerts..."
            className="w-full pl-9 pr-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500"
          />
        </div>
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value as Urgency | '')}
          className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500"
        >
          <option value="">All Severities</option>
          {(['low', 'medium', 'high', 'critical'] as Urgency[]).map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={channelFilter}
          onChange={(e) => setChannelFilter(e.target.value)}
          className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500"
        >
          <option value="">All Channels</option>
          {ALL_CHANNELS.map((ch) => <option key={ch} value={ch}>{ch.toUpperCase()}</option>)}
        </select>
        <div className="flex items-center gap-1">
          <Calendar size={14} className="text-slate-500" />
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="px-2 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500" />
          <span className="text-slate-500 text-xs">to</span>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="px-2 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-red-500" />
        </div>
      </div>

      <div className="bg-slate-900 rounded-lg border border-slate-800 overflow-hidden">
        <div className="p-4 border-b border-slate-800">
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">Alert History</h2>
        </div>
        {filtered.length === 0 ? (
          <div className="p-8 text-center text-slate-500">
            <Radio size={32} className="mx-auto mb-2 text-slate-600" />
            <p>No alerts yet.</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-800">
            {filtered.map((alert) => {
              const cfg = severityConfig[alert.severity] ?? severityConfig.medium
              const Icon = cfg.icon
              const isOpen = selectedAlertId === alert.id
              return (
                <div
                  key={alert.id}
                  className="p-4 hover:bg-slate-800/30 transition-colors cursor-pointer"
                  onClick={() => setSelectedAlertId(isOpen ? null : alert.id)}
                >
                  <div className="flex items-start gap-3">
                    <div className={cn('p-2 rounded-lg flex-shrink-0', cfg.bg)}>
                      <Icon size={16} className={cfg.color} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <p className="font-medium truncate">{alert.title}</p>
                        <span className={cn('text-xs px-2 py-0.5 rounded capitalize', cfg.bg, cfg.color)}>
                          {alert.severity}
                        </span>
                      </div>
                      <p className="text-sm text-slate-400 line-clamp-2">{alert.message}</p>
                      <div className="flex gap-3 mt-2 text-xs text-slate-500">
                        <span className="uppercase flex items-center gap-1">
                          {(() => {
                            const ChIcon = CHANNEL_ICONS[alert.recommended_action ?? 'web']
                            return ChIcon ? <ChIcon size={10} /> : null
                          })()}
                          {alert.recommended_action ?? 'alert'}
                        </span>
                        <span>•</span>
                        <span className="capitalize">{alert.alert_type.replace(/-/g, ' ')}</span>
                        <span>•</span>
                        <span>{formatDistanceToNow(new Date(alert.created_at), { addSuffix: true })}</span>
                      </div>
                      {!alert.acknowledged && (
                        <div className="mt-1 text-xs text-slate-500">
                          Status: <span className="text-amber-400">Unacknowledged</span>
                        </div>
                      )}
                    </div>
                    <button className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded flex-shrink-0">
                      <Eye size={14} />
                    </button>
                  </div>

                  {isOpen && (
                    <div className="mt-4 ml-11 p-4 bg-slate-800 rounded-lg border border-slate-700 space-y-3">
                      <div>
                        <p className="text-xs text-slate-500 mb-1">Full Message</p>
                        <p className="text-sm text-slate-300 whitespace-pre-wrap">{alert.message}</p>
                      </div>
                      <div className="grid grid-cols-3 gap-4 text-xs">
                        <div>
                          <span className="text-slate-500">Event</span>
                          <p className="text-slate-300 truncate">{alert.event_id}</p>
                        </div>
                        <div>
                          <span className="text-slate-500">Acknowledged</span>
                          <p className="text-slate-300">{alert.acknowledged ? 'Yes' : 'No'}</p>
                        </div>
                        <div>
                          <span className="text-slate-500">Confidence</span>
                          <p className="text-slate-300">{(alert.confidence_score * 100).toFixed(0)}%</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 pt-2 border-t border-slate-700">
                        <span className="text-xs text-slate-500">Delivery: </span>
                        <span className="text-xs text-green-400 flex items-center gap-1"><CheckCircle2 size={10} /> Alert issued</span>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {showTemplates && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={(e) => { if (e.target === e.currentTarget) setShowTemplates(false); }}>
          <div className="w-full max-w-lg bg-slate-900 rounded-lg border border-slate-800 shadow-2xl">
            <div className="flex items-center justify-between p-4 border-b border-slate-800">
              <h2 className="text-lg font-semibold">Template Library</h2>
              <button onClick={() => setShowTemplates(false)} className="text-slate-400 hover:text-white"><X size={20} /></button>
            </div>
            <div className="p-4 space-y-3 max-h-[60vh] overflow-y-auto">
              {DEMO_TEMPLATES.map((tmpl) => (
                <div
                  key={tmpl.id}
                  className="p-4 bg-slate-800 rounded-lg border border-slate-700 hover:border-slate-600 transition-colors cursor-pointer"
                  onClick={() => useTemplate(tmpl)}
                >
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-medium text-sm">{tmpl.name}</h3>
                    <span className="text-xs px-2 py-0.5 bg-slate-700 rounded capitalize">{tmpl.type}</span>
                  </div>
                  <p className="text-xs text-slate-400 line-clamp-2">{tmpl.content}</p>
                  <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
                    <span className="uppercase">{tmpl.channel}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={(e) => { if (e.target === e.currentTarget) closeCreate(); }}>
          <div className="w-full max-w-2xl bg-slate-900 rounded-lg border border-slate-800 shadow-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-4 border-b border-slate-800 sticky top-0 bg-slate-900">
              <h2 className="text-lg font-semibold">Create Alert</h2>
              <button onClick={closeCreate} className="text-slate-400 hover:text-white"><X size={20} /></button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault()
                // TODO: no backend endpoint for creating alerts
              }}
              className="p-6 space-y-4"
            >
              <div>
                <label className="block text-sm text-slate-400 mb-1">Title <span className="text-red-400">*</span></label>
                <input
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-red-500 disabled:opacity-50"
                  disabled
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Message <span className="text-red-400">*</span></label>
                <textarea
                  value={form.content}
                  onChange={(e) => setForm({ ...form, content: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-red-500 h-32 resize-none disabled:opacity-50"
                  disabled
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-2">Channels</label>
                <div className="flex flex-wrap gap-2">
                  {ALL_CHANNELS.map((ch) => {
                    const ChIcon = CHANNEL_ICONS[ch]
                    const selected = form.channels.includes(ch)
                    return (
                      <button
                        key={ch}
                        type="button"
                        disabled
                        className={cn(
                          'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors disabled:opacity-50',
                          selected ? 'bg-red-600/20 border-red-500/30 text-red-400' : 'bg-slate-800 border-slate-700 text-slate-400'
                        )}
                      >
                        {ChIcon && <ChIcon size={12} />}
                        {ch.toUpperCase()}
                      </button>
                    )
                  })}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Target Audience</label>
                  <select
                    value={form.audience}
                    disabled
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-red-500 disabled:opacity-50"
                  >
                    <option value="all">All</option>
                    <option value="location">Location-based</option>
                    <option value="role">Role-based</option>
                    <option value="shelter">Shelter-based</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Language</label>
                  <select
                    value={form.language}
                    disabled
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-red-500 disabled:opacity-50"
                  >
                    <option value="en">English</option>
                    <option value="hi">Hindi</option>
                    <option value="es">Spanish</option>
                    <option value="fr">French</option>
                    <option value="ar">Arabic</option>
                    <option value="zh">Chinese</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Schedule</label>
                  <select
                    value={form.schedule}
                    disabled
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-red-500 disabled:opacity-50"
                  >
                    <option value="now">Send Now</option>
                    <option value="later">Schedule for Later</option>
                    <option value="approval">Submit for Approval</option>
                  </select>
                </div>
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={closeCreate} className="px-4 py-2 text-slate-400 hover:text-white text-sm transition-colors">Cancel</button>
                <button
                  type="submit"
                  disabled
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                >
                  <Send size={14} /> Send Alert
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
