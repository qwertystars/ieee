// Location sharing beacon — manual + auto (every 2 min) via PATCH /teams/{id}/location

import React, { useState, useEffect, useCallback, useRef } from 'react'
import { teamsApi } from '../../api/client'
import { formatRelative } from '../../lib/format'

interface Props {
  teamId: string
}

type ShareStatus = 'idle' | 'sharing' | 'ok' | 'error'

export default function LocationBeacon({ teamId }: Props) {
  const [status, setStatus] = useState<ShareStatus>('idle')
  const [lastShared, setLastShared] = useState<string | null>(null)
  const [autoShare, setAutoShare] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const share = useCallback(async () => {
    if (!navigator.geolocation) {
      setStatus('error')
      return
    }
    setStatus('sharing')
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          await teamsApi.patchLocation(teamId, {
            current_location: {
              type: 'Point',
              coordinates: [pos.coords.longitude, pos.coords.latitude],
            },
          })
          setLastShared(new Date().toISOString())
          setStatus('ok')
          setTimeout(() => setStatus('idle'), 2000)
        } catch {
          setStatus('error')
        }
      },
      () => setStatus('error'),
      { timeout: 10_000, maximumAge: 10_000 },
    )
  }, [teamId])

  // Auto-share every 2 minutes when toggled on
  useEffect(() => {
    if (autoShare) {
      share()
      intervalRef.current = setInterval(share, 120_000)
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [autoShare, share])

  return (
    <div className="rounded-lg border border-gray-700 bg-gray-900 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white">📍 Location Sharing</h3>

        {/* Auto-share toggle */}
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <span className="text-xs text-gray-400">Auto (2 min)</span>
          <button
            type="button"
            role="switch"
            aria-checked={autoShare}
            onClick={() => setAutoShare((v) => !v)}
            className={`relative w-10 h-5 rounded-full transition-colors ${
              autoShare ? 'bg-blue-600' : 'bg-gray-700'
            }`}
          >
            <span
              className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
                autoShare ? 'translate-x-5' : 'translate-x-0.5'
              }`}
            />
          </button>
        </label>
      </div>

      {lastShared && (
        <p className="text-xs text-gray-500 mb-3">
          Last shared: {formatRelative(lastShared)}
        </p>
      )}

      {status === 'error' && (
        <p className="text-xs text-red-400 mb-2">GPS unavailable or update failed</p>
      )}

      <button
        type="button"
        onClick={share}
        disabled={status === 'sharing'}
        className={`w-full py-2.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${
          status === 'ok'
            ? 'bg-green-800 text-green-200'
            : 'bg-gray-700 text-white hover:bg-gray-600'
        }`}
      >
        {status === 'sharing' ? '…locating' : status === 'ok' ? '✓ Shared' : 'Share Now'}
      </button>
    </div>
  )
}
