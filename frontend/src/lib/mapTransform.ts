// GeoJSON API response -> LayerData transformations for deck.gl rendering.
// Converts backend GeoJSON FeatureCollections into typed layer arrays.

import type { GeoJSONFeature, GeoJSONGeometry } from '../api/types'
import type {
  Position, RoadFeature, ShelterFeature, HospitalFeature,
  ResponderFeature, CellTowerFeature, ObservationFeature,
  BuildingFeature, HazardZoneFeature, FloodPoint,
} from '../types/map'

type Feature = GeoJSONFeature<Record<string, unknown>>

/** Extract a Point position from a GeoJSON geometry. */
function pointPos(geom: GeoJSONGeometry | null): Position | null {
  if (!geom) return null
  if (geom.type === 'Point') return geom.coordinates as Position
  if (geom.type === 'MultiPoint') return (geom.coordinates as Position[])[0] ?? null
  return null
}

/** Extract a LineString path from a GeoJSON geometry. */
function linePath(geom: GeoJSONGeometry | null): Position[] {
  if (!geom) return []
  if (geom.type === 'LineString') return geom.coordinates as Position[]
  if (geom.type === 'MultiLineString') return (geom.coordinates as Position[][])[0] ?? []
  return []
}

/** Extract a Polygon ring from a GeoJSON geometry. */
function polygonRing(geom: GeoJSONGeometry | null): Position[] {
  if (!geom) return []
  if (geom.type === 'Polygon') return (geom.coordinates as Position[][])[0] ?? []
  if (geom.type === 'MultiPolygon') {
    const rings = geom.coordinates as Position[][][]
    return rings[0]?.[0] ?? []
  }
  return []
}

function num(v: unknown, def = 0): number {
  return typeof v === 'number' && !isNaN(v) ? v : def
}

function str(v: unknown, def = ''): string {
  return typeof v === 'string' ? v : def
}

/** Transform road entity features into RoadFeature[]. */
export function toRoads(features: Feature[]): RoadFeature[] {
  return features.flatMap(f => {
    const path = linePath(f.geometry)
    if (path.length < 2) return []
    const p = f.properties
    return [{
      id: str(p.id),
      path,
      timestamp: num(p.updated_at),
      confidence: 0.9,
      passability: (str(p.status, 'unknown') as RoadFeature['passability']),
    }]
  })
}

/** Transform shelter entity features into ShelterFeature[]. */
export function toShelters(features: Feature[]): ShelterFeature[] {
  return features.flatMap(f => {
    const pos = pointPos(f.geometry)
    if (!pos) return []
    const p = f.properties
    return [{
      id: str(p.id), position: pos, timestamp: num(p.updated_at),
      confidence: 0.9, properties: p,
      name: str(p.name, 'Shelter'),
      capacity: num(p.capacity, 0),
      occupancy: num(p.occupancy, 0),
      status: (str(p.status, 'open') as ShelterFeature['status']),
    }]
  })
}

/** Transform hospital entity features into HospitalFeature[]. */
export function toHospitals(features: Feature[]): HospitalFeature[] {
  return features.flatMap(f => {
    const pos = pointPos(f.geometry)
    if (!pos) return []
    const p = f.properties
    return [{
      id: str(p.id), position: pos, timestamp: num(p.updated_at),
      confidence: 0.9, properties: p,
      name: str(p.name, 'Hospital'),
      emergencyCapacity: num(p.capacity, 0),
      status: (str(p.status, 'operational') as HospitalFeature['status']),
    }]
  })
}

/** Transform responder entity features into ResponderFeature[]. */
export function toResponders(features: Feature[]): ResponderFeature[] {
  return features.flatMap(f => {
    const pos = pointPos(f.geometry)
    if (!pos) return []
    const p = f.properties
    return [{
      id: str(p.id), position: pos, timestamp: num(p.updated_at),
      confidence: 0.85, properties: p,
      name: str(p.name, 'Responder'),
      status: (str(p.status, 'offline') as ResponderFeature['status']),
    }]
  })
}

