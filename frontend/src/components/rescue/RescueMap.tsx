import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import type { StyleSpecification } from 'maplibre-gl'
import type { Survivor } from '../../types/rescue'
import 'maplibre-gl/dist/maplibre-gl.css'

// Satellite imagery with a label overlay, as used by the field team's
// original dashboard. Needs network access, unlike the PMTiles basemap on
// the main dashboard.
const IMAGERY_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    imagery: {
      type: 'raster',
      tiles: [
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      ],
      tileSize: 256,
      attribution:
        'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
    },
    labels: {
      type: 'raster',
      tiles: ['a', 'b', 'c'].map(
        (sub) => `https://${sub}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}.png`,
      ),
      tileSize: 256,
      attribution: '&copy; <a href="https://carto.com/attributions">CARTO</a>',
    },
  },
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#020617' } },
    { id: 'imagery', type: 'raster', source: 'imagery' },
    { id: 'labels', type: 'raster', source: 'labels' },
  ],
}

const DEFAULT_CENTER: [number, number] = [78.38, 17.45]
const DEFAULT_ZOOM = 13
// Keeps fitted markers clear of the HUD panels overlaid on the map.
const FIT_PADDING = { top: 100, bottom: 200, left: 380, right: 440 }

const URGENCY_COLOR: Record<Survivor['urgency'], string> = {
  high: 'bg-red-500',
  medium: 'bg-cyan-400',
  low: 'bg-blue-400',
}

function survivorElement(survivor: Survivor): HTMLElement {
  const color = URGENCY_COLOR[survivor.urgency]
  const el = document.createElement('div')
  el.className = 'relative flex h-8 w-8 items-center justify-center'
  el.setAttribute('aria-label', `Survivor ${survivor.id}, ${survivor.urgency} urgency`)
  el.innerHTML = `
    <span class="absolute h-8 w-8 rounded-full ${color} opacity-25 animate-ping"></span>
    <span class="relative h-4 w-4 rounded-full border-2 border-white ${color}"></span>
  `
  return el
}

type RescueMapProps = {
  survivors: Survivor[]
}

export function RescueMap({ survivors }: RescueMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const markersRef = useRef<maplibregl.Marker[]>([])

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: IMAGERY_STYLE,
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // Survivor markers; refit the view whenever the located set changes.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    markersRef.current.forEach((marker) => marker.remove())

    const located = survivors.filter(
      (s): s is Survivor & { lat: number; lng: number } =>
        s.lat !== undefined && s.lng !== undefined,
    )
    markersRef.current = located.map((s) =>
      new maplibregl.Marker({ element: survivorElement(s) })
        .setLngLat([s.lng, s.lat])
        .setPopup(new maplibregl.Popup({ offset: 16 }).setText(`Survivor ${s.id} · ${s.urgency}`))
        .addTo(map),
    )

    if (located.length > 0) {
      const bounds = new maplibregl.LngLatBounds()
      located.forEach((s) => bounds.extend([s.lng, s.lat]))
      map.fitBounds(bounds, { padding: FIT_PADDING, maxZoom: 16, duration: 600 })
    }
  }, [survivors])

  return <div ref={containerRef} className="h-full w-full" data-testid="rescue-map" />
}
