import { useMemo } from 'react'
import { CommandLog, MeshStatusPanel, RescueMap, SurvivorTriagePanel } from '../components/rescue'
import { useMeshHealth } from '../hooks/useMeshHealth'
import { useMeshRoute } from '../hooks/useMeshRoute'
import type { RouteState } from '../types/rescue'

// Shown until the mesh service sends its first update, so the page is
// demonstrable without phones on the mesh. Clearly labelled as demo data.
const DEMO_STATE: RouteState = {
  path: [],
  survivors: [
    { id: 'S-14', position: { x: -8, y: 10, z: 1.1 }, urgency: 'high', lat: 17.452, lng: 78.381, relayNodeId: 'R-03' },
    { id: 'S-22', position: { x: 6, y: -4, z: 0.8 }, urgency: 'medium', lat: 17.448, lng: 78.385, relayNodeId: 'R-03' },
    { id: 'S-31', position: { x: 18, y: 14, z: 1.2 }, urgency: 'low', lat: 17.455, lng: 78.389, relayNodeId: 'R-07' },
  ],
  hazards: [{ id: 'HZ-1', position: { x: -16, y: 6, z: 0.5 } }],
}

function logLines(state: RouteState): string[] {
  const high = state.survivors.filter((s) => s.urgency === 'high')
  const relays = new Set(state.survivors.map((s) => s.relayNodeId).filter(Boolean))
  const lines = [
    `Mesh: ${state.survivors.length} survivor beacon${state.survivors.length === 1 ? '' : 's'} via ${relays.size} relay${relays.size === 1 ? '' : 's'}.`,
  ]
  high.forEach((s) => lines.push(`Triage: Beacon ${s.id} flagged HIGH urgency.`))
  if (state.hazards.length > 0) {
    lines.push(`Mesh: ${state.hazards.length} weak-signal zone${state.hazards.length === 1 ? '' : 's'} detected.`)
  }
  return lines
}

export default function RescuePage() {
  const { state, status, hasReceivedData, reset } = useMeshRoute()
  const health = useMeshHealth()
  const shown = hasReceivedData ? state : DEMO_STATE
  const lines = useMemo(() => logLines(shown), [shown])

  return (
    <div className="relative h-[calc(100vh-3.5rem)] w-full overflow-hidden bg-slate-950 text-slate-100">
      <div className="absolute inset-0 z-0">
        <RescueMap survivors={shown.survivors} />
      </div>
      <div className="pointer-events-none absolute inset-0 z-10 flex flex-col">
        {!hasReceivedData && (
          <p
            role="status"
            className="pointer-events-auto mx-auto mt-4 rounded-full border border-amber-400/60 bg-amber-950/90 px-4 py-1 text-xs font-medium text-amber-100 shadow-lg"
          >
            Demo data: waiting for the BLE mesh service
          </p>
        )}
        <div className="flex flex-1 items-start justify-between gap-4 p-6">
          <div className="pointer-events-auto">
            <MeshStatusPanel link={status} health={health} state={shown} />
          </div>
          <div className="pointer-events-auto">
            <SurvivorTriagePanel survivors={shown.survivors} onReset={reset} />
          </div>
        </div>
        <div className="pointer-events-auto p-6">
          <CommandLog lines={lines} />
        </div>
      </div>
    </div>
  )
}
