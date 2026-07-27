import { useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Observation, GeoJSONFeature } from '../api/types'
import { LoadingState, ErrorState, EmptyState, StaleState, OfflineState } from '../components/state'

interface Telemetry {
  battery?: number
  signal?: number
  temperature?: number
  altitude?: number
  lastSeen?: number
  path: Array<{ lon: number; lat: number; ts: number }>
}

function fmtTime(ms: number): string {
  if (!ms) return '—'
  return new Date(ms).toISOString().slice(0, 19) + 'Z'
}

function extractTelemetry(features: GeoJSONFeature<Observation>[], deviceId: string): Telemetry {
  const sourceId = `simulator:${deviceId}`
  const deviceObs = features
    .filter(f => f.properties.source_id === sourceId)
    .sort((a, b) => a.properties.observed_at - b.properties.observed_at)

  const tel: Telemetry = { path: [] }
  for (const f of deviceObs) {
    const p = f.properties
    const v = typeof p.value === 'number' ? p.value : undefined
    if (p.phenomenon === 'battery_level') tel.battery = v
    else if (p.phenomenon === 'signal_quality') tel.signal = v
    else if (p.phenomenon === 'device_temperature') tel.temperature = v
    else if (p.phenomenon === 'altitude') tel.altitude = v
    if (f.geometry?.type === 'Point') {
      tel.path.push({ lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1], ts: p.observed_at })
    }
    if (!tel.lastSeen || p.observed_at > tel.lastSeen) tel.lastSeen = p.observed_at
  }
  return tel
}

function Metric({ label, value, unit, color }: { label: string; value: string; unit?: string; color?: string }) {
  return (
    <div className="rounded bg-gray-800/50 p-2" aria-label={`${label}: ${value}${unit ?? ''}`}>
      <div className="text-[10px] uppercase tracking-wider text-gray-500">{label}</div>
      <div className={`text-sm font-bold ${color ?? 'text-gray-100'}`}>
        {value}{unit && <span className="ml-0.5 text-[10px] text-gray-500">{unit}</span>}
      </div>
    </div>
  )
}

function batteryColor(v?: number): string {
  if (v == null) return 'text-gray-500'
  if (v <= 5) return 'text-red-400'
  if (v <= 20) return 'text-amber-400'
  return 'text-green-400'
}

function signalColor(v?: number): string {
  if (v == null) return 'text-gray-500'
  if (v <= 10) return 'text-red-400'
  if (v <= 30) return 'text-amber-400'
  return 'text-green-400'
}

