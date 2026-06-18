import React, { useEffect, useRef, useCallback } from 'react'
import maplibregl from 'maplibre-gl'
import type { MapLayersResponse } from '../../types'
import type { LayerId } from './LayerToggles'
import { boundsToParam } from '../../lib/geo'

// Priority level → fill colour
const PRIORITY_FILL: Record<string, string> = {
  critical: '#dc2626',
  high: '#ea580c',
  medium: '#d97706',
  low: '#65a30d',
  monitoring: '#0284c7',
  unknown: '#6b7280',
}

// Road status → line colour
const ROAD_COLOR: Record<string, string> = {
  open: '#22c55e',
  blocked: '#dc2626',
  partially_blocked: '#f97316',
  dangerous: '#eab308',
  unknown: '#6b7280',
}

// Urgency → circle colour
const URGENCY_COLOR: Record<string, string> = {
  critical: '#dc2626',
  high: '#ea580c',
  medium: '#d97706',
  low: '#65a30d',
}

interface Props {
  layers: MapLayersResponse | undefined
  visibleLayers: Record<LayerId, boolean>
  onBoundsChange: (bbox: string) => void
}

export default function MapView({ layers, visibleLayers, onBoundsChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)

  // Emit bounds on map move (debounced)
  const emitBounds = useCallback(
    (map: maplibregl.Map) => {
      const bbox = boundsToParam(map.getBounds())
      onBoundsChange(bbox)
    },
    [onBoundsChange],
  )

  // Init map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = new maplibregl.Map({
      container: containerRef.current,
      // OpenStreetMap raster tiles — no API key required
      style: {
        version: 8,
        sources: {
          osm: {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '© OpenStreetMap contributors',
          },
        },
        layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
      },
      center: [-80.0, 26.0], // Rivertown demo region placeholder
      zoom: 12,
    })

    map.addControl(new maplibregl.NavigationControl(), 'top-right')
    map.addControl(new maplibregl.ScaleControl(), 'bottom-right')

    map.on('load', () => {
      emitBounds(map)
      addLayerSources(map)
    })

    map.on('moveend', () => emitBounds(map))

    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Add empty GeoJSON sources for all data layers
  function addLayerSources(map: maplibregl.Map) {
    const empty: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

    // Priority areas — fill + outline
    map.addSource('priority_areas', { type: 'geojson', data: empty })
    map.addLayer({
      id: 'priority_areas-fill',
      type: 'fill',
      source: 'priority_areas',
      paint: { 'fill-color': ['get', 'fill'], 'fill-opacity': 0.3 },
    })
    map.addLayer({
      id: 'priority_areas-outline',
      type: 'line',
      source: 'priority_areas',
      paint: { 'line-color': ['get', 'fill'], 'line-width': 2 },
    })

    // Flood observations — polygon fill
    map.addSource('flood_observations', { type: 'geojson', data: empty })
    map.addLayer({
      id: 'flood_observations-fill',
      type: 'fill',
      source: 'flood_observations',
      paint: { 'fill-color': '#3b82f6', 'fill-opacity': 0.35 },
    })

    // Roads — line
    map.addSource('roads', { type: 'geojson', data: empty })
    map.addLayer({
      id: 'roads-line',
      type: 'line',
      source: 'roads',
      paint: {
        'line-color': ['get', 'color'],
        'line-width': 4,
      },
    })

    // Incident reports — circle
    map.addSource('incident_reports', { type: 'geojson', data: empty })
    map.addLayer({
      id: 'incident_reports-circle',
      type: 'circle',
      source: 'incident_reports',
      paint: {
        'circle-color': ['get', 'color'],
        'circle-radius': 7,
        'circle-stroke-color': '#fff',
        'circle-stroke-width': 1.5,
      },
    })

    // Shelters — circle
    map.addSource('shelters', { type: 'geojson', data: empty })
    map.addLayer({
      id: 'shelters-circle',
      type: 'circle',
      source: 'shelters',
      paint: {
        'circle-color': '#22c55e',
        'circle-radius': 9,
        'circle-stroke-color': '#fff',
        'circle-stroke-width': 2,
      },
    })

    // Teams — circle
    map.addSource('teams', { type: 'geojson', data: empty })
    map.addLayer({
      id: 'teams-circle',
      type: 'circle',
      source: 'teams',
      paint: {
        'circle-color': '#a855f7',
        'circle-radius': 8,
        'circle-stroke-color': '#fff',
        'circle-stroke-width': 2,
      },
    })

    // Popups for reports
    addPopupOnClick(map, 'incident_reports-circle', (f) => {
      const p = f.properties ?? {}
      return `<div class="text-xs"><strong>${p['category'] ?? 'Report'}</strong><br/>${p['urgency'] ?? ''} · ${p['description'] ?? ''}</div>`
    })
    addPopupOnClick(map, 'shelters-circle', (f) => {
      const p = f.properties ?? {}
      return `<div class="text-xs"><strong>${p['name'] ?? 'Shelter'}</strong><br/>${p['occupancy'] ?? ''} · ${p['status'] ?? ''}</div>`
    })
    addPopupOnClick(map, 'teams-circle', (f) => {
      const p = f.properties ?? {}
      return `<div class="text-xs"><strong>${p['name'] ?? 'Team'}</strong><br/>${p['status'] ?? ''}</div>`
    })
  }

  function addPopupOnClick(
    map: maplibregl.Map,
    layerId: string,
    html: (f: maplibregl.MapGeoJSONFeature) => string,
  ) {
    map.on('click', layerId, (e) => {
      const f = e.features?.[0]
      if (!f) return
      new maplibregl.Popup({ closeButton: false, maxWidth: '220px' })
        .setLngLat(e.lngLat)
        .setHTML(html(f))
        .addTo(map)
    })
    map.on('mouseenter', layerId, () => {
      map.getCanvas().style.cursor = 'pointer'
    })
    map.on('mouseleave', layerId, () => {
      map.getCanvas().style.cursor = ''
    })
  }

  // Update data when layers prop changes
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded() || !layers) return

    // Priority areas
    const areaFeatures: GeoJSON.Feature[] = (layers.areas ?? []).map((a) => ({
      type: 'Feature',
      geometry: a.geometry as unknown as GeoJSON.Geometry,
      properties: {
        id: a.id,
        name: a.area_name,
        priority: a.priority_level,
        score: a.overall_priority_score,
        fill: PRIORITY_FILL[a.priority_level] ?? '#6b7280',
        updated_at: a.updated_at,
      },
    }));
    (map.getSource('priority_areas') as maplibregl.GeoJSONSource)?.setData({
      type: 'FeatureCollection',
      features: areaFeatures,
    })

    // Flood observations (polygon/geometry types only)
    const obsFeatures: GeoJSON.Feature[] = (layers.observations ?? [])
      .filter((o) => o.geometry.type !== 'Point')
      .map((o) => ({
        type: 'Feature',
        geometry: o.geometry as unknown as GeoJSON.Geometry,
        properties: { id: o.id, type: o.observation_type, confidence: o.confidence_score },
      }));
    (map.getSource('flood_observations') as maplibregl.GeoJSONSource)?.setData({
      type: 'FeatureCollection',
      features: obsFeatures,
    })

    // Roads
    const roadFeatures: GeoJSON.Feature[] = (layers.roads ?? []).map((r) => ({
      type: 'Feature',
      geometry: r.geometry as unknown as GeoJSON.Geometry,
      properties: {
        id: r.id,
        name: r.road_name,
        status: r.status,
        color: ROAD_COLOR[r.status] ?? '#6b7280',
      },
    }));
    (map.getSource('roads') as maplibregl.GeoJSONSource)?.setData({
      type: 'FeatureCollection',
      features: roadFeatures,
    })

    // Incident reports
    const reportFeatures: GeoJSON.Feature[] = (layers.reports ?? []).map((r) => ({
      type: 'Feature',
      geometry: r.geometry as unknown as GeoJSON.Geometry,
      properties: {
        id: r.id,
        category: r.report_category,
        urgency: r.urgency,
        description: r.description,
        color: URGENCY_COLOR[r.urgency] ?? '#6b7280',
      },
    }));
    (map.getSource('incident_reports') as maplibregl.GeoJSONSource)?.setData({
      type: 'FeatureCollection',
      features: reportFeatures,
    })

    // Shelters
    const shelterFeatures: GeoJSON.Feature[] = (layers.shelters ?? []).map((s) => ({
      type: 'Feature',
      geometry: s.geometry as unknown as GeoJSON.Geometry,
      properties: {
        id: s.id,
        name: s.name,
        status: s.status,
        occupancy: `${s.current_occupancy}/${s.total_capacity}`,
      },
    }));
    (map.getSource('shelters') as maplibregl.GeoJSONSource)?.setData({
      type: 'FeatureCollection',
      features: shelterFeatures,
    })

    // Teams
    const teamFeatures: GeoJSON.Feature[] = (layers.teams ?? []).map((t) => ({
      type: 'Feature',
      geometry: t.current_location as unknown as GeoJSON.Geometry,
      properties: { id: t.id, name: t.name, status: t.status, type: t.team_type },
    }));
    (map.getSource('teams') as maplibregl.GeoJSONSource)?.setData({
      type: 'FeatureCollection',
      features: teamFeatures,
    })
  }, [layers])

  // Show/hide layers based on visibleLayers
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return

    const layerMap: Record<LayerId, string[]> = {
      priority_areas: ['priority_areas-fill', 'priority_areas-outline'],
      flood_observations: ['flood_observations-fill'],
      roads: ['roads-line'],
      incident_reports: ['incident_reports-circle'],
      shelters: ['shelters-circle'],
      teams: ['teams-circle'],
    }

    for (const [id, mapLayerIds] of Object.entries(layerMap) as [LayerId, string[]][]) {
      const vis = visibleLayers[id] ? 'visible' : 'none'
      for (const mlId of mapLayerIds) {
        if (map.getLayer(mlId)) {
          map.setLayoutProperty(mlId, 'visibility', vis)
        }
      }
    }
  }, [visibleLayers])

  return <div ref={containerRef} className="w-full h-full" />
}
