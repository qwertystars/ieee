// Map layer types for the disaster situational awareness map.
// Typed contracts for all deck.gl layers, freshness, and bbox-driven fetch.

/** Layer identifiers matching the SOTA spec layer toggle list. */
export type LayerId =
  | 'flood'
  | 'roads'
  | 'buildings'
  | 'shelters'
  | 'hospitals'
  | 'responders'
  | 'sensors'
  | 'alerts'
  | 'cellTowers'
  | 'observations'
  | 'hazardZones'

/** Data freshness tiers based on observation age. */
export type DataFreshness = 'fresh' | 'aging' | 'stale'

/** Bounding box for viewport-driven layer fetch. */
export interface Bbox {
  west: number
  south: number
  east: number
  north: number
}

/** Layer configuration with display metadata and color tokens. */
export interface LayerConfig {
  id: LayerId
  label: string
  visible: boolean
  /** Normal (fresh) color — hex string. */
  color: string
  /** Stale (>1h old) color — honest degradation, never normal color. */
  staleColor: string
  /** SVG path data for the layer icon (24x24 viewBox). */
  iconPath: string
}

/** Position as [longitude, latitude] in degrees. */
export type Position = [number, number]

/** Generic GeoJSON-style feature for deck.gl layers. */
export interface MapFeature {
  id: string
  position: Position
  timestamp: number
  confidence: number
  properties: Record<string, unknown>
}

/** Responder location feature (live positions). */
export interface ResponderFeature extends MapFeature {
  name: string
  status: 'available' | 'en_route' | 'on_site' | 'offline'
}

/** Shelter capacity feature. */
export interface ShelterFeature extends MapFeature {
  name: string
  capacity: number
  occupancy: number
  status: 'open' | 'full' | 'closed'
}

/** Hospital status feature. */
export interface HospitalFeature extends MapFeature {
  name: string
  emergencyCapacity: number
  status: 'operational' | 'limited' | 'overwhelmed' | 'closed'
}

/** Cell tower status feature. */
export interface CellTowerFeature extends MapFeature {
  carrier: string
  status: 'active' | 'degraded' | 'offline'
}

/** Observation feature (citizen/sensor reports). */
export interface ObservationFeature extends MapFeature {
  category: string
  description: string
  verified: boolean
}

/** Road segment feature with passability. */
export interface RoadFeature {
  id: string
  path: Position[]
  timestamp: number
  confidence: number
  passability: 'open' | 'blocked' | 'partially_blocked' | 'dangerous' | 'unknown'
}

/** Building footprint feature. */
export interface BuildingFeature {
  id: string
  polygon: Position[]
  timestamp: number
  confidence: number
  buildingType: string
  damaged: boolean
}

/** Flood probability point for heatmap visualization. */
export interface FloodPoint {
  position: Position
  probability: number
  timestamp: number
}

/** Hazard zone polygon. */
export interface HazardZoneFeature {
  id: string
  polygon: Position[]
  zoneType: string
  severity: 'low' | 'medium' | 'high' | 'extreme'
  timestamp: number
}

/** Layer state returned by the useMapLayers hook. */
export interface LayerState {
  config: LayerConfig
  freshness: DataFreshness
  dataAgeMs: number
  featureCount: number
}

/** Freshness thresholds in milliseconds. */
export const FRESHNESS_THRESHOLDS = {
  fresh: 5 * 60 * 1000, // < 5 min
  aging: 60 * 60 * 1000, // 5 min - 1 hour
  // stale: > 1 hour
} as const

/** Compute freshness tier from data age in milliseconds. */
export function computeFreshness(dataAgeMs: number): DataFreshness {
  if (dataAgeMs < FRESHNESS_THRESHOLDS.fresh) return 'fresh'
  if (dataAgeMs < FRESHNESS_THRESHOLDS.aging) return 'aging'
  return 'stale'
}

/** Default layer configurations. Colors are operational dark-theme tokens. */
export const LAYER_CONFIGS: Record<LayerId, Omit<LayerConfig, 'visible'>> = {
  flood: {
    id: 'flood',
    label: 'Flood Probability',
    color: '#3b82f6',
    staleColor: '#1e3a5f',
    iconPath: 'M12 2C8 6 6 9 6 13a6 6 0 0012 0c0-4-2-7-6-11z',
  },
  roads: {
    id: 'roads',
    label: 'Road Network',
    color: '#22c55e',
    staleColor: '#4a5c3a',
    iconPath: 'M4 19h16M4 12h16M4 5h16',
  },
  buildings: {
    id: 'buildings',
    label: 'Building Footprints',
    color: '#a78bfa',
    staleColor: '#4c3a6b',
    iconPath: 'M3 21h18M5 21V7l7-4 7 4v14',
  },
  shelters: {
    id: 'shelters',
    label: 'Shelters',
    color: '#f59e0b',
    staleColor: '#6b4a08',
    iconPath: 'M12 2L2 12h3v8h6v-6h2v6h6v-8h3z',
  },
  hospitals: {
    id: 'hospitals',
    label: 'Hospitals',
    color: '#ef4444',
    staleColor: '#5c1f1f',
    iconPath: 'M12 2v20M2 12h20',
  },
  responders: {
    id: 'responders',
    label: 'Responders (Live)',
    color: '#06b6d4',
    staleColor: '#1a4a52',
    iconPath: 'M12 12a4 4 0 100-8 4 4 0 000 8zM4 20a8 8 0 0116 0',
  },
  sensors: {
    id: 'sensors',
    label: 'Sensors',
    color: '#10b981',
    staleColor: '#1a4a3a',
    iconPath: 'M12 2a10 10 0 100 20 10 10 0 000-20zM12 8v4l3 3',
  },
  alerts: {
    id: 'alerts',
    label: 'Alerts',
    color: '#dc2626',
    staleColor: '#4a1a1a',
    iconPath: 'M12 2L1 21h22L12 2zM12 9v6M12 18v.01',
  },
  cellTowers: {
    id: 'cellTowers',
    label: 'Cell Towers',
    color: '#8b5cf6',
    staleColor: '#3a2a5c',
    iconPath: 'M12 22V8M8 12l4-4 4 4M6 8a8 8 0 0112 0',
  },
  observations: {
    id: 'observations',
    label: 'Observations',
    color: '#ec4899',
    staleColor: '#5c2a3a',
    iconPath: 'M12 6a6 6 0 100 12 6 6 0 000-12zM12 2v2M12 20v2',
  },
  hazardZones: {
    id: 'hazardZones',
    label: 'Hazard Zones',
    color: '#f97316',
    staleColor: '#5c3a1a',
    iconPath: 'M12 2L2 22h20L12 2z',
  },
}
