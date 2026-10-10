import { describe, expect, it } from 'vitest'
import { parseThermalDetections } from './ThermalPanel'

const detection = { id: 1, timestamp: 1700000000, coords: [0.2, 0.8], confidence: 0.9, radius: 4 }

describe('thermal feed boundary', () => {
  it('accepts camera-coordinate detections and empty feeds', () => {
    expect(parseThermalDetections([detection])).toEqual([detection])
    expect(parseThermalDetections([])).toEqual([])
  })
  it('rejects malformed coordinates, confidence and timestamps', () => {
    for (const invalid of [null, {}, [{ ...detection, coords: [2, 0] }],
      [{ ...detection, confidence: Number.NaN }], [{ ...detection, timestamp: 'yesterday' }]]) {
      expect(() => parseThermalDetections(invalid)).toThrow()
    }
  })
})
