import { useMeshRoute } from '../hooks/useMeshRoute'
import { useMeshHealth } from '../hooks/useMeshHealth'
import { OperationsPanel } from './OperationsPanel'
import { useClock } from '../hooks/useClock'

export function MeshOverview() {
  const mesh = useMeshRoute()
  const health = useMeshHealth()
  const now = useClock(5000)
  const relays = new Set(mesh.state.survivors.map(s => s.relayNodeId).filter(Boolean)).size
  const connected = mesh.status === 'open'
  const aging = mesh.receivedAt !== null && now - mesh.receivedAt > 60000
  const point = (x: number, y: number) => `${160 + x * 1.6},${90 - y * 0.9}`
  return (
    <OperationsPanel title="BLE mesh & rescue routes" status={aging && connected ? 'Feed stale' : connected ? 'Feed connected' : mesh.status === 'connecting' ? 'Connecting' : 'Disconnected'}>
      <div className="mb-4 grid grid-cols-3 gap-2 text-center">
        {[[mesh.state.survivors.length, 'Beacons'], [relays, 'Relays'], [mesh.state.hazards.length, 'Weak-signal zones']].map(([count, label]) => <div key={label} className="rounded bg-slate-800/60 p-3"><p className="text-xl font-semibold text-cyan-300">{mesh.hasReceivedData ? count : '—'}</p><p className="mt-1 text-xs text-slate-400">{label}</p></div>)}
      </div>
      <p role="status" className="mb-3 text-xs text-slate-400">{`Localization service: ${health}. ${!mesh.hasReceivedData ? 'Waiting for a phone to sync its mesh table.' : !connected ? 'Showing the last received mesh picture; it may be stale.' : 'Showing the latest received mesh picture.'}`}</p>
      {mesh.receivedAt !== null && <p className="mb-3 text-xs text-slate-400">Last received {Math.max(0, Math.floor((now - mesh.receivedAt) / 1000))} seconds ago.{aging && ' Awaiting a fresh update.'}</p>}
      <svg viewBox="0 0 320 180" role="img" aria-label="Relative mesh positions and reported path" className="w-full rounded-lg border border-slate-700 bg-slate-950">
        <line x1="160" x2="160" y1="0" y2="180" stroke="#334155" /><line x1="0" x2="320" y1="90" y2="90" stroke="#334155" />
        <polyline points={mesh.state.path.map(p => point(p.x, p.y)).join(' ')} stroke="#22d3ee" strokeWidth="2" fill="none" />
        {mesh.state.hazards.map(h => <circle key={h.id} cx={160 + h.position.x * 1.6} cy={90 - h.position.y * 0.9} r="10" fill="#f59e0b" fillOpacity="0.3" />)}
        {mesh.state.survivors.map(s => <g key={s.id}><circle cx={160 + s.position.x * 1.6} cy={90 - s.position.y * 0.9} r="4" fill="#22d3ee" /><title>Beacon {s.id}</title></g>)}
      </svg>
      <p className="mt-3 text-xs text-slate-400">Reported relay path · RSSI signal priority.</p>
      <ul className="mt-3 max-h-44 space-y-2 overflow-auto text-xs text-slate-300">
        {mesh.state.survivors.map(s => <li key={s.id} className="flex justify-between gap-2 border-b border-slate-800 pb-2"><span>Beacon {s.id} · relay {s.relayNodeId ?? 'unknown'}</span><span>{s.urgency} signal priority</span></li>)}
      </ul>
    </OperationsPanel>
  )
}
