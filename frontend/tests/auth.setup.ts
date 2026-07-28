import { request, expect } from '@playwright/test'
import { writeFileSync, mkdirSync } from 'node:fs'
import { dirname } from 'node:path'

const STATE_PATH = 'tests/.auth/storageState.json'
const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000'
const APP_ORIGIN = process.env.APP_ORIGIN ?? 'http://localhost:4173'

export default async function globalSetup() {
  const ctx = await request.newContext()
  const resp = await ctx.post(`${BACKEND_URL}/api/auth/login`, {
    form: {
      username: 'admin@demo.disaster',
      password: 'demo1234',
    },
  })
  expect(resp.ok(), `Login failed: ${resp.status()} ${resp.statusText()}`).toBeTruthy()
  const { access_token } = await resp.json()

  mkdirSync(dirname(STATE_PATH), { recursive: true })
  const storageState = {
    cookies: [],
    origins: [
      {
        origin: APP_ORIGIN,
        localStorage: [{ name: 'resqnet.jwt', value: access_token }],
      },
    ],
  }
  writeFileSync(STATE_PATH, JSON.stringify(storageState, null, 2))
  await ctx.dispose()
}
