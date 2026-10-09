"use client";

import type { ReactNode } from "react";

type HudStatProps = {
  icon: ReactNode;
  label: string;
  value: string;
};

export function HudStat({ icon, label, value }: HudStatProps) {
  return (
    <div className="hud-stat">
      {icon}
      <div>
        <p className="text-xs text-slate-400">{label}</p>
        <p className="text-lg font-semibold">{value}</p>
      </div>
    </div>
  );
}
