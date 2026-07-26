interface ErrorStateProps {
  message?: string
  detail?: string
  onRetry?: () => void
}

export function ErrorState({
  message = 'Something went wrong',
  detail,
  onRetry,
}: ErrorStateProps) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 p-8 text-center"
      role="alert"
      aria-live="assertive"
      aria-label={`Error: ${message}`}
    >
      <svg
        className="h-10 w-10 text-red-400"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M12 9v2m0 4h.01M5.07 19h13.86c1.54 0 2.5-1.67 1.73-3L13.73 4a2 2 0 00-3.46 0L3.34 16c-.77 1.33.19 3 1.73 3z"
        />
      </svg>
      <div>
        <p className="text-sm font-medium text-red-300">{message}</p>
        {detail && <p className="mt-1 text-xs text-gray-400">{detail}</p>}
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded-md border border-gray-600 bg-gray-800 px-4 py-1.5 text-xs font-medium text-gray-200 transition-colors hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          aria-label="Retry request"
        >
          Retry
        </button>
      )}
    </div>
  )
}
