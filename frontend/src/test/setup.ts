// Vitest global setup — runs before every test file.
import 'fake-indexeddb/auto'
import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, vi } from 'vitest'
import { clearToken } from '../api/token'

// Reset the in-memory token + localStorage between tests so auth state
// never leaks across files. fake-indexeddb auto-clears on each load, but
// we also reset the singleton DB connection in outbox.ts via vi.resetModules
// in the outbox test itself.
beforeEach(() => {
  localStorage.clear()
  clearToken()
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
