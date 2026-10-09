"use client";

import { motion } from "framer-motion";
import type { Survivor } from "@/types/route";
import type { ApiHealthStatus } from "@/hooks/useApiHealth";
import { CommandLog } from "./CommandLog";
import { LeftPanel } from "./LeftPanel";
import { RightPanel } from "./RightPanel";

type HudOverlayProps = {
  survivors: Survivor[];
  status: "connecting" | "open" | "closed" | "error";
  apiStatus: ApiHealthStatus;
  logLines: string[];
  onReset: () => void;
};

export function HudOverlay({
  survivors,
  status,
  apiStatus,
  logLines,
  onReset,
}: HudOverlayProps) {
  return (
    <motion.div
      className="pointer-events-none absolute inset-0 z-10 flex h-full w-full flex-col"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.8, ease: "easeOut" }}
    >
      <div className="flex flex-1 items-start justify-between p-6">
        <div className="pointer-events-auto">
          <LeftPanel status={status} apiStatus={apiStatus} />
        </div>
        <div className="pointer-events-auto">
          <RightPanel survivors={survivors} onReset={onReset} />
        </div>
      </div>
      <div className="pointer-events-auto p-6">
        <CommandLog logLines={logLines} />
      </div>
    </motion.div>
  );
}
