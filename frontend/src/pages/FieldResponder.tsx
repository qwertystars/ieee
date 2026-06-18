// Field responder mobile view — Task #11
// Mobile-first, low-bandwidth, offline-aware

import React, { useState, useEffect, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/AuthContext'
import { eventsApi, teamsApi, reportsApi } from '../api/client'
import FieldTaskList from '../components/field/TaskList'
import QuickReportForm from '../components/field/QuickReportForm'
import RoadStatusUpdater from '../components/field/RoadStatusUpdater'
import LocationBeacon from '../components/field/LocationBeacon'
import { getQueue, flushQueue } from '../lib/offlineQueue'

type Tab = 'tasks' | 'report' | 'roads'

const EVENT_KEY = 'field_event_id'
const TEAM_KEY  = 'field_team_id'

const TABS: { id: Tab; label: string }[] = [
  { id: 'tasks',  label: '📋 Tasks'  },
  { id: 'report', label: '📤 Report' },
  { id: 'roads',  label: '🛣️ Roads'  },
]

export default function FieldResponder() {
  const { user, logout } = useAuth()
  const qc = useQueryClient()

  const [activeTab, setActiveTab] = useState<Tab>('tasks')
  const [eventId,   setEventId]   = useState<string>(() => localStorage.getItem(EVENT_KEY) ?? '')
  const [teamId,    setTeamId]    = useState<string>(() => localStorage.getItem(TEAM_KEY)  ?? '')
  const [isOnline,  setIsOnline]  = useState(navigator.onLine)
  const [queueCount, setQueueCount] = useState(() => getQueue().length)
  const [syncing,   setSyncing]   = useState(false)
  const [syncBanner, setSyncBanner] = useState<string | null>(null)

  // ── Offline queue sync ────────────────────────────────────────────────────

  const syncOfflineQueue = useCallback(async () => {
    const queue = getQueue()
    if (queue.length === 0) return
    setSyncing(true)
    const { succeeded } = await flushQueue((eId, data) => reportsApi.create(eId, data))
    setSyncing(false)
    setQueueCount(getQueue().length)
    if (succeeded > 0) {
      qc.invalidateQueries({ queryKey: ['reports'] })
      setSyncBanner(`✓ Synced ${succeeded} queued report${succeeded > 1 ? 's' : ''}`)
      setTimeout(() => setSyncBanner(null), 4000)
    }
  }, [qc])

  // ── Online / offline detection ────────────────────────────────────────────

  useEffect(() => {
    const onOnline = () => {
      setIsOnline(true)
      syncOfflineQueue()
    }
    const onOffline = () => setIsOnline(false)
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
    }
  }, [syncOfflineQueue])

  // ── Event discovery ───────────────────────────────────────────────────────

  const { data: events } = useQuery({
    queryKey: ['events'],
    queryFn: () => eventsApi.list({ limit: 20 }),
    enabled: !eventId,
  })

  useEffect(() => {
    if (!eventId && events?.length) {
      const active = events.find((e) => e.status === 'active') ?? events[0]
      setEventId(active.id)
      localStorage.setItem(EVENT_KEY, active.id)
    }
  }, [events, eventId])

  // ── Team discovery (only when teamId not yet stored) ─────────────────────

  const { data: teams, isLoading: teamsLoading } = useQuery({
    queryKey: ['teams', eventId],
    queryFn: () => teamsApi.list(eventId),
    enabled: !!eventId && !teamId,
  })

  const selectTeam = (id: string) => {
    setTeamId(id)
    localStorage.setItem(TEAM_KEY, id)
  }

  const resetTeam = () => {
    localStorage.removeItem(TEAM_KEY)
    setTeamId('')
  }

  // Refresh queue badge whenever tab changes or form submits
  const refreshQueueCount = useCallback(() => setQueueCount(getQueue().length), [])
  useEffect(() => { refreshQueueCount() }, [activeTab, refreshQueueCount])

  // ── Loading screen while event resolves ──────────────────────────────────

  if (!eventId) {
    return (
      <div className="flex flex-col min-h-screen bg-gray-950 text-white">
        <header className="px-4 py-3 bg-gray-900 border-b border-gray-800">
          <span className="font-semibold text-sm">Field Responder</span>
        </header>
        <main className="flex flex-1 items-center justify-center px-4">
          <div className="text-center text-gray-500">
            <div className="text-3xl mb-3 animate-pulse">⏳</div>
            <p className="text-sm">Loading event data…</p>
          </div>
        </main>
      </div>
    )
  }

  // ── Team selector (shown once, result persisted to localStorage) ──────────

  if (!teamId && !teamsLoading && teams && teams.length > 0) {
    return (
      <div className="flex flex-col min-h-screen bg-gray-950 text-white">
        <header className="px-4 py-3 bg-gray-900 border-b border-gray-800">
          <span className="font-semibold text-sm">Field Responder — Select Your Team</span>
        </header>
        <main className="flex flex-col gap-3 px-4 py-6 max-w-lg mx-auto w-full">
          <p className="text-sm text-gray-400 mb-1">Which response team are you on?</p>
          {teams.map((team) => (
            <button
              key={team.id}
              onClick={() => selectTeam(team.id)}
              className="flex items-center justify-between px-4 py-3 rounded-lg border border-gray-700 bg-gray-900 hover:border-blue-500 text-left transition-colors active:scale-[0.98]"
            >
              <div>
                <div className="text-sm font-medium text-white">{team.name}</div>
                <div className="text-xs text-gray-500 mt-0.5">
                  {team.team_type} · {team.status}
                </div>
              </div>
              <span className="text-gray-600 text-lg">›</span>
            </button>
          ))}
          <button
            type="button"
            onClick={() => selectTeam('__none__')}
            className="text-xs text-gray-600 text-center mt-2 hover:text-gray-400"
          >
            Skip — show all tasks
          </button>
        </main>
      </div>
    )
  }

  // Resolve effective team ID (null = show all tasks)
  const resolvedTeamId = !teamId || teamId === '__none__' ? null : teamId

  // ── Main layout ───────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col min-h-screen bg-gray-950 text-white">

      {/* ── Sticky header ── */}
      <header className="flex items-center justify-between px-4 py-3 bg-gray-900 border-b border-gray-800 sticky top-0 z-20">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm">Field Responder</span>
          {/* Online indicator */}
          <span
            title={isOnline ? 'Online' : 'Offline'}
            className={`inline-block w-2 h-2 rounded-full ${isOnline ? 'bg-green-400' : 'bg-red-500'}`}
          />
        </div>

        <div className="flex items-center gap-3 text-xs text-gray-400">
          {/* Offline queue badge */}
          {queueCount > 0 && (
            <button
              onClick={syncOfflineQueue}
              disabled={!isOnline || syncing}
              className="px-2 py-1 rounded bg-yellow-900/60 border border-yellow-700 text-yellow-300 disabled:opacity-50 transition-opacity"
            >
              {syncing ? '…syncing' : `${queueCount} queued`}
            </button>
          )}
          <span className="hidden sm:inline truncate max-w-[80px]">{user?.name}</span>
          <button onClick={logout} className="hover:text-white transition-colors">
            Sign out
          </button>
        </div>
      </header>

      {/* ── Notification banners ── */}
      {syncBanner && (
        <div className="px-4 py-2 bg-green-900/40 border-b border-green-800 text-xs text-green-300 text-center">
          {syncBanner}
        </div>
      )}
      {!isOnline && (
        <div className="px-4 py-2 bg-yellow-900/40 border-b border-yellow-800 text-xs text-yellow-300 text-center">
          📶 Offline — reports queued locally, tasks read-only
        </div>
      )}

      {/* ── Tab bar ── */}
      <nav className="flex border-b border-gray-800 bg-gray-900 sticky top-[52px] z-10">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 py-3 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'text-white border-b-2 border-blue-500'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* ── Tab content ── */}
      <main className="flex-1 overflow-y-auto px-4 py-4 pb-safe">
        <div className="max-w-lg mx-auto">

          {activeTab === 'tasks' && (
            <FieldTaskList eventId={eventId} teamId={resolvedTeamId} />
          )}

          {activeTab === 'report' && (
            <div className="space-y-4">
              {resolvedTeamId && (
                <LocationBeacon teamId={resolvedTeamId} />
              )}
              <div className="rounded-lg border border-gray-700 bg-gray-900 p-4">
                <h2 className="text-sm font-semibold text-white mb-4">Quick Incident Report</h2>
                <QuickReportForm
                  eventId={eventId}
                  onSubmitSuccess={refreshQueueCount}
                />
              </div>
            </div>
          )}

          {activeTab === 'roads' && (
            <RoadStatusUpdater eventId={eventId} />
          )}

        </div>
      </main>

      {/* ── Footer: team info + reset ── */}
      <footer className="px-4 py-2 border-t border-gray-800 bg-gray-950 flex items-center justify-between text-xs text-gray-700">
        <span>
          {resolvedTeamId ? `Team: ${resolvedTeamId.slice(0, 8)}…` : 'All teams'}
        </span>
        <button
          onClick={resetTeam}
          className="hover:text-gray-400 transition-colors"
        >
          Change team
        </button>
      </footer>
    </div>
  )
}
