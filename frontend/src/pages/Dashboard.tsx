// Command-centre dashboard (DESIGN §11)
// Layout: header | KPI strip | [priority-list | map+layer-toggles | right-panel-tabs]

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/AuthContext'
import {
  dashboardApi,
  eventsApi,
  situationReportApi,
  alertsApi,
  recommendationsApi,
  tokenStore,
} from '../api/client'
import { boundsToParam } from '../lib/geo'
import { DisasterWsClient } from '../lib/ws'
import type { WsEvent } from '../types'

import DashboardSummaryBar from '../components/panels/DashboardSummaryBar'
import PriorityList from '../components/panels/PriorityList'
import RecommendationsPanel from '../components/panels/RecommendationsPanel'
import SheltersPanel from '../components/panels/SheltersPanel'
import TeamsPanel from '../components/panels/TeamsPanel'
import AlertsPanel from '../components/panels/AlertsPanel'
import MapView from '../components/Map/MapView'
import LayerToggles, { type LayerId } from '../components/Map/LayerToggles'

const RIGHT_TABS = ['Recommendations', 'Shelters', 'Teams', 'Alerts'] as const
type RightTab = (typeof RIGHT_TABS)[number]

const POLL_MS = 15_000

export default function Dashboard() {
  const { user, logout } = useAuth()
  const queryClient = useQueryClient()

  // ── Event selection ──────────────────────────────────────────────────────
  const [eventId, setEventId] = useState<string | null>(null)

  const { data: events } = useQuery({
    queryKey: ['events'],
    queryFn: () => eventsApi.list({ limit: 50 }),
    staleTime: 60_000,
  })

  // Auto-select first active event
  useEffect(() => {
    if (!eventId && events && events.length > 0) {
      const active = events.find((e) => e.status === 'active') ?? events[0]
      setEventId(active.id)
    }
  }, [events, eventId])

  // ── Map bbox state ───────────────────────────────────────────────────────
  const [bbox, setBbox] = useState<string | undefined>(undefined)

  const handleBoundsChange = useCallback((b: string) => {
    setBbox(b)
  }, [])

  // ── Layer visibility ─────────────────────────────────────────────────────
  const [visibleLayers, setVisibleLayers] = useState<Record<LayerId, boolean>>({
    flood_observations: true,
    incident_reports: true,
    priority_areas: true,
    shelters: true,
    roads: true,
    teams: true,
  })

  const toggleLayer = useCallback((id: LayerId) => {
    setVisibleLayers((prev) => ({ ...prev, [id]: !prev[id] }))
  }, [])

  // ── Right panel tab ──────────────────────────────────────────────────────
  const [rightTab, setRightTab] = useState<RightTab>('Recommendations')

  // ── Priority list selected area ──────────────────────────────────────────
  const [selectedAreaId, setSelectedAreaId] = useState<string | null>(null)

  // ── Data queries ─────────────────────────────────────────────────────────
  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['dashboard-summary', eventId],
    queryFn: () => dashboardApi.summary(eventId!),
    enabled: !!eventId,
    refetchInterval: POLL_MS,
  })

  const { data: mapLayers, isLoading: layersLoading } = useQuery({
    queryKey: ['map-layers', eventId, bbox],
    queryFn: () => dashboardApi.mapLayers(eventId!, bbox ? { bbox } : undefined),
    enabled: !!eventId,
    refetchInterval: POLL_MS,
    staleTime: POLL_MS,
    placeholderData: (prev) => prev,
  })

  const { data: recommendations, isLoading: recsLoading } = useQuery({
    queryKey: ['recommendations', eventId],
    queryFn: () => recommendationsApi.list(eventId!, { limit: 100 }),
    enabled: !!eventId,
    refetchInterval: POLL_MS,
  })

  const { data: alerts } = useQuery({
    queryKey: ['alerts', eventId],
    queryFn: () => alertsApi.list(eventId!),
    enabled: !!eventId,
    refetchInterval: POLL_MS,
  })

  // ── WebSocket realtime (DESIGN §11) ──────────────────────────────────────
  const wsRef = useRef<DisasterWsClient | null>(null)

  useEffect(() => {
    if (!eventId) return
    const ws = new DisasterWsClient(eventId, tokenStore.get())
    ws.connect()
    const unsub = ws.subscribe((evt: WsEvent) => {
      // Invalidate relevant queries on realtime events
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

  // ── Situation report export ──────────────────────────────────────────────
  const [exportLoading, setExportLoading] = useState(false)

  async function handleExportReport(fmt: 'text' | 'pdf') {
    if (!eventId) return
    setExportLoading(true)
    try {
      const data = await situationReportApi.generate(eventId, { format: fmt })
      if (fmt === 'pdf') {
        const url = URL.createObjectURL(data as Blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `situation-report-${eventId}.pdf`
        a.click()
        URL.revokeObjectURL(url)
      } else {
        const blob = new Blob([data as string], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `situation-report-${eventId}.txt`
        a.click()
        URL.revokeObjectURL(url)
      }
    } catch {
      // silently ignore — backend may not be live
    } finally {
      setExportLoading(false)
    }
  }

  const currentEvent = events?.find((e) => e.id === eventId)

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-white overflow-hidden">
      {/* ── Top header ─────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-800 flex-shrink-0 gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-7 h-7 rounded bg-red-600 flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <span className="font-semibold text-sm tracking-wide hidden sm:block">DisasterAware</span>

          {/* Event selector */}
          <select
            value={eventId ?? ''}
            onChange={(e) => setEventId(e.target.value)}
            className="text-sm bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white focus:outline-none focus:border-gray-500 max-w-[240px] truncate"
          >
            {!events && <option value="">Loading events…</option>}
            {events?.map((ev) => (
              <option key={ev.id} value={ev.id}>
                {ev.name} ({ev.status})
              </option>
            ))}
          </select>

          {currentEvent && (
            <span className={`text-xs px-1.5 py-0.5 rounded-full flex-shrink-0 ${
              currentEvent.status === 'active'
                ? 'bg-red-600 text-white animate-pulse'
                : 'bg-gray-700 text-gray-300'
            }`}>
              {currentEvent.status.toUpperCase()}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3 flex-shrink-0">
          {/* Situation report export */}
          <div className="flex gap-1">
            <button
              onClick={() => handleExportReport('text')}
              disabled={!eventId || exportLoading}
              className="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-40 text-gray-200 rounded transition-colors"
              title="Export situation report (text)"
            >
              📄 Report
            </button>
            <button
              onClick={() => handleExportReport('pdf')}
              disabled={!eventId || exportLoading}
              className="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-40 text-gray-200 rounded transition-colors"
              title="Export situation report (PDF)"
            >
              PDF
            </button>
          </div>

          <span className="text-xs text-gray-400 hidden md:block">
            {user?.name} · <span className="text-gray-300">{user?.role?.replace('_', ' ')}</span>
          </span>
          <button onClick={logout} className="text-xs text-gray-400 hover:text-white transition-colors">
            Sign out
          </button>
        </div>
      </header>

      {/* ── KPI summary strip ───────────────────────────────────────────────── */}
      <DashboardSummaryBar summary={summary} isLoading={summaryLoading} />

      {/* ── Main three-column layout ────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left: priority list (240px) */}
        <aside className="w-60 flex-shrink-0 overflow-hidden">
          <PriorityList
            areas={mapLayers?.areas ?? []}
            selectedId={selectedAreaId}
            onSelect={setSelectedAreaId}
            isLoading={layersLoading}
          />
        </aside>

        {/* Centre: map + layer toggles overlay */}
        <main className="flex-1 relative overflow-hidden">
          {eventId ? (
            <>
              <MapView
                layers={mapLayers}
                visibleLayers={visibleLayers}
                onBoundsChange={handleBoundsChange}
              />
              {/* Layer toggles — top-left overlay */}
              <div className="absolute top-3 left-3 z-10">
                <LayerToggles visible={visibleLayers} onToggle={toggleLayer} />
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-500 text-sm">
              Select an event to begin
            </div>
          )}
        </main>

        {/* Right: tabbed panels (280px) */}
        <aside className="w-72 flex-shrink-0 flex flex-col border-l border-gray-800 bg-gray-900 overflow-hidden">
          {/* Tab bar */}
          <div className="flex border-b border-gray-700 flex-shrink-0">
            {RIGHT_TABS.map((tab) => {
              // Badge counts
              let badge: number | null = null
              if (tab === 'Recommendations') badge = (recommendations ?? []).filter(
                (r) => r.status === 'draft' || r.status === 'reviewed'
              ).length
              if (tab === 'Alerts') badge = (alerts ?? []).filter((a) => !a.acknowledged).length

              return (
                <button
                  key={tab}
                  onClick={() => setRightTab(tab)}
                  className={`flex-1 text-xs py-2 transition-colors relative ${
                    rightTab === tab
                      ? 'text-white border-b-2 border-orange-500'
                      : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  {tab.slice(0, 4)}
                  {badge !== null && badge > 0 && (
                    <span className="absolute -top-0.5 -right-0.5 w-4 h-4 text-[10px] bg-red-600 rounded-full flex items-center justify-center">
                      {badge > 9 ? '9+' : badge}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Panel content */}
          <div className="flex-1 overflow-hidden">
            {rightTab === 'Recommendations' && eventId && (
              <RecommendationsPanel
                recommendations={recommendations ?? []}
                eventId={eventId}
                isLoading={recsLoading}
              />
            )}
            {rightTab === 'Shelters' && (
              <SheltersPanel shelters={mapLayers?.shelters ?? []} isLoading={layersLoading} />
            )}
            {rightTab === 'Teams' && (
              <TeamsPanel teams={mapLayers?.teams ?? []} isLoading={layersLoading} />
            )}
            {rightTab === 'Alerts' && eventId && (
              <AlertsPanel alerts={alerts ?? []} isLoading={layersLoading} />
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}
