import React from 'react'
import type { AlertRead } from '../../types'
import { formatRelative } from '../../lib/format'
import PriorityBadge from '../PriorityBadge'

interface Props {
  alerts: AlertRead[]
  isLoading?: boolean
}

export default function AlertsPanel({ alerts, isLoading }: Props) {
  const sorted = [...alerts].sort((a, b) => {
    if (a.acknowledged !== b.acknowledged) return a.acknowledged ? 1 : -1
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-gray-700 flex-shrink-0 flex items-center justify-between">
        <span className="text-xs text-gray-400">
          {alerts.filter((a) => !a.acknowledged).length} unacknowledged
        </span>
        {isLoading && <span className="text-xs text-gray-500 animate-pulse">…</span>}
      </div>

      <div className="flex-1 overflow-y-auto">
        {sorted.length === 0 && (
          <p className="text-xs text-gray-500 p-4 text-center">No active alerts.</p>
        )}
        {sorted.map((a) => (
          <div
            key={a.id}
            className={`px-3 py-2.5 border-b border-gray-700 ${a.acknowledged ? 'opacity-50' : ''}`}
          >
            <div className="flex items-start justify-between gap-2 mb-1">
              <span className="text-sm font-medium text-white leading-snug">{a.title}</span>
              <PriorityBadge level={a.severity} />
            </div>
            <p className="text-xs text-gray-400 mb-1 line-clamp-2">{a.message}</p>
            {a.recommended_action && (
              <p className="text-xs text-blue-400 mb-1">→ {a.recommended_action}</p>
            )}
            <div className="flex items-center justify-between text-xs text-gray-500">
              <span className="font-mono">{Math.round(a.confidence_score * 100)}% conf</span>
              <span>{formatRelative(a.created_at)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
