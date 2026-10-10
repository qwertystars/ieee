import { useCallback, useEffect, useState } from 'react'
import type { RouteState } from '../types/rescue'
import { EMPTY_ROUTE_STATE, meshApiBase, meshWsUrl, parseRouteMessage } from '../lib/meshRoute'

export type MeshLinkStatus = 'connecting' | 'open' | 'closed' | 'error'

const RETRY_MS = 2000

// Subscribes to the BLE mesh service's live route state, reconnecting on drop.
export function useMeshRoute(apiBase: string = meshApiBase(), enabled = true) {
  const [state, setState] = useState<RouteState>(EMPTY_ROUTE_STATE)
  const [hasReceivedData, setHasReceivedData] = useState(false)
  const [status, setStatus] = useState<MeshLinkStatus>('connecting')
  const [receivedAt, setReceivedAt] = useState<number | null>(null)
  const [resetError, setResetError] = useState<string | null>(null)

  useEffect(() => {
    if (!enabled) return
    let socket: WebSocket | null = null
    let retry: number | null = null
    let active = true

    const connect = () => {
      socket = new WebSocket(meshWsUrl(apiBase))
      socket.onopen = () => active && setStatus('open')
      socket.onmessage = (event) => {
        if (!active) return
        try {
          setState(parseRouteMessage(JSON.parse(event.data)))
          setReceivedAt(Date.now())
          setHasReceivedData(true)
        } catch {
          setStatus('error')
        }
      }
      socket.onerror = () => active && setStatus('error')
      socket.onclose = () => {
        if (!active) return
        setStatus('closed')
        retry = window.setTimeout(() => {
          setStatus('connecting')
          connect()
        }, RETRY_MS)
      }
    }

    connect()
    return () => {
      active = false
      if (retry !== null) window.clearTimeout(retry)
      socket?.close()
    }
  }, [apiBase, enabled])

  // Keep the last picture when a reset fails; do not imply server success.
  const reset = useCallback(async () => {
    if (!enabled) return
    setResetError(null)
    try {
      const response = await fetch(`${apiBase}/api/mesh/reset`, {
        method: 'POST', signal: AbortSignal.timeout(4000),
      })
      if (!response.ok) throw new Error('Reset failed')
      setState(EMPTY_ROUTE_STATE)
      setHasReceivedData(true)
      setReceivedAt(Date.now())
    } catch {
      setResetError('Mesh reset failed. The last received picture has been retained.')
    }
  }, [apiBase, enabled])

  return { state, status, hasReceivedData, receivedAt, resetError, reset }
}
