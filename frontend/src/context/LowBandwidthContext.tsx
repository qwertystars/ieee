import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

const STORAGE_KEY = 'resqnet:low-bandwidth'

/** Normal polling: 2s. Low-bandwidth polling: 30s. */
const NORMAL_REFETCH_MS = 2_000
const LOW_BANDWIDTH_REFETCH_MS = 30_000

interface LowBandwidthValue {
  enabled: boolean
  toggle: () => void
  setEnabled: (v: boolean) => void
  refetchInterval: number
  stripMapImagery: boolean
}

const LowBandwidthContext = createContext<LowBandwidthValue | null>(null)

function readStored(): boolean {
  if (typeof window === 'undefined') return false
  try {
    return window.localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function LowBandwidthProvider({ children }: { children: ReactNode }) {
  const [enabled, setEnabled] = useState<boolean>(readStored)

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, enabled ? '1' : '0')
    } catch {
      // localStorage may be unavailable (private mode); preference is session-only.
    }
  }, [enabled])

  const toggle = useCallback(() => setEnabled(prev => !prev), [])

  const value = useMemo<LowBandwidthValue>(() => ({
    enabled,
    toggle,
    setEnabled,
    refetchInterval: enabled ? LOW_BANDWIDTH_REFETCH_MS : NORMAL_REFETCH_MS,
    stripMapImagery: enabled,
  }), [enabled, toggle])

  return (
    <LowBandwidthContext.Provider value={value}>
      {children}
    </LowBandwidthContext.Provider>
  )
}

export function useLowBandwidth(): LowBandwidthValue {
  const ctx = useContext(LowBandwidthContext)
  if (!ctx) {
    throw new Error('useLowBandwidth must be used within LowBandwidthProvider')
  }
  return ctx
}
