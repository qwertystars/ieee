"use client";

import { useEffect, useState } from "react";

const DEFAULT_API_URL = "http://127.0.0.1:8000";

export type ApiHealthStatus = "checking" | "online" | "offline";

export function useApiHealth(baseUrl = DEFAULT_API_URL) {
  const [status, setStatus] = useState<ApiHealthStatus>("checking");

  useEffect(() => {
    let isMounted = true;
    let timer: number | null = null;

    const check = async () => {
      try {
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), 3000);
        const response = await fetch(`${baseUrl}/health`, {
          signal: controller.signal,
          cache: "no-store",
        });
        window.clearTimeout(timeout);

        if (!isMounted) return;
        setStatus(response.ok ? "online" : "offline");
      } catch {
        if (!isMounted) return;
        setStatus("offline");
      }

      timer = window.setTimeout(check, 5000);
    };

    check();

    return () => {
      isMounted = false;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [baseUrl]);

  return status;
}
