interface EmptyStateProps {
  message?: string
  hint?: string
}

export function EmptyState({ message = 'No data available', hint }: EmptyStateProps) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-2 p-8 text-center"
      role="status"
      aria-live="polite"
      aria-label={message}
    >
      <svg
        className="h-10 w-10 text-gray-600"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
        />
      </svg>
      <p className="text-sm font-medium text-gray-300">{message}</p>
      {hint && <p className="text-xs text-gray-500">{hint}</p>}
    </div>
  )
}
