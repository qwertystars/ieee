interface LegendItem {
  color: string
  label: string
  shape: 'circle' | 'line' | 'square' | 'triangle'
}

const ROAD_ITEMS: LegendItem[] = [
  { color: '#22c55e', label: 'Open', shape: 'line' },
  { color: '#f59e0b', label: 'Partial', shape: 'line' },
  { color: '#ef4444', label: 'Blocked', shape: 'line' },
  { color: '#dc2626', label: 'Dangerous', shape: 'line' },
]

const FRESHNESS_ITEMS: LegendItem[] = [
  { color: '#22c55e', label: '< 5 min (fresh)', shape: 'circle' },
  { color: '#f59e0b', label: '5–60 min (aging)', shape: 'circle' },
  { color: '#ef4444', label: '> 60 min (stale)', shape: 'circle' },
]

const FLOOD_ITEMS: LegendItem[] = [
  { color: '#00ffff', label: 'High probability', shape: 'square' },
  { color: '#00aaff', label: 'Medium', shape: 'square' },
  { color: '#0033ff', label: 'Low', shape: 'square' },
]

function Shape({ item }: { item: LegendItem }) {
  const { color, shape } = item
  if (shape === 'circle') {
    return <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: color }} />
  }
  if (shape === 'line') {
    return <span className="inline-block h-1 w-5 rounded" style={{ backgroundColor: color }} />
  }
  if (shape === 'triangle') {
    return (
      <svg width="12" height="12" viewBox="0 0 12 12">
        <path d="M6 1L11 11H1z" fill={color} />
      </svg>
    )
  }
  return <span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: color }} />
}

function LegendSection({ title, items }: { title: string; items: LegendItem[] }) {
  return (
    <div className="mb-2 last:mb-0">
      <h3 className="mb-1 text-[10px] font-bold uppercase tracking-wider text-gray-400">{title}</h3>
      <div className="flex flex-col gap-0.5">
        {items.map(item => (
          <div key={item.label} className="flex items-center gap-2">
            <Shape item={item} />
            <span className="text-[11px] text-gray-300">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function MapLegend() {
  return (
    <div className="w-44" data-testid="map-legend">
      <h2 className="mb-2 text-xs font-bold text-gray-100">Legend</h2>
      <LegendSection title="Data Freshness" items={FRESHNESS_ITEMS} />
      <LegendSection title="Road Passability" items={ROAD_ITEMS} />
      <LegendSection title="Flood Probability" items={FLOOD_ITEMS} />
      <div className="mt-2 border-t border-gray-700 pt-2">
        <p className="text-[10px] text-gray-500">
          Stale data (&gt;1h) shown in degraded colors. Flood heatmap is semi-transparent for uncertainty.
        </p>
      </div>
    </div>
  )
}
