export type GridPoint = { x: number; y: number }
export type GridHazard = 'fire' | 'flood' | 'collapse'
export type HazardCells = Record<string, GridHazard>
export const GRID_SIZE = 15
export const cellId = (point: GridPoint) => `${point.x},${point.y}`

// Geometry-only shortest path in a manually edited demonstration grid.
// Every marked hazard is excluded. No model inference or real road data.
export function findGridPath(start: GridPoint, end: GridPoint, hazards: HazardCells): GridPoint[] | null {
  const valid = (p: GridPoint) => Number.isInteger(p.x) && Number.isInteger(p.y)
    && p.x >= 0 && p.y >= 0 && p.x < GRID_SIZE && p.y < GRID_SIZE && !hazards[cellId(p)]
  if (!valid(start) || !valid(end)) return null
  const queue = [start]
  const parents = new Map<string, GridPoint | null>([[cellId(start), null]])
  for (let index = 0; index < queue.length; index++) {
    const current = queue[index]
    if (cellId(current) === cellId(end)) {
      const path: GridPoint[] = []
      let cursor: GridPoint | null = current
      while (cursor) { path.push(cursor); cursor = parents.get(cellId(cursor)) ?? null }
      return path.reverse()
    }
    for (const [dx, dy] of [[1, 0], [0, 1], [-1, 0], [0, -1]]) {
      const next = { x: current.x + dx, y: current.y + dy }
      const id = cellId(next)
      if (valid(next) && !parents.has(id)) { parents.set(id, current); queue.push(next) }
    }
  }
  return null
}
