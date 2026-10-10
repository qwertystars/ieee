import { useCallback, useEffect, useState } from 'react'
import type { RouteState } from '../types/rescue'
import { EMPTY_ROUTE_STATE, meshApiBase, meshWsUrl, parseRouteMessage } from '../lib/meshRoute'

export type MeshLinkStatus = 'connecting' | 'open' | 'closed' | 'error'

const RETRY_MS = 2000

// Subscribes to the BLE mesh service's live route state, reconnecting on drop.
export function useMeshRoute(apiBase: string = meshApiBase()) {
  const [state, setState] = useState<RouteState>(EMPTY_ROUTE_STATE)
  const [hasReceivedData, setHasReceivedData] = useState(false)
  const [status, setStatus] = useState<MeshLinkStatus>('connecting')

  useEffect(() => {
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
  }, [apiBase])

  // Clears the local picture immediately; the service broadcasts the empty
  // state to other viewers when its reset succeeds.
  const reset = useCallback(async () => {
    setState(EMPTY_ROUTE_STATE)
    setHasReceivedData(true)
    try {
      await fetch(`${apiBase}/api/mesh/reset`, { method: 'POST' })
    } catch {
      // Local state stays cleared even if the service is unreachable.
    }
  }, [apiBase])

  return { state, status, hasReceivedData, reset }
}
