// Assigned task list with 15s polling — filters to team when teamId provided

import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { tasksApi } from '../../api/client'
import type { TaskRead } from '../../types'
import TaskCard from './TaskCard'

interface Props {
  eventId: string
  teamId: string | null
}

export default function FieldTaskList({ eventId, teamId }: Props) {
  const { data: tasks, isLoading, isError, refetch } = useQuery({
    queryKey: ['tasks', eventId],
    queryFn: () => tasksApi.list(eventId),
    enabled: !!eventId,
    refetchInterval: 15_000,
  })

  const filtered: TaskRead[] = tasks
    ? teamId
      ? tasks.filter((t) => t.assigned_team_id === teamId)
      : tasks
    : []

  const active = filtered.filter((t) => !['completed', 'cancelled'].includes(t.status))
  const done = filtered.filter((t) => ['completed', 'cancelled'].includes(t.status))

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2].map((i) => (
          <div key={i} className="h-28 rounded-lg bg-gray-800 animate-pulse" />
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="text-center py-10">
        <p className="text-sm text-red-400 mb-3">Failed to load tasks</p>
        <button
          onClick={() => refetch()}
          className="text-xs text-blue-400 underline"
        >
          Retry
        </button>
      </div>
    )
  }

  if (filtered.length === 0) {
    return (
      <div className="text-center py-14 text-gray-500">
        <div className="text-3xl mb-2">✓</div>
        <p className="text-sm">No tasks assigned to your team</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {active.map((task) => (
        <TaskCard key={task.id} task={task} />
      ))}

      {done.length > 0 && (
        <details className="mt-2">
          <summary className="text-xs text-gray-500 cursor-pointer select-none py-2">
            {done.length} completed / cancelled
          </summary>
          <div className="space-y-2 mt-2">
            {done.map((task) => (
              <TaskCard key={task.id} task={task} />
            ))}
          </div>
        </details>
      )}
    </div>
  )
}