export default function DeviceDetailPage() {
  const { id } = useParams<{ id: string }>()
  const isOnline = typeof navigator !== 'undefined' ? navigator.onLine : true

  const statusQ = useQuery({
    queryKey: ['simulator-status'],
    queryFn: ({ signal }) => api.simulatorStatus(signal),
    refetchInterval: 5000,
  })

  const incidentsQ = useQuery({
    queryKey: ['incidents'],
    queryFn: ({ signal }) => api.getIncidents(signal),
  })
  const incidentId = incidentsQ.data?.incidents?.[0]?.id ?? null

  const obsQ = useQuery({
    queryKey: ['observations', incidentId],
    queryFn: ({ signal }) => api.getObservations(incidentId!, signal),
    enabled: !!incidentId,
  })

  const telemetry = useMemo(() => {
    if (!obsQ.data?.features || !id) return null
    return extractTelemetry(obsQ.data.features as GeoJSONFeature<Observation>[], id)
  }, [obsQ.data, id])

  if (!id) {
    return <div className="p-6"><EmptyState message="No device ID specified" /></div>
  }

  if (statusQ.isLoading || incidentsQ.isLoading) {
    return <div className="flex h-full items-center justify-center"><LoadingState message="Loading device…" /></div>
  }
  if (statusQ.isError) {
    return <div className="p-6"><ErrorState message="Failed to load simulator status" onRetry={() => statusQ.refetch()} /></div>
  }

  const status = statusQ.data
  const deviceExists = status?.device_ids?.includes(id) ?? false
  const simState = status?.state ?? 'stopped'

  return (
    <div className="flex flex-col gap-4 p-6" aria-label="Device detail page">
      <div
        className="rounded-lg border border-amber-600 bg-amber-900/30 px-4 py-2 text-center text-sm font-bold uppercase tracking-wider text-amber-300"
        role="banner"
        aria-label="Simulated data label"
      >
        ⚠ Simulated Data — Digital twin telemetry
      </div>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-100 font-mono">{id}</h1>
          <p className="mt-1 text-sm text-gray-500">Rescue ball device telemetry.</p>
        </div>
        <div className="flex items-center gap-2">
          {!isOnline && <OfflineState />}
          {obsQ.isStale && <StaleState />}
        </div>
      </div>

      {!deviceExists && (
        <div className="rounded-lg border border-gray-700 bg-gray-900 p-4">
          <EmptyState
            message="Device not found in active simulation"
            hint="Start the simulation to see this device's telemetry."
          />
        </div>
      )}

      {deviceExists && (
        <>
          <section className="rounded-lg border border-gray-700 bg-gray-900/95 p-4" aria-label="Device state">
            <div className="mb-2 flex items-center gap-3">
              <span className="text-xs text-gray-400">Sim state:</span>
              <span className={`rounded px-2 py-0.5 text-xs font-medium ${
                simState === 'running' ? 'bg-green-500/10 text-green-400'
                : simState === 'paused' ? 'bg-amber-500/10 text-amber-400'
                : 'bg-gray-500/10 text-gray-400'
              }`} aria-label={`Simulation state: ${simState}`}>
                {simState}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Metric label="Battery" value={telemetry?.battery != null ? telemetry.battery.toFixed(1) : '—'} unit="%" color={batteryColor(telemetry?.battery)} />
              <Metric label="Signal" value={telemetry?.signal != null ? telemetry.signal.toFixed(1) : '—'} unit="%" color={signalColor(telemetry?.signal)} />
              <Metric label="Temp" value={telemetry?.temperature != null ? telemetry.temperature.toFixed(1) : '—'} unit="°C" />
              <Metric label="Altitude" value={telemetry?.altitude != null ? telemetry.altitude.toFixed(1) : '—'} unit="m" />
            </div>
            <div className="mt-2 text-xs text-gray-500" aria-label={`Last seen: ${telemetry?.lastSeen ? fmtTime(telemetry.lastSeen) : 'never'}`}>
              Last seen: {telemetry?.lastSeen ? fmtTime(telemetry.lastSeen) : 'never'}
            </div>
          </section>

          <section className="rounded-lg border border-gray-700 bg-gray-900/95 p-4" aria-label="Sensor status">
            <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-300">Sensors</h2>
            {obsQ.isLoading && <LoadingState message="Loading sensors…" />}
            {obsQ.isError && <ErrorState message="Failed to load observations" onRetry={() => obsQ.refetch()} />}
            {obsQ.data && !telemetry?.lastSeen && (
              <EmptyState message="No telemetry published" hint="Observations will appear once the simulation publishes data." />
            )}
            {telemetry?.lastSeen && (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Metric label="Camera" value="N/A" />
                <Metric label="Thermal" value="N/A" />
                <Metric label="IMU" value="N/A" />
                <Metric label="Acoustic" value="N/A" />
              </div>
            )}
            <p className="mt-2 text-[10px] text-gray-600">
              Sensor detail requires direct device access (not exposed via API).
            </p>
          </section>

          <section className="rounded-lg border border-gray-700 bg-gray-900/95 p-4" aria-label="Path history">
            <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-300">Path History</h2>
            {telemetry && telemetry.path.length > 0 ? (
              <div className="max-h-48 overflow-y-auto" role="list">
                {telemetry.path.slice(-20).reverse().map((p, i) => (
                  <div key={i} role="listitem" className="flex items-center justify-between border-b border-gray-800 py-1 text-[11px]">
                    <span className="font-mono text-blue-400">{p.lon.toFixed(4)}, {p.lat.toFixed(4)}</span>
                    <span className="text-gray-500">{fmtTime(p.ts)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState message="No path data" hint="Path history appears as the device moves." />
            )}
          </section>
        </>
      )}
    </div>
  )
}
