import { useState } from 'react'
import { cellId, findGridPath, GRID_SIZE, type GridPoint, type HazardCells } from '../lib/routeSandbox'

type Tool = 'start' | 'end' | 'fire' | 'flood' | 'collapse' | 'erase'
const TOOLS: Tool[] = ['start', 'end', 'fire', 'flood', 'collapse', 'erase']
const INITIAL_START = { x: 0, y: 0 }
const INITIAL_END = { x: 14, y: 14 }

export default function RouteSandbox() {
  const [start, setStart] = useState<GridPoint>(INITIAL_START)
  const [end, setEnd] = useState<GridPoint>(INITIAL_END)
  const [hazards, setHazards] = useState<HazardCells>({})
  const [tool, setTool] = useState<Tool>('fire')
  const [result, setResult] = useState<GridPoint[] | null | undefined>()
  const path = new Set(result?.map(cellId))

  function edit(point: GridPoint) {
    const id = cellId(point)
    setResult(undefined)
    if (tool === 'start') setStart(point)
    if (tool === 'end') setEnd(point)
    setHazards(current => {
      const next = { ...current }
      if (tool === 'start' || tool === 'end' || tool === 'erase') delete next[id]
      else if (id !== cellId(start) && id !== cellId(end)) next[id] = tool
      return next
    })
  }

  return (
    <div className="grid gap-6 p-5 lg:grid-cols-[1fr_320px]">
      <div>
        <div className="mb-4 flex flex-wrap gap-2" aria-label="Route grid tools">
          {TOOLS.map(value => <button key={value} type="button" aria-pressed={tool === value} onClick={() => setTool(value)} className={`rounded px-3 py-2 text-xs capitalize ${tool === value ? 'bg-cyan-700 text-white' : 'bg-slate-800 text-slate-300'}`}>{value}</button>)}
        </div>
        <div className="grid aspect-square max-w-[600px] gap-0.5 rounded-lg bg-slate-800 p-1" style={{ gridTemplateColumns: `repeat(${GRID_SIZE}, minmax(0, 1fr))` }} aria-label="Demonstration route grid">
          {Array.from({ length: GRID_SIZE * GRID_SIZE }, (_, index) => {
            const point = { x: index % GRID_SIZE, y: Math.floor(index / GRID_SIZE) }
            const id = cellId(point)
            const isStart = id === cellId(start)
            const isEnd = id === cellId(end)
            const hazard = hazards[id]
            const color = isStart ? 'bg-emerald-600' : isEnd ? 'bg-purple-600' : hazard === 'fire' ? 'bg-orange-700' : hazard === 'flood' ? 'bg-blue-700' : hazard === 'collapse' ? 'bg-red-800' : path.has(id) ? 'bg-cyan-500' : 'bg-slate-950 hover:bg-slate-700'
            return <button key={id} type="button" onClick={() => edit(point)} aria-label={`Cell ${point.x}, ${point.y}${isStart ? ', start' : isEnd ? ', destination' : hazard ? `, ${hazard}` : path.has(id) ? ', path' : ''}`} className={`min-w-0 rounded-sm text-[10px] text-white focus:outline-none focus:ring-2 focus:ring-white ${color}`}>{isStart ? 'S' : isEnd ? 'E' : hazard === 'fire' ? 'F' : hazard === 'flood' ? 'W' : hazard === 'collapse' ? 'X' : ''}</button>
          })}
        </div>
      </div>
      <aside className="space-y-4 text-sm text-slate-300">
        <h2 className="text-lg font-semibold text-white">Route planning sandbox</h2>
        <p className="text-xs text-slate-400">Manual hazard grid · shortest-path routing.</p>
        <p>Select a tool and click cells to set the start, destination, fire, flood or collapsed areas. Marked hazards block traversal.</p>
        <button type="button" onClick={() => setResult(findGridPath(start, end, hazards))} className="rounded bg-cyan-700 px-4 py-2 text-white">Calculate demo path</button>
        <button type="button" onClick={() => { setStart(INITIAL_START); setEnd(INITIAL_END); setHazards({}); setResult(undefined) }} className="ml-2 rounded border border-slate-600 px-4 py-2">Clear grid</button>
        <p role="status">{result === undefined ? 'Ready to plan.' : result === null ? 'No path connects these cells. Change the hazards or endpoints.' : `Draft path: ${result.length - 1} grid steps; ${Object.keys(hazards).length} blocked cells.`}</p>
      </aside>
    </div>
  )
}
