import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

const CATEGORIES = ['flooding', 'structural', 'medical', 'rescue', 'logistics', 'other']
const URGENCIES = ['low', 'medium', 'high', 'critical']

interface ReportForm {
  category: string
  urgency: string
  description: string
  water_depth: string
  people: string
  lat: string
  lon: string
}

const EMPTY_FORM: ReportForm = {
  category: 'flooding', urgency: 'medium', description: '',
  water_depth: '', people: '', lat: '', lon: '',
}

interface QuickReportFormProps {
  incidentId: string
  onDone: () => void
  showToast: (msg: string, kind?: 'success' | 'error') => void
}

export function QuickReportForm({ incidentId, onDone, showToast }: QuickReportFormProps) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<ReportForm>(EMPTY_FORM)

  const reportMut = useMutation({
    mutationFn: () => {
      const props: Record<string, unknown> = {}
      if (form.water_depth) props.water_depth = parseFloat(form.water_depth)
      if (form.people) props.people_count = parseInt(form.people, 10)
      const lat = parseFloat(form.lat)
      const lon = parseFloat(form.lon)
      return api.createTask(incidentId, {
        title: form.description || `Field report: ${form.category}`,
        priority: form.urgency,
        required_capability: form.category,
        geometry: !isNaN(lat) && !isNaN(lon) ? { type: 'Point', coordinates: [lon, lat] } : null,
        properties: props,
      })
    },
    onSuccess: () => {
      showToast('Report submitted')
      setForm(EMPTY_FORM)
      queryClient.invalidateQueries({ queryKey: ['tasks', incidentId] })
      queryClient.invalidateQueries({ queryKey: ['entities', incidentId] })
      onDone()
    },
    onError: (e: unknown) => showToast(e instanceof Error ? e.message : 'Report failed', 'error'),
  })

  function handleGeolocate() {
    if (!navigator.geolocation) {
      showToast('Geolocation not available', 'error')
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => setForm(f => ({ ...f, lat: pos.coords.latitude.toFixed(6), lon: pos.coords.longitude.toFixed(6) })),
      () => showToast('Geolocation denied', 'error'),
    )
  }

  const inputCls = 'min-h-[44px] rounded border border-gray-600 bg-gray-800 px-3 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500'

  return (
    <section className="rounded-lg border border-gray-700 bg-gray-900/95 p-3" aria-label="Quick report form">
      <div className="flex flex-col gap-2">
        <label className="text-xs text-gray-400" htmlFor="rpt-category">Category</label>
        <select id="rpt-category" value={form.category}
          onChange={(e) => setForm(f => ({ ...f, category: e.target.value }))}
          className={inputCls} aria-label="Report category">
          {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>

        <label className="text-xs text-gray-400" htmlFor="rpt-urgency">Urgency</label>
        <select id="rpt-urgency" value={form.urgency}
          onChange={(e) => setForm(f => ({ ...f, urgency: e.target.value }))}
          className={inputCls} aria-label="Report urgency">
          {URGENCIES.map(u => <option key={u} value={u}>{u}</option>)}
        </select>

        <label className="text-xs text-gray-400" htmlFor="rpt-desc">Description</label>
        <textarea id="rpt-desc" value={form.description} rows={2}
          onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))}
          className="rounded border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          aria-label="Report description" placeholder="What do you see?" />

        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-xs text-gray-400" htmlFor="rpt-depth">Water depth (m)</label>
            <input id="rpt-depth" type="number" step="0.1" value={form.water_depth}
              onChange={(e) => setForm(f => ({ ...f, water_depth: e.target.value }))}
              className={inputCls} aria-label="Water depth in meters" />
          </div>
          <div>
            <label className="text-xs text-gray-400" htmlFor="rpt-people">People</label>
            <input id="rpt-people" type="number" value={form.people}
              onChange={(e) => setForm(f => ({ ...f, people: e.target.value }))}
              className={inputCls} aria-label="Number of people affected" />
          </div>
        </div>

        <button onClick={handleGeolocate}
          className="min-h-[44px] rounded-lg border border-gray-600 bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          aria-label="Geolocate my position">
          📍 Geolocate
        </button>
        {form.lat && form.lon && (
          <p className="text-[11px] text-gray-500" aria-label="Current position">
            {form.lat}, {form.lon}
          </p>
        )}

        <button onClick={() => reportMut.mutate()} disabled={reportMut.isPending || !form.description}
          className="min-h-[44px] rounded-lg bg-green-600 px-4 py-3 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-green-500"
          aria-label="Submit report">
          Submit Report
        </button>
      </div>
    </section>
  )
}
