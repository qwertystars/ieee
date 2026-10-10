import { useEffect, useState } from 'react'

const TYPE_MS = 32
const LINE_MS = 2200

type CommandLogProps = {
  lines: string[]
}

// Cycles through status lines with a typewriter effect.
export function CommandLog({ lines }: CommandLogProps) {
  const [lineIndex, setLineIndex] = useState(0)
  const [chars, setChars] = useState(0)

  const line = lines.length ? lines[lineIndex % lines.length] : 'Awaiting inbound telemetry…'

  useEffect(() => {
    const interval = window.setInterval(() => {
      setChars((c) => (c >= line.length ? c : c + 1))
    }, TYPE_MS)
    const timeout = window.setTimeout(() => {
      setChars(0)
      setLineIndex((i) => i + 1)
    }, LINE_MS)
    return () => {
      window.clearInterval(interval)
      window.clearTimeout(timeout)
    }
  }, [line, lineIndex])

  return (
    <section className="rescue-panel w-full" aria-label="Command log">
      <header className="flex items-center justify-between">
        <p className="rescue-eyebrow">Command Log</p>
        <span className="text-xs text-slate-400">LIVE FEED</span>
      </header>
      <div className="mt-4 rounded-xl bg-black/50 px-4 py-3 font-mono text-xs text-cyan-200">
        <span className="text-cyan-500" aria-hidden="true">&gt;</span>{' '}
        <span>{line.slice(0, chars)}</span>
      </div>
    </section>
  )
}
