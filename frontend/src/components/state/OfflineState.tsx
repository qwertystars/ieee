interface OfflineStateProps {
  message?: string
}

export function OfflineState({ message = 'You are offline' }: OfflineStateProps) {
  return (
    <div
      className="inline-flex items-center gap-1.5 rounded-full bg-red-500/10 px-2.5 py-1 text-xs text-red-400"
      role="status"
      aria-live="assertive"
      aria-label={message}
    >
      <svg
        className="h-3.5 w-3.5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M18.364 5.636a9 9 0 010 12.728m-12.728 0a9 9 0 010-12.728m9.9-2.828L5.636 18.364M12 9v4m0 0h.01"
        />
      </svg>
      <span>{message}</span>
    </div>
  )
}
