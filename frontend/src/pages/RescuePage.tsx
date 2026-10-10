import { useMemo } from 'react'
import { CommandLog, MeshStatusPanel, RescueMap, SurvivorTriagePanel } from '../components/rescue'
import { useMeshHealth } from '../hooks/useMeshHealth'
import { useMeshRoute } from '../hooks/useMeshRoute'
import type { RouteState } from '../types/rescue'

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
  const { state, status, hasReceivedData, resetError, reset } = useMeshRoute()
  const health = useMeshHealth()
  const shown = state
  const lines = useMemo(() => logLines(shown), [shown])

  return (
    <div className="relative h-[calc(100vh-3.5rem)] w-full overflow-hidden bg-slate-950 text-slate-100">
      <div className="absolute inset-0 z-0">
        <RescueMap survivors={shown.survivors} />
      </div>
      <div className="pointer-events-none absolute inset-0 z-10 flex flex-col overflow-y-auto">
        {resetError && <p role="alert" className="pointer-events-auto bg-red-950 p-3 text-sm text-red-200">{resetError}</p>}
        {hasReceivedData && status !== 'open' && <p role="status" className="bg-amber-950 p-3 text-xs text-amber-200">Mesh disconnected; showing the last received picture.</p>}
        {!hasReceivedData && (
          <p
            role="status"
            className="pointer-events-auto mx-auto mt-4 rounded-full border border-amber-400/60 bg-amber-950/90 px-4 py-1 text-xs font-medium text-amber-100 shadow-lg"
          >
            Waiting for beacon data from the BLE mesh service
          </p>
        )}
        <div className="flex flex-1 flex-wrap items-start justify-between gap-4 p-4 md:p-6">
          <div className="pointer-events-auto">
            <MeshStatusPanel link={status} health={health} state={shown} />
          </div>
          <div className="pointer-events-auto">
            <SurvivorTriagePanel survivors={shown.survivors} onReset={reset} />
          </div>
        </div>
        <div className="pointer-events-auto p-6">
          <CommandLog lines={hasReceivedData ? lines : []} label={!hasReceivedData ? 'WAITING FOR DATA' : status === 'open' ? 'MESH SUMMARY' : 'LAST RECEIVED DATA'} />
        </div>
      </div>
    </div>
  )
}
