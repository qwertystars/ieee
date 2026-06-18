// WebSocket helper — auto-reconnect with polling fallback (DESIGN §11)

import type { WsEvent } from '../types'

type EventHandler = (evt: WsEvent) => void

export class DisasterWsClient {
  private ws: WebSocket | null = null
  private handlers = new Set<EventHandler>()
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private stopped = false

  constructor(
    private readonly eventId: string,
    private readonly token: string | null,
  ) {}

  connect() {
    if (this.stopped) return
    try {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const url = `${proto}://${location.host}/ws/events/${this.eventId}${this.token ? `?token=${this.token}` : ''}`
      this.ws = new WebSocket(url)

      this.ws.onmessage = (e) => {
        try {
          const evt = JSON.parse(e.data) as WsEvent
          this.handlers.forEach((h) => h(evt))
        } catch {
          // ignore malformed messages
        }
      }

      this.ws.onclose = () => {
        if (!this.stopped) this.scheduleReconnect()
      }

      this.ws.onerror = () => {
        this.ws?.close()
      }
    } catch {
      this.scheduleReconnect()
    }
  }

  private scheduleReconnect(delayMs = 5_000) {
    if (this.stopped) return
    this.reconnectTimer = setTimeout(() => this.connect(), delayMs)
  }

  subscribe(handler: EventHandler): () => void {
    this.handlers.add(handler)
    return () => this.handlers.delete(handler)
  }

  disconnect() {
    this.stopped = true
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.ws?.close()
    this.ws = null
  }
}
