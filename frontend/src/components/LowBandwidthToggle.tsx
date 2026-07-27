import { useLowBandwidth } from '../context/LowBandwidthContext'

export function LowBandwidthToggle() {
  const { enabled, toggle } = useLowBandwidth()
  const label = enabled ? 'Low-bandwidth mode on — polling 30s, map imagery stripped'
    : 'Enable low-bandwidth mode'

  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      aria-label={label}
      onClick={toggle}
      className={`flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 ${
        enabled
          ? 'border-amber-500 bg-amber-500/10 text-amber-400'
          : 'border-gray-700 bg-gray-800 text-gray-300 hover:bg-gray-700'
      }`}
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
          d="M5 12a7 7 0 0114 0M2 12a10 10 0 0120 0M12 12h.01"
        />
      </svg>
      <span>{enabled ? 'Low BW' : 'Low BW'}</span>
    </button>
  )
}
