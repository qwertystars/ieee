import type { MeshLinkStatus } from '../../hooks/useMeshRoute'
import type { MeshHealthStatus } from '../../hooks/useMeshHealth'
import type { RouteState } from '../../types/rescue'

const LINK_LABEL: Record<MeshLinkStatus, string> = {
  connecting: 'Linking…',
  open: 'Online',
  closed: 'Offline',
  error: 'Interference',
}

const LINK_COLOR: Record<MeshLinkStatus, string> = {
  connecting: 'text-cyan-300',
  open: 'text-emerald-300',
  closed: 'text-amber-300',
  error: 'text-red-400',
}

const LINK_BAR: Record<MeshLinkStatus, string> = {
  connecting: 'w-2/3',
  open: 'w-full',
  closed: 'w-1/4',
  error: 'w-1/3',
}

const HEALTH_LABEL: Record<MeshHealthStatus, string> = {
  checking: 'Checking…',
  online: 'Online',
  offline: 'Offline',
}

const HEALTH_COLOR: Record<MeshHealthStatus, string> = {
  checking: 'text-cyan-300',
  online: 'text-emerald-300',
  offline: 'text-red-400',
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-slate-700/40 bg-slate-900/50 p-3">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="text-lg font-semibold text-slate-100">{value}</p>
    </div>
  )
}

type MeshStatusPanelProps = {
  link: MeshLinkStatus
  health: MeshHealthStatus
  state: RouteState
}

export function MeshStatusPanel({ link, health, state }: MeshStatusPanelProps) {
  const relays = new Set(state.survivors.map((s) => s.relayNodeId).filter(Boolean)).size
  const highUrgency = state.survivors.filter((s) => s.urgency === 'high').length

  return (
    <section className="rescue-panel w-80 space-y-5" aria-label="Mesh network status">
      <header>
        <p className="rescue-eyebrow">BLE Mesh</p>
        <h2 className="text-xl font-semibold text-slate-50">Network Status</h2>
      </header>
      <div className="space-y-3">
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-300">Live feed</span>
          <span role="status" className={`font-semibold ${LINK_COLOR[link]}`}>
            {LINK_LABEL[link]}
          </span>
        </div>
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>Localization service</span>
          <span role="status" className={`font-semibold ${HEALTH_COLOR[health]}`}>
            {HEALTH_LABEL[health]}
          </span>
        </div>
        <div className="h-2 rounded-full bg-slate-800" aria-hidden="true">
          <div
            className={`h-2 rounded-full bg-gradient-to-r from-cyan-500 to-blue-500 ${LINK_BAR[link]}`}
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Stat label="Survivors" value={state.survivors.length} />
        <Stat label="High urgency" value={highUrgency} />
        <Stat label="Relay nodes" value={relays} />
        <Stat label="Weak-signal zones" value={state.hazards.length} />
      </div>
    </section>
  )
}
