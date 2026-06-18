import React from 'react'
import type { ResponseTeamRead } from '../../types'
import { formatRelative } from '../../lib/format'

interface Props {
  teams: ResponseTeamRead[]
  isLoading?: boolean
}

const STATUS_STYLE: Record<string, string> = {
  available: 'bg-green-900 text-green-300',
  deployed: 'bg-blue-900 text-blue-300',
  en_route: 'bg-yellow-900 text-yellow-300',
  on_site: 'bg-orange-900 text-orange-300',
  unavailable: 'bg-gray-800 text-gray-500',
}

const TYPE_ICON: Record<string, string> = {
  rescue: '🚁',
  medical: '🏥',
  logistics: '🚛',
  engineering: '🔧',
  coordination: '📡',
}

export default function TeamsPanel({ teams, isLoading }: Props) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-gray-700 flex-shrink-0 flex items-center justify-between">
        <span className="text-xs text-gray-400">
          {teams.filter((t) => t.status === 'deployed' || t.status === 'on_site').length} deployed · {teams.length} total
        </span>
        {isLoading && <span className="text-xs text-gray-500 animate-pulse">…</span>}
      </div>

      <div className="flex-1 overflow-y-auto">
        {teams.length === 0 && (
          <p className="text-xs text-gray-500 p-4 text-center">No team data.</p>
        )}
        {teams.map((t) => (
          <div key={t.id} className="px-3 py-2.5 border-b border-gray-700">
            <div className="flex items-center justify-between mb-0.5">
              <div className="flex items-center gap-1.5 min-w-0">
                <span>{TYPE_ICON[t.team_type] ?? '👥'}</span>
                <span className="text-sm font-medium text-white truncate">{t.name}</span>
              </div>
              <span className={`text-xs px-1.5 py-0.5 rounded flex-shrink-0 ${STATUS_STYLE[t.status] ?? STATUS_STYLE['unavailable']}`}>
                {t.status}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs text-gray-500 mt-0.5">
              <span>Cap: {t.capacity}</span>
              {t.assigned_task_id && (
                <span className="text-blue-400 truncate ml-2">task assigned</span>
              )}
              <span className="ml-auto">{formatRelative(t.updated_at)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
