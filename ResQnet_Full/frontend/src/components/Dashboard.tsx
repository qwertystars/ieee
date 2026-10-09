"use client";

import { useMemo } from "react";
import dynamic from "next/dynamic";
import type { RouteState } from "@/types/route";
import { useApiHealth } from "@/hooks/useApiHealth";
import { useWebSocket } from "@/hooks/useWebSocket";
import { HudOverlay } from "@/components/hud/HudOverlay";

const MapCanvas = dynamic(() => import("@/components/scene/MapCanvas"), { 
  ssr: false,
  loading: () => <div className="h-full w-full bg-slate-950 flex items-center justify-center text-cyan-400 animate-pulse font-mono tracking-widest text-sm">INITIALIZING MAP SYSTEM...</div>
});

const fallbackState: RouteState = {
  path: [
    { x: -22, y: -18, z: 0.8 },
    { x: -12, y: -6, z: 1.2 },
    { x: -4, y: 6, z: 0.6 },
    { x: 8, y: 12, z: 1.1 },
    { x: 20, y: 4, z: 0.4 },
  ],
  survivors: [
    { id: "S-14", position: { x: -8, y: 10, z: 1.1 }, urgency: "high", lat: 12.8406, lng: 80.1534 },
    { id: "S-22", position: { x: 6, y: -4, z: 0.8 }, urgency: "medium", lat: 12.8420, lng: 80.1550 },
    { id: "S-31", position: { x: 18, y: 14, z: 1.2 }, urgency: "low", lat: 12.8390, lng: 80.1520 },
  ],
  hazards: [
    { id: "HZ-01", position: { x: -16, y: 6, z: 0.5 } },
    { id: "HZ-02", position: { x: 10, y: -14, z: 0.7 } },
  ],
};

const commandLog = [
  "AI: New hazard detected. Rerouting...",
  "Mesh: Relay node 12 reconnected.",
  "AI: Survivor cluster flagged in sector E7.",
  "Command: Dispatching unit Delta-2.",
];

export default function Dashboard() {
  const { state, status, hasReceivedData, reset } = useWebSocket();
  const apiStatus = useApiHealth();

  const mergedState = useMemo<RouteState>(() => {
    if (hasReceivedData) {
      return state;
    }
    return fallbackState;
  }, [hasReceivedData, state]);

  return (
    <div className="relative h-screen overflow-hidden bg-slate-950 text-slate-100">
      <div className="absolute inset-0 z-0">
        <MapCanvas
          path={mergedState.path}
          survivors={mergedState.survivors}
          hazards={mergedState.hazards}
        />
      </div>
      <HudOverlay
        survivors={mergedState.survivors}
        status={status}
        apiStatus={apiStatus}
        logLines={commandLog}
        onReset={reset}
      />
    </div>
  );
}
