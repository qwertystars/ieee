import { useEffect, useState } from 'react'
import { meshApiBase } from '../lib/meshRoute'

export type MeshHealthStatus = 'checking' | 'online' | 'offline'

const POLL_MS = 5000
const TIMEOUT_MS = 3000

// Polls the BLE mesh service's /health endpoint.
export function useMeshHealth(apiBase: string = meshApiBase(), enabled = true) {
  const [status, setStatus] = useState<MeshHealthStatus>('checking')

  useEffect(() => {
    if (!enabled) return
    let active = true
    let timer: number | null = null

    const check = async () => {
      const controller = new AbortController()
      const timeout = window.setTimeout(() => controller.abort(), TIMEOUT_MS)
      try {
        const response = await fetch(`${apiBase}/health`, {
          signal: controller.signal,
          cache: 'no-store',
        })
        if (active) setStatus(response.ok ? 'online' : 'offline')
      } catch {
        if (active) setStatus('offline')
      } finally {
        window.clearTimeout(timeout)
      }
      if (active) timer = window.setTimeout(check, POLL_MS)
    }

    void check()
    return () => {
      active = false
      if (timer !== null) window.clearTimeout(timer)
    }
  }, [apiBase, enabled])

  return status
}
