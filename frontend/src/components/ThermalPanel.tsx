import { useQuery } from '@tanstack/react-query'
import { OperationsPanel } from './OperationsPanel'
import { useClock } from '../hooks/useClock'

export interface ThermalDetection {
  id: number
  timestamp: number
  coords: [number, number]
  confidence: number
  radius: number
}

export function parseThermalDetections(value: unknown): ThermalDetection[] {
  if (!Array.isArray(value)) throw new Error('Invalid thermal response')
  return value.map((item: unknown) => {
    if (!item || typeof item !== 'object') throw new Error('Invalid thermal detection')
    const d = item as Record<string, unknown>
    const coords = d.coords
    if (typeof d.id !== 'number' || !Number.isFinite(d.id)
      || typeof d.timestamp !== 'number' || !Number.isFinite(d.timestamp)
      || typeof d.confidence !== 'number' || !Number.isFinite(d.confidence) || d.confidence < 0 || d.confidence > 1
      || typeof d.radius !== 'number' || !Number.isFinite(d.radius) || d.radius < 0
      || !Array.isArray(coords) || coords.length !== 2
      || !coords.every((n: unknown) => typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= 1)) {
      throw new Error('Invalid thermal detection')
    }
    return { id: d.id, timestamp: d.timestamp, confidence: d.confidence, radius: d.radius,
      coords: [coords[0] as number, coords[1] as number] }
  })
}

export function ThermalPanel() {
  const now = useClock()
  const base = (import.meta.env.VITE_THERMAL_API_BASE
    ?? `${window.location.protocol}//${window.location.hostname}:8765`).replace(/\/+$/, '')
  const query = useQuery({
    queryKey: ['thermal-detections', base],
    queryFn: async ({ signal }) => {
      const response = await fetch(`${base}/api/hazard?limit=50`, {
        signal: AbortSignal.any([signal, AbortSignal.timeout(4000)]), cache: 'no-store',
      })
      if (!response.ok) throw new Error('Thermal service unavailable')
      return parseThermalDetections(await response.json())
    },
    retry: false, refetchInterval: 5000,
  })
  const detections = query.data ?? []
  const stale = detections.some(d => now - d.timestamp * 1000 > 60000)
  return (
    <OperationsPanel title="Thermal intelligence" status={query.isPending ? 'Connecting' : query.isError ? 'Disconnected' : 'Connected'}>
      <p className="mb-3 text-xs text-slate-400">Heat signatures in the camera frame · candidates awaiting human review</p>
      {query.isError && <p role="alert" className="mb-3 text-xs text-amber-300">Thermal feed unavailable. {query.data ? 'Showing last received detections.' : 'No live detections available.'}</p>}
      {stale && <p role="status" className="mb-3 text-xs text-amber-300">Some detections are older than one minute.</p>}
      <svg viewBox="0 0 320 180" role="img" aria-label="Thermal detections in camera coordinates" className="w-full rounded-lg border border-slate-700 bg-slate-950">
        {[80, 160, 240].map(x => <line key={x} x1={x} x2={x} y1="0" y2="180" stroke="#1e293b" />)}
        {[60, 120].map(y => <line key={y} x1="0" x2="320" y1={y} y2={y} stroke="#1e293b" />)}
        {detections.map(d => <g key={d.id}><circle cx={d.coords[0] * 320} cy={d.coords[1] * 180} r="7" fill="#fb923c" fillOpacity="0.5" stroke="#fdba74" /><title>Candidate {d.id}: {(d.confidence * 100).toFixed(0)}% stability</title></g>)}
      </svg>
      {!query.isPending && !query.isError && detections.length === 0 && <p className="mt-3 text-sm text-slate-400">Connected; waiting for thermal detections.</p>}
      <ul className="mt-3 max-h-44 space-y-2 overflow-auto text-xs text-slate-300">
        {detections.map(d => <li key={d.id} className="flex justify-between gap-2 border-b border-slate-800 pb-2"><span>Candidate #{d.id} · {(d.confidence * 100).toFixed(0)}% stability</span><time dateTime={new Date(d.timestamp * 1000).toISOString()}>{new Date(d.timestamp * 1000).toLocaleTimeString()}</time></li>)}
      </ul>
      <p className="mt-3 text-xs text-slate-500">Camera positions are not GPS locations. This feed does not include video.</p>
    </OperationsPanel>
  )
}
