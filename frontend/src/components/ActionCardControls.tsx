interface ActionCardControlsProps {
  readonly actionLabel: string
  readonly isResolved: boolean
  readonly dispatchPending: boolean
  readonly onApprove: () => void
  readonly onDismiss: () => void
  readonly onModify: () => void
  readonly onDispatchRequest: () => void
}

export function ActionCardControls({
  actionLabel,
  isResolved,
  dispatchPending,
  onApprove,
  onDismiss,
  onModify,
  onDispatchRequest,
}: ActionCardControlsProps) {
  return (
    <>
      <div className="mt-3 flex gap-2 border-t border-gray-700 pt-3">
        <button data-testid="approve-button" onClick={onApprove} disabled={isResolved} className="flex-1 rounded bg-green-700 px-2 py-1 text-xs font-medium text-white hover:bg-green-600 disabled:opacity-40" aria-label={`Approve action: ${actionLabel}`}>
          Approve
        </button>
        <button data-testid="dismiss-button" onClick={onDismiss} disabled={isResolved} className="flex-1 rounded bg-red-700 px-2 py-1 text-xs font-medium text-white hover:bg-red-600 disabled:opacity-40" aria-label={`Dismiss action: ${actionLabel}`}>
          Dismiss
        </button>
        <button data-testid="modify-button" onClick={onModify} disabled={isResolved} className="flex-1 rounded bg-gray-700 px-2 py-1 text-xs font-medium text-gray-200 hover:bg-gray-600 disabled:opacity-40" aria-label={`Modify action: ${actionLabel}`}>
          Modify
        </button>
        <button data-testid="dispatch-button" onClick={onDispatchRequest} disabled={isResolved || dispatchPending} className="flex-1 rounded border border-amber-700 bg-amber-950/70 px-2 py-1 text-xs font-medium text-amber-200 hover:bg-amber-900 disabled:opacity-40" aria-label={`Request dispatch: ${actionLabel}`}>
          Request Dispatch
        </button>
      </div>
      {dispatchPending && (
        <div data-testid="dispatch-pending" className="mt-2 rounded border border-amber-800/70 bg-amber-950/40 px-2 py-2 text-[11px] text-amber-200">
          Awaiting dual approval. No task created.
        </div>
      )}
    </>
  )
}
