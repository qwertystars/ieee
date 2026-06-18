// Road status panel — mark roads blocked / open / dangerous with 15s polling

import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { roadsApi } from '../../api/client'
import type { RoadStatusEnum } from '../../types'
import { formatRelative } from '../../lib/format'

const STATUS_COLOR: Record<RoadStatusEnum, string> = {
  open:              'text-green-400',
  blocked:           'text-red-400',
  partially_blocked: 'text-orange-400',
  dangerous:         'text-yellow-300',
  unknown:           'text-gray-400',
}

interface Props {
  eventId: string
}

export default function RoadStatusUpdater({ eventId }: Props) {
  const qc = useQueryClient()
  const [updating, setUpdating] = useState<string | null>(null)

  const { data: roads, isLoading, isError, refetch } = useQuery({
    queryKey: ['roads', eventId],
    queryFn: () => roadsApi.list(eventId),
    enabled: !!eventId,
    refetchInterval: 15_000,
  })

  const mutation = useMutation({
    mutationFn: ({
      id,
      status,
      reason,
    }: {
      id: string
      status: string
      reason?: string
    }) => roadsApi.patchStatus(id, { status, reason, confidence_score: 0.9 }),
    onMutate: (vars) => setUpdating(vars.id),
    onSettled: () => {
      setUpdating(null)
      qc.invalidateQueries({ queryKey: ['roads', eventId] })
    },
  })

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-20 rounded-lg bg-gray-800 animate-pulse" />
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="text-center py-10">
        <p className="text-sm text-red-400 mb-3">Failed to load road data</p>
        <button onClick={() => refetch()} className="text-xs text-blue-400 underline">
          Retry
        </button>
      </div>
    )
  }

  if (!roads?.length) {
    return (
      <div className="text-center py-14 text-gray-500 text-sm">
        No road data for this event
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {roads.map((road) => {
        const busy = updating === road.id
        return (
          <div key={road.id} className="rounded-lg border border-gray-700 bg-gray-900 p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-white">{road.road_name}</span>
              <span className="text-xs text-gray-600">{formatRelative(road.updated_at)}</span>
            </div>

            <div className="flex items-center gap-2 mb-2">
              <span className={`text-xs font-semibold ${STATUS_COLOR[road.status]}`}>
                {road.status.replace('_', ' ')}
              </span>
              {road.reason && (
                <span className="text-xs text-gray-500 truncate">· {road.reason}</span>
              )}
            </div>

            <div className="grid grid-cols-3 gap-1.5">
              <button
                onClick={() =>
                  mutation.mutate({
                    id: road.id,
                    status: 'blocked',
                    reason: 'Field report: road blocked',
                  })
                }
                disabled={road.status === 'blocked' || busy}
                className="py-1.5 text-xs rounded bg-red-900 text-red-200 disabled:opacity-40 hover:bg-red-800 transition-colors"
              >
                🚧 Blocked
              </button>
              <button
                onClick={() =>
                  mutation.mutate({
                    id: road.id,
                    status: 'dangerous',
                    reason: 'Field report: dangerous conditions',
                  })
                }
                disabled={road.status === 'dangerous' || busy}
                className="py-1.5 text-xs rounded bg-yellow-900 text-yellow-200 disabled:opacity-40 hover:bg-yellow-800 transition-colors"
              >
                ⚠️ Danger
              </button>
              <button
                onClick={() =>
                  mutation.mutate({ id: road.id, status: 'open' })
                }
                disabled={road.status === 'open' || busy}
                className="py-1.5 text-xs rounded bg-green-900 text-green-200 disabled:opacity-40 hover:bg-green-800 transition-colors"
              >
                ✓ Open
              </button>
            </div>

            {busy && (
              <p className="text-xs text-gray-500 mt-1.5 text-center animate-pulse">
                Updating…
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
