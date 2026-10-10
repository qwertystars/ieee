import type { Survivor } from '../../types/rescue'

const URGENCY_BADGE: Record<Survivor['urgency'], string> = {
  low: 'bg-blue-500/20 text-blue-200',
  medium: 'bg-cyan-500/20 text-cyan-100',
  high: 'bg-red-500/20 text-red-200',
}

const URGENCY_RANK: Record<Survivor['urgency'], number> = { high: 0, medium: 1, low: 2 }

type SurvivorTriagePanelProps = {
  survivors: Survivor[]
  onReset: () => void
}

export function SurvivorTriagePanel({ survivors, onReset }: SurvivorTriagePanelProps) {
  const sorted = [...survivors].sort((a, b) => URGENCY_RANK[a.urgency] - URGENCY_RANK[b.urgency])

  return (
    <section className="rescue-panel w-full max-w-[24rem] space-y-4" aria-label="Survivor triage">
      <header className="flex items-center justify-between">
        <div>
          <p className="rescue-eyebrow">Survivor Beacons</p>
          <h2 className="text-xl font-semibold text-slate-50">Priority Signals</h2>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span className="rounded-full border border-white/10 px-2 py-1">
            Found {survivors.length}
          </span>
          <button
            type="button"
            onClick={onReset}
            className="rounded-full border border-white/10 px-2 py-1 text-[11px] text-slate-200 transition hover:border-cyan-400/40 hover:text-cyan-200 focus:outline-none focus:ring-2 focus:ring-cyan-500"
          >
            Reset
          </button>
        </div>
      </header>
      <p className="text-xs text-amber-200">Signal priority reflects RSSI, not medical urgency. GPS marks the reporting relay.</p>
      {sorted.length === 0 ? (
        <p className="text-sm text-slate-400">No survivors detected yet.</p>
      ) : (
        <ul className="max-h-[50vh] space-y-3 overflow-y-auto">
          {sorted.map((survivor) => (
            <li
              key={survivor.id}
              className="flex items-center justify-between rounded-xl border border-white/5 bg-slate-900/60 px-4 py-3"
            >
              <div>
                <p className="text-sm font-semibold text-slate-100">Beacon {survivor.id}</p>
                {survivor.lat !== undefined && survivor.lng !== undefined && (
                  <p className="font-mono text-[10px] text-cyan-400/80">
                    Relay GPS {survivor.lat.toFixed(6)}, {survivor.lng.toFixed(6)}
                  </p>
                )}
                <p className="text-[11px] text-slate-500">
                  Relay: {survivor.relayNodeId ?? 'Unknown'}
                </p>
              </div>
              <span
                className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${URGENCY_BADGE[survivor.urgency]}`}
              >
                {survivor.urgency}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
