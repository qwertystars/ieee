import React, { useCallback, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../auth/AuthContext'
import { dashboardApi, eventsApi } from '../api/client'
import MapView from '../components/Map/MapView'
import LayerToggles, { type LayerId } from '../components/Map/LayerToggles'

const POLL_MS = 15_000

export default function MapPage() {
  const { user } = useAuth()

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

  // ── Data query ───────────────────────────────────────────────────────────
  const { data: mapLayers, isLoading: layersLoading } = useQuery({
    queryKey: ['map-layers', eventId, bbox],
    queryFn: () => dashboardApi.mapLayers(eventId!, bbox ? { bbox } : undefined),
    enabled: !!eventId,
    refetchInterval: POLL_MS,
    staleTime: POLL_MS,
    placeholderData: (prev) => prev,
  })

  const currentEvent = events?.find((e) => e.id === eventId)

  return (
    <div className="flex flex-col h-full bg-gray-950 text-white overflow-hidden">
      {/* ── Top bar with event selector ──────────────────────────────────── */}
      <header className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-800 flex-shrink-0 gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="font-semibold text-sm tracking-wide hidden sm:block">Map</span>

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
            <span
              className={`text-xs px-1.5 py-0.5 rounded-full flex-shrink-0 ${
                currentEvent.status === 'active'
                  ? 'bg-red-600 text-white animate-pulse'
                  : 'bg-gray-700 text-gray-300'
              }`}
            >
              {currentEvent.status.toUpperCase()}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3 flex-shrink-0">
          <span className="text-xs text-gray-400 hidden md:block">
            {user?.name} · <span className="text-gray-300">{user?.role?.replace('_', ' ')}</span>
          </span>
        </div>
      </header>

      {/* ── Map canvas ─────────────────────────────────────────────────────── */}
      <main className="flex-1 relative overflow-hidden">
        {eventId ? (
          <>
            <MapView
              layers={mapLayers}
              visibleLayers={visibleLayers}
              onBoundsChange={handleBoundsChange}
            />
            {layersLoading && (
              <div className="absolute top-3 right-3 z-10 text-xs text-gray-400 bg-gray-900/80 px-2 py-1 rounded border border-gray-700">
                Loading layers…
              </div>
            )}
            <div className="absolute top-3 left-3 z-10">
              <LayerToggles visible={visibleLayers} onToggle={toggleLayer} />
            </div>
          </>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500 text-sm">
            Select an event to view the map
          </div>
        )}
      </main>
    </div>
  )
}
