// Geo helpers for MapLibre

import type { GeoGeometry, GeoPoint } from '../types'

/** Convert a GeoJSON point to [lng, lat] tuple */
export function pointCoords(pt: GeoPoint): [number, number] {
  return [pt.coordinates[0], pt.coordinates[1]]
}

/** Parse bbox string "minx,miny,maxx,maxy" */
export function parseBbox(bbox: string): [number, number, number, number] {
  const parts = bbox.split(',').map(Number)
  return [parts[0], parts[1], parts[2], parts[3]] as [number, number, number, number]
}

/** Format map bounds as bbox query param */
export function boundsToParam(bounds: {
  getWest(): number
  getSouth(): number
  getEast(): number
  getNorth(): number
}): string {
  return `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`
}

/** Lightweight centroid for a geometry (for popup placement) */
export function geometryCentroid(geom: GeoGeometry): [number, number] {
  if (geom.type === 'Point') return geom.coordinates as [number, number]
  if (geom.type === 'LineString') {
    const mid = Math.floor(geom.coordinates.length / 2)
    return geom.coordinates[mid] as [number, number]
  }
  if (geom.type === 'Polygon') {
    const coords = geom.coordinates[0]
    const lng = coords.reduce((s, c) => s + c[0], 0) / coords.length
    const lat = coords.reduce((s, c) => s + c[1], 0) / coords.length
    return [lng, lat]
  }
  // MultiPolygon — use first polygon
  const coords = (geom as { type: 'MultiPolygon'; coordinates: [number, number][][][] }).coordinates[0][0]
  const lng = coords.reduce((s, c) => s + c[0], 0) / coords.length
  const lat = coords.reduce((s, c) => s + c[1], 0) / coords.length
  return [lng, lat]
}
