import type { ReactNode } from 'react'

export function OperationsPanel({ title, status, children }: {
  title: string; status?: string; children: ReactNode
}) {
  return (
    <section className="min-w-0 rounded-xl border border-slate-800 bg-slate-900/70 p-5" aria-label={title}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
        {status && <span role="status" className="rounded-full bg-slate-800 px-3 py-1 text-xs text-cyan-200">{status}</span>}
      </div>
      {children}
    </section>
  )
}
