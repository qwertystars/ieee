import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { EntityFeatureCollection } from '../api/types'
import {
  type LayerId, type LayerConfig, type LayerState,
  type DataFreshness, type Bbox, type Position,
  type ResponderFeature, type ShelterFeature, type HospitalFeature,
  type CellTowerFeature, type ObservationFeature,
  type RoadFeature, type BuildingFeature,
  type FloodPoint, type HazardZoneFeature,
  LAYER_CONFIGS, computeFreshness,
} from '../types/map'
import {
  toRoads, toShelters, toHospitals, toResponders,
  toCellTowers, toBuildings, toHazardZones,
  toObservations, toFloodPoints, toRescueBalls, toZonePolygons,
} from '../lib/mapTransform'

/** All layer data bundled for the map renderer. */
export interface LayerData {
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

/** Demo data center (Mumbai — matches seed data coordinates). */
export const MAP_CENTER: Position = [72.877, 19.076]

const EMPTY_DATA: LayerData = {
  flood: [], roads: [], buildings: [], shelters: [], hospitals: [],
  responders: [], sensors: [], alerts: [], cellTowers: [],
  observations: [], hazardZones: [],
}

const ENTITY_TYPES = [
  'zones', 'roads', 'shelters', 'hospitals', 'hazards',
  'buildings', 'cell_towers', 'responders', 'sensors',
] as const

type EntityType = typeof ENTITY_TYPES[number]

/** Hook managing all map layer state: visibility, data, freshness, bbox fetch. */
export function useMapLayers() {
  const [visibleLayers, setVisibleLayers] = useState<Set<LayerId>>(
    new Set(['flood', 'roads', 'responders', 'shelters', 'hospitals', 'hazardZones', 'observations'])
  )
  const [bbox, setBbox] = useState<Bbox | null>(null)
  const [now, setNow] = useState(() => Date.now())

  // Refresh "now" every 30s so freshness badges update in real time.
  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(interval)
  }, [])

  // Fetch incidents first to get the incident ID.
  const incidentsQuery = useQuery({
    queryKey: ['incidents'],
    queryFn: ({ signal }) => api.getIncidents(signal),
  })
  const incidentId = incidentsQuery.data?.incidents?.[0]?.id ?? null

  // Fetch all entity types in parallel (dependent on incidentId).
  const entityQueries = useQuery({
    queryKey: ['entities-all', incidentId],
    queryFn: async ({ signal }) => {
      const results = await Promise.all(
        ENTITY_TYPES.map(t => api.getEntities(incidentId!, t, signal))
      )
      const map: Record<EntityType, EntityFeatureCollection> = {} as never
      ENTITY_TYPES.forEach((t, i) => { map[t] = results[i] })
      return map
    },
    enabled: !!incidentId,
  })

  // Fetch observations.
  const observationsQuery = useQuery({
    queryKey: ['observations', incidentId],
    queryFn: ({ signal }) => api.getObservations(incidentId!, signal),
    enabled: !!incidentId,
  })

  const isLoading = incidentsQuery.isLoading || entityQueries.isLoading || observationsQuery.isLoading
  const isError = incidentsQuery.isError || entityQueries.isError || observationsQuery.isError
  const isStale = incidentsQuery.isStale || entityQueries.isStale || observationsQuery.isStale

  // Transform API data into LayerData.
  const data: LayerData = useMemo(() => {
    if (!entityQueries.data || !observationsQuery.data) return EMPTY_DATA
    const eq = entityQueries.data
    const obs = observationsQuery.data.features as unknown as import('../api/types').GeoJSONFeature[]
    const obsFeatures = obs as Parameters<typeof toObservations>[0]
    const sensors = (eq.sensors.features as unknown as Parameters<typeof toRescueBalls>[0])
    return {
      flood: toFloodPoints(obsFeatures),
      roads: toRoads(eq.roads.features as unknown as Parameters<typeof toRoads>[0]),
      buildings: toBuildings(eq.buildings.features as unknown as Parameters<typeof toBuildings>[0]),
      shelters: toShelters(eq.shelters.features as unknown as Parameters<typeof toShelters>[0]),
      hospitals: toHospitals(eq.hospitals.features as unknown as Parameters<typeof toHospitals>[0]),
      responders: toResponders(eq.responders.features as unknown as Parameters<typeof toResponders>[0]),
      sensors: toRescueBalls(sensors),
      alerts: [], // alerts API has no geometry — shown in dashboard panel
      cellTowers: toCellTowers(eq.cell_towers.features as unknown as Parameters<typeof toCellTowers>[0]),
      observations: toObservations(obsFeatures),
      hazardZones: toHazardZones(eq.hazards.features as unknown as Parameters<typeof toHazardZones>[0]),
    }
  }, [entityQueries.data, observationsQuery.data])

  // Incident boundary from zone polygons.
  const incidentBoundary: Position[][] = useMemo(() => {
    if (!entityQueries.data) return []
    return toZonePolygons(
      entityQueries.data.zones.features as unknown as Parameters<typeof toZonePolygons>[0]
    )
  }, [entityQueries.data])

  // Rescue-ball sensors for path rendering.
  const rescueBalls: ObservationFeature[] = data.sensors

  const fetchByBbox = useCallback((newBbox: Bbox) => {
    setBbox(newBbox)
  }, [])

  const toggleLayer = useCallback((id: LayerId) => {
    setVisibleLayers(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const setLayerVisible = useCallback((id: LayerId, visible: boolean) => {
    setVisibleLayers(prev => {
      const next = new Set(prev)
      if (visible) next.add(id)
      else next.delete(id)
      return next
    })
  }, [])

  // Compute per-layer state: config + freshness + age + feature count.
  const layerStates = useMemo(() => {
    const states: Partial<Record<LayerId, LayerState>> = {}
    for (const id of Object.keys(LAYER_CONFIGS) as LayerId[]) {
      const cfg = LAYER_CONFIGS[id]
      const layerData = data[id]
      const timestamps: number[] = []
      if (Array.isArray(layerData)) {
        for (const f of layerData) {
          const ts = (f as { timestamp?: number }).timestamp
          if (typeof ts === 'number') timestamps.push(ts)
        }
      }
      const newest = timestamps.length > 0 ? Math.max(...timestamps) : 0
      const dataAgeMs = newest > 0 ? Math.max(0, now - newest) : Infinity
      const freshness: DataFreshness = dataAgeMs === Infinity ? 'stale' : computeFreshness(dataAgeMs)
      const config: LayerConfig = { ...cfg, visible: visibleLayers.has(id) }
      states[id] = {
        config, freshness, dataAgeMs,
        featureCount: Array.isArray(layerData) ? layerData.length : 0,
      }
    }
    return states
  }, [data, now, visibleLayers])

  const allConfigs = useMemo(
    () => (Object.keys(LAYER_CONFIGS) as LayerId[]).map(id => layerStates[id]!.config),
    [layerStates]
  )

  return {
    data, bbox, visibleLayers, layerStates, allConfigs,
    toggleLayer, setLayerVisible, fetchByBbox,
    incidentId, incidentBoundary, rescueBalls,
    isLoading, isError, isStale,
    refetch: () => {
      incidentsQuery.refetch()
      entityQueries.refetch()
      observationsQuery.refetch()
    },
  }
}
