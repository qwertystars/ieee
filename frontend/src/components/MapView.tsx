import { useEffect, useRef, useState, useCallback } from 'react'
import maplibregl from 'maplibre-gl'
import type { StyleSpecification } from 'maplibre-gl'
import { MapboxOverlay } from '@deck.gl/mapbox'
import { PolygonLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers'
import type { Layer } from '@deck.gl/core'
import { Protocol } from 'pmtiles'
import type { Bbox, LayerConfig, Position } from '../types/map'
import { useMapLayers, MAP_CENTER } from '../hooks/useMapLayers'
import { buildLayers } from './mapLayers'
import { LayerToggle } from './LayerToggle'
import { MapLegend } from './MapLegend'
import { LoadingState, ErrorState } from './state'
import 'maplibre-gl/dist/maplibre-gl.css'

const INITIAL_ZOOM = 12

const PMTILES_URL = '/basemaps/mumbai.pmtiles'

const pmtilesProtocol = new Protocol()
maplibregl.addProtocol('pmtiles', pmtilesProtocol.tile)

const PMTILES_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    mumbai: {
      type: 'vector',
      url: `pmtiles://${PMTILES_URL}`,
    },
  },
  layers: [
    {
      id: 'background',
      type: 'background',
      paint: { 'background-color': '#0f172a' },
    },
    {
      id: 'mumbai-landuse',
      type: 'fill',
      source: 'mumbai',
      'source-layer': 'mumbai',
      filter: ['has', 'landuse'],
      paint: {
        'fill-color': [
          'match', ['get', 'landuse'],
          'residential', '#1e293b',
          'commercial', '#1e293b',
          'industrial', '#1c1917',
          'forest', '#14532d',
          'farmland', '#1a2e1a',
          'park', '#14532d',
          'grass', '#1a3a1a',
          'water', '#0c4a6e',
          '#1e293b',
        ],
        'fill-opacity': 0.6,
      },
    },
    {
      id: 'mumbai-water',
      type: 'fill',
      source: 'mumbai',
      'source-layer': 'mumbai',
      filter: ['any',
        ['has', 'natural'],
        ['has', 'waterway'],
      ],
      paint: { 'fill-color': '#0c4a6e', 'fill-opacity': 0.8 },
    },
    {
      id: 'mumbai-roads',
      type: 'line',
      source: 'mumbai',
      'source-layer': 'mumbai',
      filter: ['has', 'highway'],
      paint: {
        'line-color': '#334155',
        'line-width': [
          'interpolate', ['linear'], ['zoom'],
          8, 0.5,
          12, 1,
          16, 2,
        ],
      },
    },
    {
      id: 'mumbai-buildings',
      type: 'fill',
      source: 'mumbai',
      'source-layer': 'mumbai',
      filter: ['has', 'building'],
      paint: { 'fill-color': '#0f172a', 'fill-opacity': 0.5 },
    },
  ],
}

const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{
    id: 'background',
    type: 'background',
    paint: { 'background-color': '#0f172a' },
  }],
}

interface DrawnZone { id: string; polygon: Position[] }

interface HoverInfo {
  x: number; y: number; layer: string; feature: Record<string, unknown>
}

