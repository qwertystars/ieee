import React from 'react'
import type { ShelterRead } from '../../types'
import { formatCapacity, formatRelative } from '../../lib/format'

interface Props {
  shelters: ShelterRead[]
  isLoading?: boolean
}

const STATUS_STYLE: Record<string, string> = {
  open: 'bg-green-900 text-green-300',
  full: 'bg-red-900 text-red-300',
  closed: 'bg-gray-800 text-gray-400',
  evacuated: 'bg-yellow-900 text-yellow-300',
}

export default function SheltersPanel({ shelters, isLoading }: Props) {
  const sorted = [...shelters].sort((a, b) => {
    const order = ['open', 'full', 'evacuated', 'closed']
    return order.indexOf(a.status) - order.indexOf(b.status)
  })

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-gray-700 flex-shrink-0 flex items-center justify-between">
        <span className="text-xs text-gray-400">
          {shelters.filter((s) => s.status === 'open').length} open ·{' '}
          {shelters.reduce((s, sh) => s + sh.available_capacity, 0)} beds available
        </span>
        {isLoading && <span className="text-xs text-gray-500 animate-pulse">…</span>}
      </div>

      <div className="flex-1 overflow-y-auto">
        {sorted.length === 0 && (
          <p className="text-xs text-gray-500 p-4 text-center">No shelter data.</p>
        )}
        {sorted.map((s) => (
          <div key={s.id} className="px-3 py-2.5 border-b border-gray-700">
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-white truncate mr-2">{s.name}</span>
              <span className={`text-xs px-1.5 py-0.5 rounded flex-shrink-0 ${STATUS_STYLE[s.status] ?? STATUS_STYLE['closed']}`}>
                {s.status}
              </span>
            </div>

            {/* Occupancy bar */}
            <div className="flex items-center gap-2 mb-1">
              <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    s.total_capacity > 0 && s.current_occupancy / s.total_capacity > 0.9
                      ? 'bg-red-500'
                      : 'bg-green-500'
                  }`}
                  style={{
                    width: s.total_capacity > 0
                      ? `${Math.min((s.current_occupancy / s.total_capacity) * 100, 100)}%`
                      : '0%',
                  }}
                />
              </div>
              <span className="text-xs font-mono text-gray-400 flex-shrink-0">
                {formatCapacity(s.current_occupancy, s.total_capacity)}
              </span>
            </div>

            <div className="flex gap-2 text-xs text-gray-500">
              {s.medical_support && <span className="text-blue-400">🏥 Medical</span>}
              {s.accessibility_support && <span className="text-green-400">♿ Access</span>}
              <span className="ml-auto">{formatRelative(s.updated_at)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
