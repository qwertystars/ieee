// Top KPI strip — critical/high areas, active recs, blocked roads, alerts (DESIGN §11)

import React from 'react'
import type { DashboardSummary } from '../../types'
import { formatRelative } from '../../lib/format'

interface Props {
  summary: DashboardSummary | undefined
  isLoading?: boolean
}

function Kpi({ label, value, color = 'text-white' }: { label: string; value: React.ReactNode; color?: string }) {
  return (
    <div className="flex flex-col items-center px-4 py-1.5 border-r border-gray-700 last:border-r-0">
      <span className={`text-lg font-bold font-mono leading-none ${color}`}>{value}</span>
      <span className="text-xs text-gray-400 mt-0.5 whitespace-nowrap">{label}</span>
    </div>
  )
}

export default function DashboardSummaryBar({ summary, isLoading }: Props) {
  if (!summary && isLoading) {
    return (
      <div className="flex items-center px-3 py-1.5 bg-gray-900 border-b border-gray-800 text-xs text-gray-500 animate-pulse">
        Loading summary…
      </div>
    )
  }
  if (!summary) return null

  return (
    <div className="flex items-center bg-gray-900 border-b border-gray-800 overflow-x-auto flex-shrink-0">
      <Kpi label="Critical areas" value={summary.critical_areas} color="text-red-400" />
      <Kpi label="High areas" value={summary.high_areas} color="text-orange-400" />
      <Kpi label="Active recs" value={summary.active_recommendations} color="text-yellow-400" />
      <Kpi label="Pending tasks" value={summary.pending_tasks} />
      <Kpi label="Roads blocked" value={summary.roads_blocked} color={summary.roads_blocked > 0 ? 'text-red-400' : 'text-white'} />
      <Kpi label="Reports" value={summary.total_reports} />
      <Kpi label="Unverified" value={summary.unverified_reports} color={summary.unverified_reports > 0 ? 'text-yellow-400' : 'text-white'} />
      <Kpi label="Shelters open" value={`${summary.shelters_open}/${summary.shelters_open + summary.shelters_full}`} color="text-green-400" />
      <Kpi label="Alerts" value={summary.alerts_active} color={summary.alerts_active > 0 ? 'text-red-400' : 'text-white'} />
      <div className="ml-auto px-3 text-xs text-gray-500 whitespace-nowrap flex-shrink-0">
        {formatRelative(summary.last_updated)}
      </div>
    </div>
  )
}
