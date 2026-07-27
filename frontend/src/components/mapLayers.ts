// deck.gl layer factory: creates layers from map data with stale-data coloring.
// Stale data (>1h old) uses degraded colors — never normal colors.

import { HeatmapLayer } from '@deck.gl/aggregation-layers'
import { PolygonLayer, LineLayer, IconLayer, ScatterplotLayer } from '@deck.gl/layers'
import type { Layer } from '@deck.gl/core'
import type {
  LayerConfig, FloodPoint, RoadFeature, BuildingFeature,
  ShelterFeature, HospitalFeature, ResponderFeature, CellTowerFeature,
  ObservationFeature, HazardZoneFeature,
} from '../types/map'

const STALE_MS = 60 * 60 * 1000 // 1 hour

function isStale(timestamp: number, now: number): boolean {
  return now - timestamp > STALE_MS
}

function freshnessRgba(
  timestamp: number, now: number, freshColor: string, staleColor: string, alpha: number
): [number, number, number, number] {
  return hexToRgba(isStale(timestamp, now) ? staleColor : freshColor, alpha)
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
}

function hexToRgba(hex: string, alpha: number): [number, number, number, number] {
  const [r, g, b] = hexToRgb(hex)
  return [r, g, b, alpha]
}

/** Generate an SVG circle icon as a data URI for IconLayer. */
function iconUri(color: string, letter: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">` +
    `<circle cx="16" cy="16" r="13" fill="${color}" stroke="white" stroke-width="2" opacity="0.9"/>` +
    `<text x="16" y="21" text-anchor="middle" fill="white" font-size="14" font-weight="bold" ` +
    `font-family="sans-serif">${letter}</text></svg>`
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}

const ROAD_COLORS: Record<string, string> = {
  open: '#22c55e',
  blocked: '#ef4444',
  partially_blocked: '#f59e0b',
  dangerous: '#dc2626',
  unknown: '#6b7280',
}

const HAZARD_COLORS: Record<string, string> = {
  low: '#fbbf24', medium: '#f97316', high: '#ef4444', extreme: '#7c2d12',
}

export interface LayerFactoryArgs {
  data: {
    flood: FloodPoint[]
    roads: RoadFeature[]
    buildings: BuildingFeature[]
    shelters: ShelterFeature[]
    hospitals: HospitalFeature[]
    responders: ResponderFeature[]
    sensors: ObservationFeature[]
    alerts: ObservationFeature[]
    cellTowers: CellTowerFeature[]
    observations: ObservationFeature[]
    hazardZones: HazardZoneFeature[]
  }
  configs: Record<string, LayerConfig>
  visible: Set<string>
  now: number
  drawnZones: { polygon: [number, number][] }[]
}

