"use client";

import { useEffect, useMemo, useState } from "react";

type CommandLogProps = {
  logLines: string[];
};

export function CommandLog({ logLines }: CommandLogProps) {
  const lines = useMemo(
    () => (logLines.length ? logLines : ["AI: Awaiting inbound telemetry..."]),
    [logLines]
  );
  const [lineIndex, setLineIndex] = useState(0);
  const [typedLine, setTypedLine] = useState("");

  useEffect(() => {
    const line = lines[lineIndex % lines.length];
    let cursor = 0;
    setTypedLine("");

    const interval = window.setInterval(() => {
      cursor += 1;
      setTypedLine(line.slice(0, cursor));
      if (cursor >= line.length) {
        window.clearInterval(interval);
      }
    }, 32);

    const timeout = window.setTimeout(() => {
      setLineIndex((prev) => (prev + 1) % lines.length);
    }, 2200);

    return () => {
      window.clearInterval(interval);
      window.clearTimeout(timeout);
    };
  }, [lineIndex, lines]);

  return (
    <section className="hud-panel w-full">
      <header className="flex items-center justify-between">
        <p className="hud-eyebrow">Command Log</p>
        <span className="text-xs text-slate-400">LIVE FEED</span>
      </header>
      <div className="mt-4 rounded-xl bg-black/50 px-4 py-3 font-mono text-xs text-cyan-200">
        <span className="text-cyan-500">&gt;</span> {typedLine}
      </div>
    </section>
  );
}
