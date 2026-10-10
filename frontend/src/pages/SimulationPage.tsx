import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { InjectFaultRequest, Observation, GeoJSONFeature } from '../api/types'
import { LoadingState, ErrorState, EmptyState, StaleState, OfflineState } from '../components/state'

const FAULT_TYPES = [
  'battery_drain', 'sensor_degradation', 'connectivity_loss', 'blocked_route',
  'thermal_hotspot', 'human_heat_signature', 'water_depth', 'motion', 'vibration', 'environmental_temp',
]

function fmtTime(ms: number): string {
  const s = Math.floor((ms ?? 0) / 1000)
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s % 60}s`
  return `${s}s`
}

function stateColor(state: string): string {
  if (state === 'running') return 'bg-green-500/10 text-green-400'
  if (state === 'paused') return 'bg-amber-500/10 text-amber-400'
  return 'bg-gray-500/10 text-gray-400'
}

interface Telemetry { battery?: number; signal?: number; temperature?: number; altitude?: number; lon?: number; lat?: number }

function extractTel(features: GeoJSONFeature<Observation>[], deviceId: string): Telemetry | null {
  const sourceId = `simulator:${deviceId}`
  const obs = features.filter(f => f.properties.source_id === sourceId)
  if (obs.length === 0) return null
  const tel: Telemetry = {}
  for (const f of obs) {
    const p = f.properties
    const v = typeof p.value === 'number' ? p.value : undefined
    if (p.phenomenon === 'battery_level') tel.battery = v
    else if (p.phenomenon === 'signal_quality') tel.signal = v
    else if (p.phenomenon === 'device_temperature') tel.temperature = v
    else if (p.phenomenon === 'altitude') tel.altitude = v
    if (f.geometry?.type === 'Point') { tel.lon = f.geometry.coordinates[0]; tel.lat = f.geometry.coordinates[1] }
  }
  return tel
}

export default function SimulationPage() {
  const queryClient = useQueryClient()
  const [toast, setToast] = useState<{ msg: string; kind: 'success' | 'error' } | null>(null)
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null)
  const [speed, setSpeed] = useState(1.0)
  const isOnline = typeof navigator !== 'undefined' ? navigator.onLine : true

  function showToast(msg: string, kind: 'success' | 'error' = 'success') {
    setToast({ msg, kind })
    setTimeout(() => setToast(null), 3000)
  }

  const statusQ = useQuery({
    queryKey: ['simulator-status'],
    queryFn: ({ signal }) => api.simulatorStatus(signal),
    refetchInterval: 2000,
  })

  const incidentsQ = useQuery({
    queryKey: ['incidents'],
    queryFn: ({ signal }) => api.getIncidents(signal),
  })
  const incidentId = incidentsQ.data?.incidents?.[0]?.id ?? null
  const orgId = incidentsQ.data?.incidents?.[0]?.org_id ?? null

  const obsQ = useQuery({
    queryKey: ['observations', incidentId],
    queryFn: ({ signal }) => api.getObservations(incidentId!, signal),
    enabled: !!incidentId && !!selectedDevice,
  })

  const telemetry = useMemo(() => {
    if (!obsQ.data?.features || !selectedDevice) return null
    return extractTel(obsQ.data.features as GeoJSONFeature<Observation>[], selectedDevice)
  }, [obsQ.data, selectedDevice])

  function invalidateStatus() {
    queryClient.invalidateQueries({ queryKey: ['simulator-status'] })
  }

  const startMut = useMutation({
    mutationFn: () => api.simulatorStart({ org_id: orgId!, incident_id: incidentId!, device_count: 2 }),
    onSuccess: () => { showToast('Simulation started'); invalidateStatus() },
    onError: (e: unknown) => showToast(e instanceof Error ? e.message : 'Start failed', 'error'),
  })
  const stopMut = useMutation({
    mutationFn: () => api.simulatorStop(),
    onSuccess: () => { showToast('Simulation stopped'); invalidateStatus() },
    onError: (e: unknown) => showToast(e instanceof Error ? e.message : 'Stop failed', 'error'),
  })
  const pauseMut = useMutation({
    mutationFn: () => api.simulatorPause(),
    onSuccess: () => { showToast('Simulation paused'); invalidateStatus() },
    onError: (e: unknown) => showToast(e instanceof Error ? e.message : 'Pause failed', 'error'),
  })
  const resumeMut = useMutation({
    mutationFn: () => api.simulatorResume(),
    onSuccess: () => { showToast('Simulation resumed'); invalidateStatus() },
    onError: (e: unknown) => showToast(e instanceof Error ? e.message : 'Resume failed', 'error'),
  })
  const speedMut = useMutation({
    mutationFn: (s: number) => api.simulatorSetSpeed(s),
    onSuccess: () => invalidateStatus(),
    onError: (e: unknown) => showToast(e instanceof Error ? e.message : 'Speed change failed', 'error'),
  })
  const faultMut = useMutation({
    mutationFn: (req: InjectFaultRequest) => api.simulatorInjectFault(req),
    onSuccess: (_d, req) => { showToast(`Fault ${req.fault_type} injected`); invalidateStatus() },
    onError: (e: unknown) => showToast(e instanceof Error ? e.message : 'Fault injection failed', 'error'),
  })

  if (statusQ.isLoading) {
    return <div className="flex h-full items-center justify-center"><LoadingState message="Loading simulator…" /></div>
  }
  if (statusQ.isError) {
    return <div className="p-6"><ErrorState message="Failed to load simulator status" onRetry={() => statusQ.refetch()} /></div>
  }

  const status = statusQ.data
  const state = status?.state ?? 'stopped'
  const deviceIds = status?.device_ids ?? []
  const pending = startMut.isPending || stopMut.isPending || pauseMut.isPending || resumeMut.isPending
  const canStart = state === 'stopped' && !!incidentId && !!orgId

  return (
    <div className="flex flex-col gap-4 p-6" aria-label="Simulation page">
      <div className="rounded-lg border border-amber-600 bg-amber-900/30 px-4 py-2 text-center text-sm font-bold uppercase tracking-wider text-amber-300" role="banner" aria-label="Simulated data banner">
        ⚠ Simulated Data — Digital twin only, not for operational use
      </div>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-100">Simulation</h1>
          <p className="mt-1 text-sm text-gray-500">Digital-twin device simulator control.</p>
        </div>
        <div className="flex items-center gap-2">
          {!isOnline && <OfflineState />}
          {statusQ.isStale && <StaleState />}
        </div>
      </div>

      {toast && (
        <div role="alert" aria-live="assertive" className={`rounded-lg border px-3 py-2 text-xs ${toast.kind === 'success' ? 'border-green-600 bg-green-900/95 text-green-200' : 'border-red-600 bg-red-900/95 text-red-200'}`}>
          {toast.msg}
        </div>
      )}

      <section className="rounded-lg border border-gray-700 bg-gray-900/95 p-4" aria-label="Simulator controls">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <span className={`rounded px-2 py-0.5 text-xs font-medium ${stateColor(state)}`} aria-label={`State: ${state}`}>{state}</span>
          <span className="text-xs text-gray-400" aria-label={`Sim time: ${fmtTime(status?.sim_time_ms ?? 0)}`}>Sim time: {fmtTime(status?.sim_time_ms ?? 0)}</span>
          <span className="text-xs text-gray-400" aria-label={`Seed: ${status?.seed ?? 0}`}>Seed: {status?.seed ?? 0}</span>
          <span className="text-xs text-gray-400" aria-label={`Devices: ${status?.device_count ?? 0}`}>Devices: {status?.device_count ?? 0}</span>
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Simulation controls">
          <button onClick={() => startMut.mutate()} disabled={!canStart || pending} className="rounded-md bg-green-600 px-4 py-2 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-green-500" aria-label="Start simulation">Start</button>
          <button onClick={() => stopMut.mutate()} disabled={state === 'stopped' || pending} className="rounded-md bg-red-600 px-4 py-2 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-red-500" aria-label="Stop simulation">Stop</button>
          <button onClick={() => pauseMut.mutate()} disabled={state !== 'running' || pending} className="rounded-md bg-amber-600 px-4 py-2 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-amber-500" aria-label="Pause simulation">Pause</button>
          <button onClick={() => resumeMut.mutate()} disabled={state !== 'paused' || pending} className="rounded-md bg-blue-600 px-4 py-2 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-blue-500" aria-label="Resume simulation">Resume</button>
        </div>
        <div className="mt-3" aria-label="Speed control">
          <label htmlFor="speed-slider" className="mb-1 block text-xs text-gray-400">Speed: {speed.toFixed(1)}x</label>
          <input id="speed-slider" type="range" min={0.5} max={5} step={0.5} value={speed} onChange={(e) => { setSpeed(parseFloat(e.target.value)); speedMut.mutate(parseFloat(e.target.value)) }} className="w-full accent-blue-500" aria-label={`Simulation speed ${speed}x`} />
        </div>
      </section>

      <section className="rounded-lg border border-gray-700 bg-gray-900/95 p-4" aria-label="Devices">
        <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-300">Devices</h2>
        {deviceIds.length === 0 ? (
          <EmptyState message="No devices" hint="Start the simulation to create devices." />
        ) : (
          <div className="flex flex-col gap-2" role="list">
            {deviceIds.map(id => (
              <div key={id} role="listitem" className={`flex items-center justify-between rounded border p-2 text-xs ${selectedDevice === id ? 'border-blue-600 bg-blue-900/20' : 'border-gray-700'}`}>
                <button onClick={() => setSelectedDevice(id)} className="font-mono text-blue-400 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500" aria-label={`Select device ${id}`}>{id}</button>
                <Link to={`/devices/${id}`} className="rounded border border-gray-600 px-2 py-1 text-[10px] text-gray-300 hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500" aria-label={`View details for ${id}`}>Details →</Link>
              </div>
            ))}
          </div>
        )}
      </section>

      {selectedDevice && (
        <section className="rounded-lg border border-gray-700 bg-gray-900/95 p-4" aria-label={`Telemetry for ${selectedDevice}`}>
          <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-300">Telemetry — <span className="font-mono text-blue-400">{selectedDevice}</span></h2>
          {obsQ.isLoading && <LoadingState message="Loading telemetry…" />}
          {obsQ.isError && <ErrorState message="Failed to load telemetry" onRetry={() => obsQ.refetch()} />}
          {obsQ.data && !telemetry && <EmptyState message="No telemetry published" hint="Observations will appear once the simulation publishes data." />}
          {telemetry && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              <div className="rounded bg-gray-800/50 p-2" aria-label={`Battery: ${telemetry.battery?.toFixed(1) ?? '—'}%`}>
                <div className="text-[10px] uppercase text-gray-500">Battery</div>
                <div className="text-sm font-bold text-gray-100">{telemetry.battery?.toFixed(1) ?? '—'}%</div>
              </div>
              <div className="rounded bg-gray-800/50 p-2" aria-label={`Signal: ${telemetry.signal?.toFixed(1) ?? '—'}%`}>
                <div className="text-[10px] uppercase text-gray-500">Signal</div>
                <div className="text-sm font-bold text-gray-100">{telemetry.signal?.toFixed(1) ?? '—'}%</div>
              </div>
              <div className="rounded bg-gray-800/50 p-2" aria-label={`Temperature: ${telemetry.temperature?.toFixed(1) ?? '—'}°C`}>
                <div className="text-[10px] uppercase text-gray-500">Temp</div>
                <div className="text-sm font-bold text-gray-100">{telemetry.temperature?.toFixed(1) ?? '—'}°C</div>
              </div>
              <div className="rounded bg-gray-800/50 p-2" aria-label={`Position: ${telemetry.lon?.toFixed(4) ?? '—'}, ${telemetry.lat?.toFixed(4) ?? '—'}`}>
                <div className="text-[10px] uppercase text-gray-500">Position</div>
                <div className="text-[11px] font-mono text-gray-100">{telemetry.lon?.toFixed(4) ?? '—'}, {telemetry.lat?.toFixed(4) ?? '—'}</div>
              </div>
            </div>
          )}
        </section>
      )}

      {selectedDevice && (
        <section className="rounded-lg border border-gray-700 bg-gray-900/95 p-4" aria-label="Fault injection">
          <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-300">Inject Fault — <span className="font-mono text-blue-400">{selectedDevice}</span></h2>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3" role="group" aria-label="Fault types">
            {FAULT_TYPES.map(ft => (
              <button key={ft} onClick={() => faultMut.mutate({ device_id: selectedDevice, fault_type: ft })} disabled={faultMut.isPending} className="rounded border border-gray-600 bg-gray-800 px-2 py-2 text-[11px] text-gray-200 hover:bg-gray-700 disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-blue-500" aria-label={`Inject fault ${ft}`}>
                {ft.replace(/_/g, ' ')}
              </button>
            ))}
          </div>
        </section>
      )}

      {pending && (
        <div className="fixed bottom-6 right-6 z-50" role="status" aria-live="polite" aria-label="Processing">
          <div className="flex items-center gap-2 rounded-lg border border-gray-600 bg-gray-900 px-4 py-2 shadow-xl">
            <svg className="h-4 w-4 animate-spin text-blue-400" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="text-xs text-gray-300">Processing…</span>
          </div>
        </div>
      )}
    </div>
  )
}