/** Build all visible deck.gl layers. Stale data uses degraded colors. */
export function buildLayers(args: LayerFactoryArgs): Layer[] {
  const { data, configs, visible, now, drawnZones } = args
  const layers: Layer[] = []

  if (visible.has('flood')) {
    layers.push(new HeatmapLayer({
      id: 'flood-layer',
      data: data.flood,
      getPosition: (d: FloodPoint) => d.position,
      getWeight: (d: FloodPoint) => d.probability,
      intensity: 1,
      radiusPixels: 60,
      opacity: 0.5, // semi-transparent for uncertainty visualization
      threshold: 0.03,
      colorRange: [
        [0, 0, 255, 0], [0, 60, 255, 40], [0, 120, 255, 80],
        [0, 180, 255, 120], [0, 220, 255, 160], [0, 255, 255, 200],
      ],
      pickable: true,
    }))
  }

  if (visible.has('roads')) {
    layers.push(new LineLayer({
      id: 'roads-layer',
      data: data.roads,
      getSourcePosition: (d: RoadFeature) => d.path[0],
      getTargetPosition: (d: RoadFeature) => d.path[1],
      getColor: (d: RoadFeature) => {
        const base = ROAD_COLORS[d.passability] || configs.roads.color
        return isStale(d.timestamp, now)
          ? hexToRgb(configs.roads.staleColor) : hexToRgb(base)
      },
      getWidth: 3,
      widthUnits: 'pixels',
      pickable: true,
    }))
  }

  if (visible.has('buildings')) {
    const cfg = configs.buildings
    layers.push(new PolygonLayer({
      id: 'buildings-layer',
      data: data.buildings,
      getPolygon: (d: BuildingFeature) => d.polygon,
      getFillColor: (d: BuildingFeature) =>
        d.damaged ? [239, 68, 68, 180] : freshnessRgba(d.timestamp, now, cfg.color, cfg.staleColor, 120),
      getLineColor: [255, 255, 255, 60],
      stroked: true,
      filled: true,
      pickable: true,
    }))
  }

  // Point layers using IconLayer with SVG data URIs
  const pointLayerDefs: [string, string, string, { id: string; position: [number, number]; timestamp: number }[]][] = [
    ['shelters', 'S', 'shelters', data.shelters],
    ['hospitals', 'H', 'hospitals', data.hospitals],
    ['responders', 'R', 'responders', data.responders],
    ['cellTowers', 'C', 'cellTowers', data.cellTowers],
  ]
  for (const [id, letter, cfgKey, features] of pointLayerDefs) {
    if (!visible.has(id)) continue
    const cfg = configs[cfgKey]
    layers.push(new IconLayer({
      id: `${id}-layer`,
      data: features,
      getIcon: (d: { timestamp: number }) => ({
        url: iconUri(isStale(d.timestamp, now) ? cfg.staleColor : cfg.color, letter),
        width: 32, height: 32, anchorY: 16,
      }),
      getPosition: (d: { position: [number, number] }) => d.position,
      getSize: 1,
      sizeUnits: 'pixels',
      sizeScale: 1,
      pickable: true,
    }))
  }

  if (visible.has('observations')) {
    const cfg = configs.observations
    layers.push(new ScatterplotLayer({
      id: 'observations-layer',
      data: data.observations,
      getPosition: (d: ObservationFeature) => d.position,
      getFillColor: (d: ObservationFeature) =>
        freshnessRgba(d.timestamp, now, cfg.color, cfg.staleColor, d.verified ? 200 : 120),
      getRadius: 8,
      radiusUnits: 'pixels',
      stroked: true,
      getLineColor: [255, 255, 255, 200],
      getLineWidth: 1,
      lineWidthUnits: 'pixels',
      pickable: true,
    }))
  }

  if (visible.has('sensors')) {
    const cfg = configs.sensors
    layers.push(new ScatterplotLayer({
      id: 'sensors-layer',
      data: data.sensors,
      getPosition: (d: ObservationFeature) => d.position,
      getFillColor: (d: ObservationFeature) =>
        freshnessRgba(d.timestamp, now, cfg.color, cfg.staleColor, 180),
      getRadius: 6,
      radiusUnits: 'pixels',
      pickable: true,
    }))
  }

  if (visible.has('alerts')) {
    const cfg = configs.alerts
    layers.push(new ScatterplotLayer({
      id: 'alerts-layer',
      data: data.alerts,
      getPosition: (d: ObservationFeature) => d.position,
      getFillColor: (d: ObservationFeature) =>
        freshnessRgba(d.timestamp, now, cfg.color, cfg.staleColor, 220),
      getRadius: 12,
      radiusUnits: 'pixels',
      stroked: true,
      getLineColor: [255, 255, 0, 255],
      getLineWidth: 2,
      lineWidthUnits: 'pixels',
      pickable: true,
    }))
  }

  if (visible.has('hazardZones')) {
    layers.push(new PolygonLayer({
      id: 'hazard-zones-layer',
      data: data.hazardZones,
      getPolygon: (d: HazardZoneFeature) => d.polygon,
      getFillColor: (d: HazardZoneFeature) =>
        hexToRgba(HAZARD_COLORS[d.severity] || '#f97316', 60),
      getLineColor: (d: HazardZoneFeature) =>
        hexToRgb(HAZARD_COLORS[d.severity] || '#f97316'),
      stroked: true,
      filled: true,
      pickable: true,
    }))
  }

  // Drawn zones (terra-draw equivalent — native polygon drawing)
  if (drawnZones.length > 0) {
    layers.push(new PolygonLayer({
      id: 'drawn-zones-layer',
      data: drawnZones,
      getPolygon: (d: { polygon: [number, number][] }) => d.polygon,
      getFillColor: [59, 130, 246, 40],
      getLineColor: [59, 130, 246, 200],
      getLineWidth: 2,
      lineWidthUnits: 'pixels',
      stroked: true,
      filled: true,
      pickable: false,
    }))
  }

  return layers
}
