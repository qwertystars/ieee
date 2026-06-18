import React from 'react'

export type LayerId =
  | 'flood_observations'
  | 'incident_reports'
  | 'priority_areas'
  | 'shelters'
  | 'roads'
  | 'teams'

export const LAYER_LABELS: Record<LayerId, string> = {
  flood_observations: 'Flood Obs.',
  incident_reports: 'Reports',
  priority_areas: 'Priority Zones',
  shelters: 'Shelters',
  roads: 'Road Status',
  teams: 'Teams',
}

interface Props {
  visible: Record<LayerId, boolean>
  onToggle: (id: LayerId) => void
}

const DOT_COLORS: Record<LayerId, string> = {
  flood_observations: 'bg-blue-400',
  incident_reports: 'bg-red-400',
  priority_areas: 'bg-orange-400',
  shelters: 'bg-green-400',
  roads: 'bg-yellow-400',
  teams: 'bg-purple-400',
}

export default function LayerToggles({ visible, onToggle }: Props) {
  return (
    <div className="flex flex-col gap-1 p-2 bg-gray-900 border border-gray-700 rounded-lg shadow-lg min-w-[140px]">
      <p className="text-xs text-gray-500 font-semibold uppercase tracking-wider px-1 mb-1">Layers</p>
      {(Object.keys(LAYER_LABELS) as LayerId[]).map((id) => (
        <button
          key={id}
          onClick={() => onToggle(id)}
          className={`flex items-center gap-2 px-2 py-1 rounded text-xs transition-colors text-left ${
            visible[id]
              ? 'text-white bg-gray-800'
              : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${visible[id] ? DOT_COLORS[id] : 'bg-gray-600'}`} />
          {LAYER_LABELS[id]}
        </button>
      ))}
    </div>
  )
}
