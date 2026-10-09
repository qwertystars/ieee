import { describe, expect, it } from 'vitest'
import { meshWsUrl, normalizeVec3, parseRouteMessage } from './meshRoute'

describe('normalizeVec3', () => {
  it('accepts arrays and objects, defaulting z to 0', () => {
    expect(normalizeVec3([1, 2])).toEqual({ x: 1, y: 2, z: 0 })
    expect(normalizeVec3({ x: 1, y: 2, z: 3 })).toEqual({ x: 1, y: 2, z: 3 })
  })

  it('rejects malformed points', () => {
    expect(normalizeVec3(['a', 2])).toBeNull()
    expect(normalizeVec3({ x: 1 })).toBeNull()
    expect(normalizeVec3(null)).toBeNull()
  })
})

describe('parseRouteMessage', () => {
  it('maps the BLE service payload', () => {
    const state = parseRouteMessage({
      path: [{ x: 0, y: 0, z: 0.2 }],
      survivors: [
        { id: 'S-1', x: 3, y: 4, lat: 17.4, lng: 78.3, urgency: 'high', relay_node_id: 'R-7' },
      ],
      blocked_edges: [{ x: 3, y: 4, z: 0.6 }],
    })
    expect(state.path).toEqual([{ x: 0, y: 0, z: 0.2 }])
    expect(state.survivors).toEqual([
      {
        id: 'S-1',
        position: { x: 3, y: 4, z: 0 },
        urgency: 'high',
        relayNodeId: 'R-7',
        confidence: undefined,
        lat: 17.4,
        lng: 78.3,
      },
    ])
    expect(state.hazards).toEqual([{ id: 'HZ-1', position: { x: 3, y: 4, z: 0.6 } }])
  })

  it('defaults unknown urgency to medium and drops bad entries', () => {
    const state = parseRouteMessage({
      survivors: [{ x: 1, y: 1, urgency: 'critical' }, { nope: true }],
    })
    expect(state.survivors).toHaveLength(1)
    expect(state.survivors[0].urgency).toBe('medium')
    expect(state.survivors[0].id).toBe('S-1')
  })

  it('returns an empty state for non-objects', () => {
    expect(parseRouteMessage('garbage')).toEqual({ path: [], survivors: [], hazards: [] })
  })
})

describe('meshWsUrl', () => {
  it('derives the websocket url from the http base', () => {
    expect(meshWsUrl('http://10.0.0.5:8001')).toBe('ws://10.0.0.5:8001/ws/route')
    expect(meshWsUrl('https://mesh.example.org')).toBe('wss://mesh.example.org/ws/route')
  })
})
