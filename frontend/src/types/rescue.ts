// Live rescue picture pushed by the BLE localization service
// (modules/ble_localization) over its /ws/route WebSocket.

export type Vec3 = {
  x: number
  y: number
  z: number
}

export type Urgency = 'low' | 'medium' | 'high'

export type Survivor = {
  id: string
  position: Vec3
  urgency: Urgency
  relayNodeId?: string
  confidence?: number
  lat?: number
  lng?: number
}

export type Hazard = {
  id: string
  position: Vec3
}

export type RouteState = {
  path: Vec3[]
  survivors: Survivor[]
  hazards: Hazard[]
}
