// Left sidebar: priority-ranked area assessments — primary operational tool (DESIGN §11)

import React from 'react'
import type { AreaAssessmentRead } from '../../types'
import ConfidenceBadge from '../ConfidenceBadge'
import PriorityBadge from '../PriorityBadge'

interface Props {
  areas: AreaAssessmentRead[]
  selectedId: string | null
  onSelect: (id: string) => void
  isLoading?: boolean
}

export default function PriorityList({ areas, selectedId, onSelect, isLoading }: Props) {
  // Sort by overall_priority_score descending
  const sorted = [...areas].sort((a, b) => b.overall_priority_score - a.overall_priority_score)

  return (
    <div className="flex flex-col h-full bg-gray-900 border-r border-gray-800">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-800 flex-shrink-0">
        <h2 className="text-sm font-semibold text-white">Priority Areas</h2>
        {isLoading && <span className="text-xs text-gray-500 animate-pulse">updating…</span>}
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {sorted.length === 0 && !isLoading && (
          <p className="text-xs text-gray-500 p-4 text-center">No areas assessed yet.</p>
        )}
        {sorted.map((area, idx) => (
          <button
            key={area.id}
            onClick={() => onSelect(area.id)}
            className={`w-full text-left px-3 py-3 border-b border-gray-800 transition-colors hover:bg-gray-800 ${
              selectedId === area.id ? 'bg-gray-800 border-l-2 border-l-orange-500' : ''
            }`}
          >
            <div className="flex items-start justify-between gap-2 mb-1">
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-xs font-bold text-gray-500 flex-shrink-0">#{idx + 1}</span>
                <span className="text-sm font-medium text-white truncate">{area.area_name}</span>
              </div>
              <PriorityBadge level={area.priority_level} />
            </div>

            {/* Score bar */}
            <div className="flex items-center gap-2 mb-1.5">
              <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-orange-500 rounded-full transition-all"
                  style={{ width: `${Math.min(area.overall_priority_score, 100)}%` }}
                />
              </div>
              <span className="text-xs font-mono text-gray-400 flex-shrink-0">
                {area.overall_priority_score.toFixed(1)}
              </span>
            </div>

            {area.summary && (
              <p className="text-xs text-gray-400 line-clamp-2 mb-1.5">{area.summary}</p>
            )}

            <ConfidenceBadge
              confidence={area.hazard_score / 100}
              updatedAt={area.updated_at}
            />
          </button>
        ))}
      </div>
    </div>
  )
}