/** Transform cell tower entity features into CellTowerFeature[]. */
export function toCellTowers(features: Feature[]): CellTowerFeature[] {
  return features.flatMap(f => {
    const pos = pointPos(f.geometry)
    if (!pos) return []
    const p = f.properties
    return [{
      id: str(p.id), position: pos, timestamp: num(p.updated_at),
      confidence: 0.9, properties: p,
      carrier: str(p.name, 'Unknown'),
      status: (str(p.status, 'offline') as CellTowerFeature['status']),
    }]
  })
}

/** Transform building entity features into BuildingFeature[]. */
export function toBuildings(features: Feature[]): BuildingFeature[] {
  return features.flatMap(f => {
    const polygon = polygonRing(f.geometry)
    if (polygon.length < 3) return []
    const p = f.properties
    return [{
      id: str(p.id), polygon, timestamp: num(p.updated_at),
      confidence: 0.85, buildingType: str(p.building_type, 'unknown'),
      damaged: str(p.status) === 'damaged',
    }]
  })
}

/** Transform hazard entity features into HazardZoneFeature[]. */
export function toHazardZones(features: Feature[]): HazardZoneFeature[] {
  return features.flatMap(f => {
    const polygon = polygonRing(f.geometry)
    if (polygon.length < 3) return []
    const p = f.properties
    return [{
      id: str(p.id), polygon,
      zoneType: str(p.hazard_type, 'unknown'),
      severity: (str(p.severity, 'medium') as HazardZoneFeature['severity']),
      timestamp: num(p.updated_at),
    }]
  })
}

/** Transform observation GeoJSON features into ObservationFeature[]. */
export function toObservations(features: Feature[]): ObservationFeature[] {
  return features.flatMap(f => {
    const pos = pointPos(f.geometry)
    if (!pos) return []
    const p = f.properties
    const corroborated = str(p.corroboration_state) === 'corroborated'
    return [{
      id: str(p.observation_id), position: pos,
      timestamp: num(p.observed_at),
      confidence: num(p.source_reliability, 0.5),
      properties: p,
      category: str(p.phenomenon, 'unknown'),
      description: str(p.event_type, 'observation'),
      verified: corroborated,
    }]
  })
}

/** Extract flood points from observation features (water_level / flood phenomena). */
export function toFloodPoints(features: Feature[]): FloodPoint[] {
  const floodPhenomena = new Set([
    'water_level', 'flood_extent', 'flood', 'rainfall_rate',
    'rainfall_accumulation', 'storm_surge',
  ])
  return features.flatMap(f => {
    const pos = pointPos(f.geometry)
    if (!pos) return []
    const p = f.properties
    if (!floodPhenomena.has(str(p.phenomenon))) return []
    const val = num(p.value, 0.5)
    return [{
      position: pos,
      probability: Math.min(1, Math.max(0, val > 1 ? val / 100 : val)),
      timestamp: num(p.observed_at),
    }]
  })
}

/** Extract rescue-ball sensors (sensor_type=rescue_ball) as observation features. */
export function toRescueBalls(features: Feature[]): ObservationFeature[] {
  return features.flatMap(f => {
    const pos = pointPos(f.geometry)
    if (!pos) return []
    const p = f.properties
    if (str(p.sensor_type) !== 'rescue_ball') return []
    return [{
      id: str(p.id), position: pos, timestamp: num(p.updated_at),
      confidence: 0.95, properties: p,
      category: 'rescue_ball', description: str(p.name, 'Rescue Ball'),
      verified: true,
    }]
  })
}

/** Extract zone polygons for incident boundary rendering. */
export function toZonePolygons(features: Feature[]): Position[][] {
  return features.flatMap(f => {
    const ring = polygonRing(f.geometry)
    return ring.length >= 3 ? [ring] : []
  })
}
