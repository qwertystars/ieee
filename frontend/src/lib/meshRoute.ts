// Parsing and endpoint helpers for the BLE mesh localization service
// (modules/ble_localization/main.py). Kept free of React so it can be
// unit-tested directly.
import type { Hazard, RouteState, Survivor, Urgency, Vec3 } from '../types/rescue'

// The mesh service runs separately from the platform backend; it defaults to
// port 8001 on the same host so the two don't collide on 8000.
export function meshApiBase(): string {
  const env = import.meta.env.VITE_MESH_API_BASE
  if (env) return env.replace(/\/+$/, '')
  return `${window.location.protocol}//${window.location.hostname}:8001`
}

export function meshWsUrl(apiBase: string = meshApiBase()): string {
  return `${apiBase.replace(/^http/, 'ws')}/ws/route`
}

export const EMPTY_ROUTE_STATE: RouteState = { path: [], survivors: [], hazards: [] }

export function normalizeVec3(value: unknown): Vec3 | null {
  if (Array.isArray(value)) {
    const [x, y, z] = value
    if (typeof x === 'number' && typeof y === 'number') {
      return { x, y, z: typeof z === 'number' ? z : 0 }
    }
    return null
  }
  if (value && typeof value === 'object') {
    const { x, y, z } = value as { x?: unknown; y?: unknown; z?: unknown }
    if (typeof x === 'number' && typeof y === 'number') {
      return { x, y, z: typeof z === 'number' ? z : 0 }
    }
  }
  return null
}

function isUrgency(value: unknown): value is Urgency {
  return value === 'low' || value === 'medium' || value === 'high'
}

function mapSurvivor(value: unknown, index: number): Survivor | null {
  if (!value || typeof value !== 'object') return null
  const data = value as Record<string, unknown>
  const position = normalizeVec3(data.position ?? data)
  if (!position) return null

  const relay = data.relayNodeId ?? data.relay_node_id
  return {
    id: data.id !== undefined && data.id !== null ? String(data.id) : `S-${index + 1}`,
    position,
    urgency: isUrgency(data.urgency) ? data.urgency : 'medium',
    relayNodeId: typeof relay === 'string' ? relay : undefined,
    confidence: typeof data.confidence === 'number' ? data.confidence : undefined,
    lat: typeof data.lat === 'number' ? data.lat : undefined,
    lng: typeof data.lng === 'number' ? data.lng : undefined,
  }
}

function mapHazard(value: unknown, index: number): Hazard | null {
  const position = normalizeVec3(value)
  return position ? { id: `HZ-${index + 1}`, position } : null
}

function mapList<T>(source: unknown, fn: (value: unknown, index: number) => T | null): T[] {
  if (!Array.isArray(source)) return []
  return source.map(fn).filter((item): item is T => item !== null)
}

// Accepts the service's payload ({path, survivors, blocked_edges}) and the
// older blocked_nodes / hazards spellings.
export function parseRouteMessage(payload: unknown): RouteState {
  if (!payload || typeof payload !== 'object') return EMPTY_ROUTE_STATE
  const data = payload as Record<string, unknown>
  return {
    path: mapList(data.path, normalizeVec3),
    survivors: mapList(data.survivors, mapSurvivor),
    hazards: mapList(data.blocked_edges ?? data.blocked_nodes ?? data.hazards, mapHazard),
  }
}
