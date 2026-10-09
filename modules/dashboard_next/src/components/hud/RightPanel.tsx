"use client";

import { HeartPulse, RotateCcw, ShieldAlert } from "lucide-react";
import type { Survivor } from "@/types/route";

type RightPanelProps = {
  survivors: Survivor[];
  onReset: () => void;
};

const urgencyBadge: Record<Survivor["urgency"], string> = {
  low: "bg-blue-500/20 text-blue-200",
  medium: "bg-cyan-500/20 text-cyan-100",
  high: "bg-red-500/20 text-red-200",
};

export function RightPanel({ survivors, onReset }: RightPanelProps) {
  return (
    <section className="hud-panel w-96 space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <p className="hud-eyebrow">Survivor Triage</p>
          <h2 className="hud-title">Priority Signals</h2>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span className="rounded-full border border-white/10 px-2 py-1">
            Found {survivors.length}
          </span>
          <button
            type="button"
            onClick={onReset}
            className="flex items-center gap-1 rounded-full border border-white/10 px-2 py-1 text-[11px] text-slate-200 transition hover:border-cyan-400/40 hover:text-cyan-200"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Reset
          </button>
          <ShieldAlert className="h-5 w-5 text-red-400" />
        </div>
      </header>
      <div className="space-y-3">
        {survivors.length === 0 ? (
          <p className="text-sm text-slate-400">No survivors detected yet.</p>
        ) : (
          survivors.map((survivor) => (
            <div
              key={survivor.id}
              className="flex items-center justify-between rounded-xl border border-white/5 bg-slate-900/60 px-4 py-3"
            >
              <div className="flex items-center gap-3">
                <HeartPulse className="h-4 w-4 text-cyan-300" />
                <div>
                  <p className="text-sm font-semibold text-slate-100">Beacon {survivor.id}</p>

                  {survivor.lat !== undefined && survivor.lng !== undefined && (
                    <p className="text-[10px] text-cyan-400/80">
                      GPS: {survivor.lat.toFixed(6)}, {survivor.lng.toFixed(6)}
                    </p>
                  )}
                  <p className="text-[11px] text-slate-500">
                    Relay: {survivor.relayNodeId ?? "Unknown"}
                  </p>
                </div>
              </div>
              <span
                className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${
                  urgencyBadge[survivor.urgency]
                }`}
              >
                {survivor.urgency}
              </span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
