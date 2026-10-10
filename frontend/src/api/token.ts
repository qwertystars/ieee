const TOKEN_KEY = 'resqnet.jwt'

let inMemoryToken: string | null = null

export function getToken(): string | null {
  if (inMemoryToken) return inMemoryToken
  try {
    const stored = localStorage.getItem(TOKEN_KEY)
    inMemoryToken = stored
    return stored
  } catch {
    return null
  }
}

export function setToken(token: string | null): void {
  inMemoryToken = token
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // localStorage may be unavailable (private mode); in-memory only.
  }
}

export function clearToken(): void {
  setToken(null)
}
