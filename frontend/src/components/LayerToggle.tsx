import type { LayerId, LayerState, DataFreshness } from '../types/map'

interface LayerToggleProps {
  layerStates: Partial<Record<LayerId, LayerState>>
  onToggle: (id: LayerId) => void
}

const FRESHNESS_STYLES: Record<DataFreshness, { dot: string; text: string; label: string }> = {
  fresh: { dot: 'bg-green-500', text: 'text-green-400', label: 'Fresh' },
  aging: { dot: 'bg-amber-500', text: 'text-amber-400', label: 'Aging' },
  stale: { dot: 'bg-red-500', text: 'text-red-400', label: 'Stale' },
}

function formatAge(ms: number): string {
  if (ms === Infinity) return 'no data'
  if (ms < 60_000) return `${Math.round(ms / 1000)}s ago`
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m ago`
  return `${Math.round(ms / 3_600_000)}h ago`
}

function FreshnessBadge({ freshness, ageMs }: { freshness: DataFreshness; ageMs: number }) {
  const style = FRESHNESS_STYLES[freshness]
  return (
    <div className="flex items-center gap-1" title={`Data age: ${formatAge(ageMs)}`}>
      <span className={`inline-block h-2 w-2 rounded-full ${style.dot}`} />
      <span className={`text-[10px] ${style.text}`}>{formatAge(ageMs)}</span>
    </div>
  )
}

function LayerRow({
  state,
  onToggle,
}: {
  state: LayerState
  onToggle: (id: LayerId) => void
}) {
  const { config, freshness, dataAgeMs, featureCount } = state
  const isStale = freshness === 'stale'
  const color = isStale ? config.staleColor : config.color

  return (
    <div
      className="flex items-center gap-2 rounded px-2 py-1.5 transition-colors hover:bg-gray-800"
      data-testid={`layer-toggle-${config.id}`}
      data-layer-id={config.id}
      data-visible={config.visible ? 'true' : 'false'}
      data-freshness={freshness}
      data-feature-count={featureCount}
    >
      <button
        onClick={() => onToggle(config.id)}
        className="flex-shrink-0"
        role="checkbox"
        aria-checked={config.visible}
        aria-label={`Toggle ${config.label}`}
      >
        <svg width="18" height="18" viewBox="0 0 18 18" className="block">
          <rect
            x="1" y="1" width="16" height="16" rx="3"
            fill={config.visible ? color : 'transparent'}
            stroke={color}
            strokeWidth="2"
          />
          {config.visible && (
            <path
              d="M4 9l3 3 7-7"
              fill="none"
              stroke="white"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}
        </svg>
      </button>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-1.5">
          <svg width="14" height="14" viewBox="0 0 24 24" className="flex-shrink-0">
            <path d={config.iconPath} fill={color} stroke="none" />
          </svg>
          <span className={`truncate text-xs font-medium ${isStale ? 'text-gray-500' : 'text-gray-200'}`}>
            {config.label}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <FreshnessBadge freshness={freshness} ageMs={dataAgeMs} />
          <span className="text-[10px] text-gray-500">{featureCount} features</span>
        </div>
      </div>
    </div>
  )
}

export function LayerToggle({ layerStates, onToggle }: LayerToggleProps) {
  const entries = Object.values(layerStates) as LayerState[]
  const sorted = entries.sort((a, b) => a.config.label.localeCompare(b.config.label))

  return (
    <div className="flex flex-col gap-0.5" data-testid="layer-toggle-list">
      {sorted.map(state => (
        <LayerRow key={state.config.id} state={state} onToggle={onToggle} />
      ))}
    </div>
  )
}
