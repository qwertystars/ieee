// Right panel: recommendations with approve + dismiss actions (DESIGN §11)

import React, { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { recommendationsApi } from '../../api/client'
import type { RecommendationRead } from '../../types'
import ConfidenceBadge from '../ConfidenceBadge'
import PriorityBadge from '../PriorityBadge'

interface Props {
  recommendations: RecommendationRead[]
  eventId: string
  isLoading?: boolean
}

const STATUS_ORDER = ['draft', 'reviewed', 'approved', 'assigned', 'in_progress', 'completed', 'dismissed']

export default function RecommendationsPanel({ recommendations, eventId, isLoading }: Props) {
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState<'active' | 'all'>('active')

  const active = ['draft', 'reviewed', 'approved', 'assigned', 'in_progress']
  const filtered = filter === 'active'
    ? recommendations.filter((r) => active.includes(r.status))
    : recommendations

  const sorted = [...filtered].sort((a, b) => {
    // urgency first, then status order
    const urgencyOrder = ['critical', 'high', 'medium', 'low']
    const ua = urgencyOrder.indexOf(a.urgency)
    const ub = urgencyOrder.indexOf(b.urgency)
    if (ua !== ub) return ua - ub
    return STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status)
  })

  const approveMutation = useMutation({
    mutationFn: (id: string) => recommendationsApi.approve(eventId, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['recommendations', eventId] }),
  })
  const dismissMutation = useMutation({
    mutationFn: (id: string) => recommendationsApi.dismiss(eventId, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['recommendations', eventId] }),
  })

  return (
    <div className="flex flex-col h-full">
      {/* Sub-header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-700 flex-shrink-0">
        <div className="flex gap-2">
          {(['active', 'all'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-xs px-2 py-0.5 rounded transition-colors ${
                filter === f ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              {f === 'active' ? 'Active' : 'All'}{' '}
              <span className="text-gray-500">
                ({f === 'active'
                  ? recommendations.filter((r) => active.includes(r.status)).length
                  : recommendations.length})
              </span>
            </button>
          ))}
        </div>
        {isLoading && <span className="text-xs text-gray-500 animate-pulse">…</span>}
      </div>

      <div className="flex-1 overflow-y-auto">
        {sorted.length === 0 && (
          <p className="text-xs text-gray-500 p-4 text-center">No recommendations.</p>
        )}
        {sorted.map((rec) => (
          <div key={rec.id} className="px-3 py-3 border-b border-gray-700">
            <div className="flex items-start justify-between gap-2 mb-1">
              <span className="text-sm font-medium text-white leading-snug">{rec.title}</span>
              <PriorityBadge level={rec.urgency} />
            </div>

            <p className="text-xs text-gray-400 mb-1.5 line-clamp-2">{rec.description}</p>

            {rec.reasoning && (
              <p className="text-xs text-gray-500 italic mb-1.5 line-clamp-1">
                {rec.reasoning}
              </p>
            )}

            <div className="flex items-center justify-between">
              <ConfidenceBadge confidence={rec.confidence_score} updatedAt={rec.updated_at} />
              <span className={`text-xs px-1.5 py-0.5 rounded ${
                rec.status === 'approved' || rec.status === 'in_progress'
                  ? 'bg-green-900 text-green-300'
                  : rec.status === 'dismissed'
                  ? 'bg-gray-800 text-gray-500'
                  : 'bg-yellow-900 text-yellow-300'
              }`}>
                {rec.status}
              </span>
            </div>

            {/* Human-approval actions — life-critical DESIGN §12 */}
            {(rec.status === 'draft' || rec.status === 'reviewed') && (
              <div className="flex gap-2 mt-2">
                <button
                  onClick={() => approveMutation.mutate(rec.id)}
                  disabled={approveMutation.isPending}
                  className="flex-1 py-1 text-xs font-medium bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white rounded transition-colors"
                >
                  ✓ Approve
                </button>
                <button
                  onClick={() => dismissMutation.mutate(rec.id)}
                  disabled={dismissMutation.isPending}
                  className="flex-1 py-1 text-xs font-medium bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-gray-300 rounded transition-colors"
                >
                  ✕ Dismiss
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
