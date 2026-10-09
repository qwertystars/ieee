"use client";

import { useEffect, useRef, useState } from "react";
import type { Hazard, RouteState, Survivor, Vec3 } from "@/types/route";

const DEFAULT_URL = "ws://127.0.0.1:8000/ws/route";

const emptyState: RouteState = {
  path: [],
  survivors: [],
  hazards: [],
};

const toHttpBase = (wsUrl: string) => {
  try {
    const parsed = new URL(wsUrl);
    const protocol = parsed.protocol === "wss:" ? "https:" : "http:";
    return `${protocol}//${parsed.host}`;
  } catch {
    return "";
  }
};

const normalizeVec3 = (value: unknown): Vec3 | null => {
  if (Array.isArray(value)) {
    const [x, y, z] = value;
    if (typeof x === "number" && typeof y === "number") {
      return { x, y, z: typeof z === "number" ? z : 0 };
    }
  }

  if (value && typeof value === "object") {
    const { x, y, z } = value as { x?: unknown; y?: unknown; z?: unknown };
    if (typeof x === "number" && typeof y === "number") {
      return { x, y, z: typeof z === "number" ? z : 0 };
    }
  }

  return null;
};

const mapSurvivor = (value: unknown, index: number): Survivor | null => {
  if (!value || typeof value !== "object") return null;

  const data = value as {
    id?: string | number;
    position?: unknown;
    x?: unknown;
    y?: unknown;
    z?: unknown;
    urgency?: "low" | "medium" | "high" | string;
    relay_node_id?: string;
    relayNodeId?: string;
    confidence?: number;
    lat?: number;
    lng?: number;
  };

  const position = normalizeVec3(data.position ?? data);
  if (!position) return null;

  const urgency =
    data.urgency === "high" || data.urgency === "medium" || data.urgency === "low"
      ? data.urgency
      : "medium";

  return {
    id: data.id ? String(data.id) : `S-${index + 1}`,
    position,
    urgency,
    relayNodeId: data.relayNodeId ?? data.relay_node_id,
    confidence: typeof data.confidence === "number" ? data.confidence : undefined,
    lat: typeof data.lat === "number" ? data.lat : undefined,
    lng: typeof data.lng === "number" ? data.lng : undefined,
  };
};

const mapHazard = (value: unknown, index: number): Hazard | null => {
  const position = normalizeVec3(value);
  if (!position) return null;

  return {
    id: `HZ-${index + 1}`,
    position,
  };
};

export function useWebSocket(url = DEFAULT_URL) {
  const [state, setState] = useState<RouteState>(emptyState);
  const [hasReceivedData, setHasReceivedData] = useState(false);
  const [status, setStatus] = useState<"connecting" | "open" | "closed" | "error">(
    "connecting"
  );
  const retryRef = useRef<number | null>(null);

  const reset = async () => {
    setState(emptyState);
    setHasReceivedData(true);

    const baseUrl = toHttpBase(url);
    if (!baseUrl) return;

    try {
      await fetch(`${baseUrl}/api/mesh/reset`, {
        method: "POST",
      });
    } catch {
      // Keep local state cleared even if backend reset fails.
    }
  };

  useEffect(() => {
    let socket: WebSocket | null = null;
    let isMounted = true;

    const connect = () => {
      if (!isMounted) return;

      setStatus("connecting");
      socket = new WebSocket(url);

      socket.onopen = () => {
        if (!isMounted) return;
        setStatus("open");
      };

      socket.onmessage = (event) => {
        if (!isMounted) return;

        try {
          const payload = JSON.parse(event.data);

          const path = Array.isArray(payload.path)
            ? payload.path
                .map(normalizeVec3)
                .filter((point): point is Vec3 => Boolean(point))
            : [];

          const survivors = Array.isArray(payload.survivors)
            ? payload.survivors
                .map(mapSurvivor)
                .filter((survivor): survivor is Survivor => Boolean(survivor))
            : [];

          const hazardSource =
            payload.blocked_edges ?? payload.blocked_nodes ?? payload.hazards ?? [];
          const hazards = Array.isArray(hazardSource)
            ? hazardSource
                .map(mapHazard)
                .filter((hazard): hazard is Hazard => Boolean(hazard))
            : [];

          setState({ path, survivors, hazards });
          setHasReceivedData(true);
        } catch {
          setStatus("error");
        }
      };

      socket.onerror = () => {
        if (!isMounted) return;
        setStatus("error");
      };

      socket.onclose = () => {
        if (!isMounted) return;
        setStatus("closed");
        retryRef.current = window.setTimeout(connect, 2000);
      };
    };

    connect();

    return () => {
      isMounted = false;
      if (retryRef.current) {
        window.clearTimeout(retryRef.current);
      }
      socket?.close();
    };
  }, [url]);

  return { state, status, hasReceivedData, reset };
}
