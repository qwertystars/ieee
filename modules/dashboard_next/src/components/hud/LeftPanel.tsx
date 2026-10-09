"use client";

import { Activity, Cpu, Radar, Wifi } from "lucide-react";
import type { ApiHealthStatus } from "@/hooks/useApiHealth";

type LeftPanelProps = {
  status: "connecting" | "open" | "closed" | "error";
  apiStatus: ApiHealthStatus;
};

const statusLabel: Record<LeftPanelProps["status"], string> = {
  connecting: "Linking...",
  open: "Online",
  closed: "Offline",
  error: "Interference",
};

const statusColor: Record<LeftPanelProps["status"], string> = {
  connecting: "text-cyan-300",
  open: "text-emerald-300",
  closed: "text-amber-300",
  error: "text-red-400",
};

const apiStatusLabel: Record<ApiHealthStatus, string> = {
  checking: "Checking...",
  online: "Online",
  offline: "Offline",
};

const apiStatusColor: Record<ApiHealthStatus, string> = {
  checking: "text-cyan-300",
  online: "text-emerald-300",
  offline: "text-red-400",
};

const healthBarWidth: Record<LeftPanelProps["status"], string> = {
  connecting: "w-2/3",
  open: "w-full",
  closed: "w-1/4",
  error: "w-1/3",
};

export function LeftPanel({ status, apiStatus }: LeftPanelProps) {
  return (
    <section className="hud-panel w-80 space-y-5">
      <header className="flex items-center justify-between">
        <div>
          <p className="hud-eyebrow">Active Rescue Units</p>
          <h2 className="hud-title">Delta Wing</h2>
        </div>
        <Activity className="h-5 w-5 text-cyan-300" />
      </header>
      <div className="space-y-3">
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-300">Mesh Network Health</span>
          <span className={`font-semibold ${statusColor[status]}`}>{statusLabel[status]}</span>
        </div>
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>Command Center</span>
          <span className={`font-semibold ${apiStatusColor[apiStatus]}`}>
            {apiStatusLabel[apiStatus]}
          </span>
        </div>
        <div className="h-2 rounded-full bg-slate-800">
          <div
            className={`h-2 rounded-full bg-gradient-to-r from-cyan-500 to-blue-500 ${
              healthBarWidth[status]
            }`}
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm text-slate-200">
        <div className="hud-stat">
          <Radar className="h-4 w-4 text-blue-300" />
          <div>
            <p className="text-xs text-slate-400">Scans Active</p>
            <p className="text-lg font-semibold">14</p>
          </div>
        </div>
        <div className="hud-stat">
          <Wifi className="h-4 w-4 text-cyan-300" />
          <div>
            <p className="text-xs text-slate-400">Relay Nodes</p>
            <p className="text-lg font-semibold">52</p>
          </div>
        </div>
        <div className="hud-stat">
          <Cpu className="h-4 w-4 text-blue-300" />
          <div>
            <p className="text-xs text-slate-400">AI Latency</p>
            <p className="text-lg font-semibold">320ms</p>
          </div>
        </div>
        <div className="hud-stat">
          <Activity className="h-4 w-4 text-cyan-300" />
          <div>
            <p className="text-xs text-slate-400">Units Online</p>
            <p className="text-lg font-semibold">8</p>
          </div>
        </div>
      </div>
    </section>
  );
}