function formatAge(ms: number): string {
  if (ms === Infinity) return 'no data'
  if (ms < 60_000) return `${Math.round(ms / 1000)}s ago`
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m ago`
  return `${Math.round(ms / 3_600_000)}h ago`
}

export default function MapView() {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const overlayRef = useRef<MapboxOverlay | null>(null)
  const [drawnZones, setDrawnZones] = useState<DrawnZone[]>([])
  const [drawingPoints, setDrawingPoints] = useState<Position[]>([])
  const [isDrawing, setIsDrawing] = useState(false)
  const [now, setNow] = useState(Date.now())
  const [hover, setHover] = useState<HoverInfo | null>(null)

  const {
    data, visibleLayers, layerStates, allConfigs, toggleLayer, fetchByBbox,
    incidentBoundary, rescueBalls, isLoading, isError, refetch,
  } = useMapLayers()

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(t)
  }, [])

  // Initialize MapLibre map once with local PMTiles basemap (no online tiles).
  // Falls back to solid dark background if PMTiles fails to load.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: PMTILES_STYLE,
      center: MAP_CENTER,
      zoom: INITIAL_ZOOM,
    })
    mapRef.current = map
    const overlay = new MapboxOverlay({ interleaved: false })
    map.addControl(overlay)
    overlayRef.current = overlay

    map.on('error', (e: { error?: Error; type?: string }) => {
      const msg = e.error?.message ?? ''
      if (msg.includes('mumbai') || msg.includes('pmtiles')) {
        map.setStyle(FALLBACK_STYLE)
      }
    })

    map.on('moveend', () => {
      const b = map.getBounds()
      const bbox: Bbox = {
        west: b.getWest(), south: b.getSouth(),
        east: b.getEast(), north: b.getNorth(),
      }
      fetchByBbox(bbox)
    })

    map.on('click', (e: maplibregl.MapMouseEvent) => {
      if (!isDrawing) return
      setDrawingPoints(prev => [...prev, [e.lngLat.lng, e.lngLat.lat]])
    })

    map.on('dblclick', (e: maplibregl.MapMouseEvent) => {
      if (!isDrawing) return
      e.preventDefault()
      setDrawingPoints(prev => {
        const pts: Position[] = [...prev, [e.lngLat.lng, e.lngLat.lat]]
        if (pts.length >= 3) {
          setDrawnZones(zones => [...zones, { id: `zone-${Date.now()}`, polygon: pts }])
        }
        return []
      })
    })

    return () => {
      map.remove()
      mapRef.current = null
      overlayRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Update deck.gl layers when data, visibility, or freshness changes.
  useEffect(() => {
    if (!overlayRef.current) return
    const configMap: Record<string, LayerConfig> = {}
    for (const cfg of allConfigs) configMap[cfg.id] = cfg
    const layers: Layer[] = buildLayers({
      data, configs: configMap, visible: visibleLayers, now, drawnZones,
    })

    // Incident boundary — outlined polygon from zone data.
    if (incidentBoundary.length > 0) {
      layers.push(new PolygonLayer({
        id: 'incident-boundary',
        data: incidentBoundary,
        getPolygon: (d: Position[]) => d,
        getFillColor: [59, 130, 246, 15],
        getLineColor: [96, 165, 250, 180],
        getLineWidth: 2,
        lineWidthUnits: 'pixels',
        stroked: true, filled: true, pickable: false,
      }))
    }

    // Rescue-ball sensors — distinct cyan markers with labels.
    if (rescueBalls.length > 0) {
      layers.push(new ScatterplotLayer({
        id: 'rescue-balls',
        data: rescueBalls,
        getPosition: (d: { position: Position }) => d.position,
        getFillColor: (d: { timestamp: number }) => {
          const age = now - d.timestamp
          return age > 3_600_000 ? [30, 80, 90, 200] : [6, 182, 212, 220]
        },
        getRadius: 14, radiusUnits: 'pixels',
        stroked: true, getLineColor: [255, 255, 255, 255], getLineWidth: 2,
        lineWidthUnits: 'pixels', pickable: true,
        onHover: (info) => setHover(info.object ? {
          x: info.x, y: info.y, layer: 'Rescue Ball',
          feature: info.object as Record<string, unknown>,
        } : null),
      }))
      layers.push(new TextLayer({
        id: 'rescue-ball-labels',
        data: rescueBalls,
        getPosition: (d: { position: Position }) => d.position,
        getText: (d: { description: string }) => d.description,
        getSize: 11, getColor: [255, 255, 255, 220],
        getTextAnchor: 'middle', getAlignmentBaseline: 'bottom',
        getPixelOffset: [0, -18], pickable: false,
      }))
    }

    overlayRef.current.setProps({
      layers,
      onHover: (info: { x: number; y: number; object?: unknown; layer?: { id: string } | null }) => {
        if (info.object && info.layer) {
          setHover({
            x: info.x, y: info.y,
            layer: info.layer.id,
            feature: info.object as Record<string, unknown>,
          })
        } else {
          setHover(null)
        }
      },
    })
  }, [data, visibleLayers, now, drawnZones, allConfigs, incidentBoundary, rescueBalls])

  const toggleDrawing = useCallback(() => {
    setIsDrawing(prev => {
      const next = !prev
      if (!next && drawingPoints.length > 0) setDrawingPoints([])
      if (mapRef.current) {
        mapRef.current.getCanvas().style.cursor = next ? 'crosshair' : ''
        if (next) mapRef.current.doubleClickZoom.disable()
        else mapRef.current.doubleClickZoom.enable()
      }
      return next
    })
  }, [drawingPoints.length])

  const clearZones = useCallback(() => {
    setDrawnZones([])
    setDrawingPoints([])
  }, [])

  return (
    <div className="relative h-full w-full bg-gray-900">
      <div ref={containerRef} className="absolute inset-0 h-full w-full" data-testid="map-container" />

      {isLoading && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-gray-950/70" role="status">
          <LoadingState message="Loading map data…" />
        </div>
      )}
      {isError && (
        <div className="absolute right-3 top-3 z-20" role="alert">
          <ErrorState message="Failed to load map data" onRetry={refetch} />
        </div>
      )}

      {/* Layer toggles — left panel */}
      <div className="absolute left-3 top-3 z-10 max-h-[calc(100vh-24px)] w-72 overflow-y-auto rounded-lg border border-gray-700 bg-gray-900/95 p-3 shadow-xl backdrop-blur-sm">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-bold text-gray-100">Map Layers</h2>
          <span className="text-xs text-gray-400">{visibleLayers.size} active</span>
        </div>
        <LayerToggle layerStates={layerStates} onToggle={toggleLayer} />
        <div className="mt-3 flex gap-2 border-t border-gray-700 pt-3">
          <button
            onClick={toggleDrawing}
            aria-label={isDrawing ? 'Finish drawing zone' : 'Start drawing zone'}
            className={`flex-1 rounded px-2 py-1 text-xs font-medium transition-colors ${
              isDrawing ? 'bg-blue-600 text-white hover:bg-blue-500' : 'bg-gray-700 text-gray-200 hover:bg-gray-600'
            }`}
          >
            {isDrawing ? 'Drawing… (dbl-click to finish)' : 'Draw Zone'}
          </button>
          {drawnZones.length > 0 && (
            <button onClick={clearZones} aria-label="Clear drawn zones"
              className="rounded bg-gray-700 px-2 py-1 text-xs text-gray-200 hover:bg-red-700">
              Clear
            </button>
          )}
        </div>
        {drawnZones.length > 0 && (
          <p className="mt-1 text-xs text-gray-400">{drawnZones.length} zone(s) drawn</p>
        )}
      </div>

      {/* Legend — bottom right */}
      <div className="absolute bottom-3 right-3 z-10 rounded-lg border border-gray-700 bg-gray-900/95 p-3 shadow-xl backdrop-blur-sm">
        <MapLegend />
      </div>

      {/* Observation markers indicator — visible when observations are on the map */}
      {data.observations.length > 0 && visibleLayers.has('observations') && (
        <div
          className="absolute bottom-3 left-3 z-10 rounded-lg border border-gray-700 bg-gray-900/95 px-2 py-1 text-xs text-gray-300 shadow-xl"
          data-testid="observation-marker"
          role="status"
          aria-label={`${data.observations.length} observation markers on map`}
        >
          {data.observations.length} observations
        </div>
      )}

      {/* Drawing mode indicator */}
      {isDrawing && (
        <div className="absolute top-3 left-1/2 z-10 -translate-x-1/2 rounded-full bg-blue-600 px-4 py-1 text-xs font-medium text-white shadow-lg">
          Click to add vertices · Double-click to complete zone
        </div>
      )}

      {/* Uncertainty + data-age tooltip */}
      {hover && (
        <div
          className="pointer-events-none absolute z-30 max-w-xs rounded-lg border border-gray-600 bg-gray-900/95 p-2 text-xs text-gray-200 shadow-xl"
          style={{ left: hover.x + 12, top: hover.y + 12 }}
          role="tooltip"
        >
          <div className="font-bold text-blue-300">{hover.layer}</div>
          {(() => {
            const f = hover.feature
            const ts = f.timestamp as number | undefined
            const age = ts ? formatAge(now - ts) : 'unknown'
            const conf = f.confidence as number | undefined
            return (
              <>
                {f.name && <div className="text-gray-300">{String(f.name)}</div>}
                {f.category && <div className="text-gray-400">Category: {String(f.category)}</div>}
                {f.passability && <div className="text-gray-400">Status: {String(f.passability)}</div>}
                <div className="mt-1 border-t border-gray-700 pt-1">
                  <span className="text-gray-500">Age: </span>
                  <span className={age.includes('h') ? 'text-red-400' : 'text-green-400'}>{age}</span>
                  {conf !== undefined && (
                    <><span className="ml-2 text-gray-500">Conf: </span><span className="text-amber-400">{Math.round(conf * 100)}%</span></>
                  )}
                </div>
              </>
            )
          })()}
        </div>
      )}
    </div>
  )
}
