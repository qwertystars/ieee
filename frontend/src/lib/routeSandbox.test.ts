import { describe, expect, it } from 'vitest'
import { findGridPath } from './routeSandbox'

describe('demonstration grid routing', () => {
  it('takes a shortest path and avoids blocked cells', () => {
    const path = findGridPath({ x: 0, y: 0 }, { x: 2, y: 0 }, { '1,0': 'fire' })
    expect(path).toHaveLength(5)
    expect(path).not.toContainEqual({ x: 1, y: 0 })
    expect(path?.[0]).toEqual({ x: 0, y: 0 })
    expect(path && path[path.length - 1]).toEqual({ x: 2, y: 0 })
  })
  it('reports unreachable, blocked and invalid endpoints', () => {
    expect(findGridPath({ x: 0, y: 0 }, { x: 2, y: 2 }, { '1,0': 'fire', '0,1': 'flood' })).toBeNull()
    expect(findGridPath({ x: 0, y: 0 }, { x: 1, y: 0 }, { '1,0': 'collapse' })).toBeNull()
    expect(findGridPath({ x: -1, y: 0 }, { x: 1, y: 0 }, {})).toBeNull()
  })
  it('supports a destination equal to the start', () => {
    expect(findGridPath({ x: 0, y: 0 }, { x: 0, y: 0 }, {})).toEqual([{ x: 0, y: 0 }])
  })
})
