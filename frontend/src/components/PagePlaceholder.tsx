import type { ReactNode } from 'react'
import { LoadingState } from './state/LoadingState'

interface PagePlaceholderProps {
  title: string
  description: string
  children?: ReactNode
}

export function PagePlaceholder({ title, description, children }: PagePlaceholderProps) {
  return (
    <div className="flex flex-col gap-4 p-6">
      <div>
        <h1 className="text-lg font-bold text-gray-100">{title}</h1>
        <p className="mt-1 text-sm text-gray-500">{description}</p>
      </div>
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-6">
        {children ?? (
          <div className="flex flex-col items-center justify-center gap-3 py-12">
            <LoadingState message="Coming soon" />
            <p className="text-xs text-gray-600">
              This view will be implemented in a follow-up task.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
