// Single task card with optimistic status update buttons

import React, { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { tasksApi } from '../../api/client'
import type { TaskRead, TaskStatus } from '../../types'
import { formatRelative } from '../../lib/format'

interface StatusAction {
  from: TaskStatus[]
  to: TaskStatus
  label: string
  color: string
}

const STATUS_ACTIONS: StatusAction[] = [
  { from: ['assigned'],                           to: 'accepted',  label: 'Accept',    color: 'bg-blue-700 hover:bg-blue-600' },
  { from: ['accepted'],                           to: 'en_route',  label: 'En Route',  color: 'bg-yellow-700 hover:bg-yellow-600' },
  { from: ['en_route'],                           to: 'on_site',   label: 'On Site',   color: 'bg-orange-700 hover:bg-orange-600' },
  { from: ['on_site'],                            to: 'completed', label: 'Complete',  color: 'bg-green-700 hover:bg-green-600' },
  { from: ['accepted', 'en_route', 'on_site'],    to: 'blocked',   label: 'Blocked',   color: 'bg-red-800 hover:bg-red-700' },
]

const PRIORITY_PILL: Record<string, string> = {
  critical: 'bg-red-800 text-red-200',
  high:     'bg-orange-800 text-orange-200',
  medium:   'bg-yellow-800 text-yellow-200',
  low:      'bg-green-800 text-green-200',
}

const STATUS_PILL: Record<string, string> = {
  assigned:   'bg-blue-900 text-blue-300',
  accepted:   'bg-blue-700 text-blue-100',
  en_route:   'bg-yellow-800 text-yellow-100',
  on_site:    'bg-orange-800 text-orange-100',
  completed:  'bg-green-800 text-green-100',
  blocked:    'bg-red-900 text-red-200',
  cancelled:  'bg-gray-800 text-gray-400',
}

interface Props {
  task: TaskRead
}

export default function TaskCard({ task }: Props) {
  const qc = useQueryClient()
  const [optimisticStatus, setOptimisticStatus] = useState<TaskStatus | null>(null)
  const currentStatus = optimisticStatus ?? task.status
  const isDone = currentStatus === 'completed' || currentStatus === 'cancelled'

  const mutation = useMutation({
    mutationFn: (newStatus: TaskStatus) => tasksApi.patch(task.id, { status: newStatus }),
    onMutate: (newStatus) => setOptimisticStatus(newStatus),
    onSuccess: () => {
      setOptimisticStatus(null)
      qc.invalidateQueries({ queryKey: ['tasks'] })
    },
    onError: () => setOptimisticStatus(null),
  })

  const availableActions = STATUS_ACTIONS.filter((a) =>
    a.from.includes(currentStatus as TaskStatus),
  )

  return (
    <div
      className={`rounded-lg border p-4 ${
        isDone ? 'border-gray-800 bg-gray-900/40 opacity-60' : 'border-gray-700 bg-gray-900'
      }`}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="text-sm font-semibold text-white leading-tight">{task.title}</h3>
        <div className="flex shrink-0 gap-1.5 flex-wrap justify-end">
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium ${PRIORITY_PILL[task.priority] ?? 'bg-gray-700 text-gray-300'}`}
          >
            {task.priority}
          </span>
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_PILL[currentStatus] ?? 'bg-gray-700 text-gray-300'}`}
          >
            {currentStatus.replace('_', ' ')}
          </span>
        </div>
      </div>

      {/* Description */}
      {task.description && (
        <p className="text-xs text-gray-400 mb-3 leading-relaxed">{task.description}</p>
      )}

      {/* Location + timestamp */}
      <p className="text-xs text-gray-600 mb-3">
        📍 {task.location.coordinates[1].toFixed(5)},{task.location.coordinates[0].toFixed(5)}
        <span className="ml-2">· {formatRelative(task.updated_at)}</span>
      </p>

      {/* Action buttons */}
      {!isDone && availableActions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {availableActions.map((action) => (
            <button
              key={action.to}
              onClick={() => mutation.mutate(action.to)}
              disabled={mutation.isPending}
              className={`text-xs px-3 py-1.5 rounded font-medium text-white ${action.color} disabled:opacity-50 active:scale-95 transition-transform`}
            >
              {mutation.isPending && optimisticStatus === action.to ? '…' : action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
