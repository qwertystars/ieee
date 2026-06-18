// Quick incident report form — mobile-first, offline-aware, geolocation-enabled

import React, { useState, useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { reportsApi } from '../../api/client'
import type { ReportCategory, Urgency, IncidentReportCreate } from '../../types'
import { enqueueReport } from '../../lib/offlineQueue'

interface CategoryOption {
  value: ReportCategory
  label: string
  icon: string
}

const CATEGORIES: CategoryOption[] = [
  { value: 'trapped_person',       label: 'Trapped Person',     icon: '🆘' },
  { value: 'medical_emergency',    label: 'Medical',            icon: '🏥' },
  { value: 'road_blocked',         label: 'Road Blocked',       icon: '🚧' },
  { value: 'flooding',             label: 'Flooding',           icon: '🌊' },
  { value: 'power_outage',         label: 'Power Outage',       icon: '⚡' },
  { value: 'shelter_need',         label: 'Shelter Need',       icon: '🏠' },
  { value: 'infrastructure_damage',label: 'Infrastructure',     icon: '🏗️' },
  { value: 'other',                label: 'Other',              icon: '📋' },
]

const URGENCIES: { value: Urgency; label: string; active: string }[] = [
  { value: 'low',      label: 'Low',      active: 'border-green-500 bg-green-900/40 text-green-300' },
  { value: 'medium',   label: 'Med',      active: 'border-yellow-500 bg-yellow-900/40 text-yellow-300' },
  { value: 'high',     label: 'High',     active: 'border-orange-500 bg-orange-900/40 text-orange-300' },
  { value: 'critical', label: 'Critical', active: 'border-red-500 bg-red-900/40 text-red-300' },
]

interface Props {
  eventId: string
  onSubmitSuccess?: () => void
}

interface FormState {
  category: ReportCategory | ''
  urgency: Urgency | ''
  description: string
  lat: string
  lng: string
  photoUrl: string
  waterDepth: string
  peopleCount: string
}

const EMPTY_FORM: FormState = {
  category: '', urgency: '', description: '',
  lat: '', lng: '', photoUrl: '', waterDepth: '', peopleCount: '',
}

type GeoStatus = 'idle' | 'loading' | 'done' | 'error'
type SubmitState = 'idle' | 'success' | 'queued'

export default function QuickReportForm({ eventId, onSubmitSuccess }: Props) {
  const qc = useQueryClient()
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [geoStatus, setGeoStatus] = useState<GeoStatus>('idle')
  const [submitState, setSubmitState] = useState<SubmitState>('idle')

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const geolocate = useCallback(() => {
    if (!navigator.geolocation) { setGeoStatus('error'); return }
    setGeoStatus('loading')
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        set('lat', pos.coords.latitude.toFixed(6))
        set('lng', pos.coords.longitude.toFixed(6))
        setGeoStatus('done')
      },
      () => setGeoStatus('error'),
      { timeout: 10_000, maximumAge: 30_000 },
    )
  }, [])

  const buildPayload = (): IncidentReportCreate | null => {
    if (!form.category || !form.urgency) return null
    const lat = parseFloat(form.lat)
    const lng = parseFloat(form.lng)
    if (isNaN(lat) || isNaN(lng)) return null

    const meta: Record<string, unknown> = {}
    if (form.waterDepth) meta['water_depth_m'] = parseFloat(form.waterDepth)
    if (form.peopleCount) meta['people_count'] = parseInt(form.peopleCount, 10)

    return {
      event_id: eventId,
      reporter_type: 'field_responder',
      report_category: form.category as ReportCategory,
      description: form.description || form.category.replace(/_/g, ' '),
      geometry: { type: 'Point', coordinates: [lng, lat] },
      urgency: form.urgency as Urgency,
      ...(form.photoUrl ? { photo_url: form.photoUrl } : {}),
      ...(Object.keys(meta).length ? { metadata: meta } : {}),
    }
  }

  const reset = () => {
    setForm(EMPTY_FORM)
    setGeoStatus('idle')
  }

  const mutation = useMutation({
    mutationFn: (data: IncidentReportCreate) => reportsApi.create(eventId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reports'] })
      setSubmitState('success')
      reset()
      onSubmitSuccess?.()
      setTimeout(() => setSubmitState('idle'), 3000)
    },
    onError: () => {
      // Offline fallback — queue locally
      const payload = buildPayload()
      if (payload) {
        enqueueReport(eventId, payload)
        setSubmitState('queued')
        reset()
        onSubmitSuccess?.()
        setTimeout(() => setSubmitState('idle'), 4000)
      }
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const payload = buildPayload()
    if (!payload) return
    setSubmitState('idle')
    mutation.mutate(payload)
  }

  // Quick-fill helpers for critical shortcuts
  const quickFill = (category: ReportCategory) => {
    setForm((f) => ({ ...f, category, urgency: 'critical' }))
  }

  const locationOk =
    form.lat !== '' &&
    form.lng !== '' &&
    !isNaN(parseFloat(form.lat)) &&
    !isNaN(parseFloat(form.lng))

  const canSubmit = !!form.category && !!form.urgency && locationOk && !mutation.isPending

  return (
    <div className="space-y-5">
      {/* Status banner */}
      {submitState === 'success' && (
        <div className="rounded-lg px-3 py-2.5 bg-green-900/40 border border-green-700 text-green-300 text-sm">
          ✓ Report submitted
        </div>
      )}
      {submitState === 'queued' && (
        <div className="rounded-lg px-3 py-2.5 bg-yellow-900/40 border border-yellow-700 text-yellow-300 text-sm">
          📶 Saved offline — will sync when connected
        </div>
      )}

      {/* SOS shortcuts */}
      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => quickFill('trapped_person')}
          className="flex items-center justify-center gap-1.5 py-3 rounded-lg bg-red-900/60 border border-red-700 text-red-200 text-sm font-semibold hover:bg-red-900 transition-colors active:scale-95"
        >
          🆘 Trapped Person
        </button>
        <button
          type="button"
          onClick={() => quickFill('medical_emergency')}
          className="flex items-center justify-center gap-1.5 py-3 rounded-lg bg-red-900/60 border border-red-700 text-red-200 text-sm font-semibold hover:bg-red-900 transition-colors active:scale-95"
        >
          🏥 Medical Need
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Category */}
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-2">
            Category <span className="text-red-400">*</span>
          </label>
          <div className="grid grid-cols-2 gap-2">
            {CATEGORIES.map((c) => (
              <button
                key={c.value}
                type="button"
                onClick={() => set('category', c.value)}
                className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-left transition-colors ${
                  form.category === c.value
                    ? 'border-blue-500 bg-blue-900/40 text-white'
                    : 'border-gray-700 bg-gray-800 text-gray-300 hover:border-gray-500'
                }`}
              >
                <span className="text-base">{c.icon}</span>
                <span className="text-xs leading-tight">{c.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Urgency */}
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-2">
            Urgency <span className="text-red-400">*</span>
          </label>
          <div className="grid grid-cols-4 gap-2">
            {URGENCIES.map((u) => (
              <button
                key={u.value}
                type="button"
                onClick={() => set('urgency', u.value)}
                className={`py-2 rounded-lg border text-xs font-semibold transition-colors ${
                  form.urgency === u.value
                    ? u.active
                    : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-500'
                }`}
              >
                {u.label}
              </button>
            ))}
          </div>
        </div>

        {/* Location */}
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-2">
            Location <span className="text-red-400">*</span>
          </label>
          <button
            type="button"
            onClick={geolocate}
            disabled={geoStatus === 'loading'}
            className={`w-full py-2.5 rounded-lg border text-sm transition-colors mb-2 disabled:opacity-50 ${
              geoStatus === 'done'
                ? 'border-green-600 bg-green-900/30 text-green-300'
                : 'border-gray-700 bg-gray-800 text-gray-300 hover:border-blue-500'
            }`}
          >
            {geoStatus === 'loading'
              ? '…locating'
              : geoStatus === 'done'
              ? '✓ GPS captured — tap to refresh'
              : '📍 Use GPS location'}
          </button>
          {geoStatus === 'error' && (
            <p className="text-xs text-yellow-400 mb-2">GPS unavailable — enter manually</p>
          )}
          <div className="grid grid-cols-2 gap-2">
            <input
              type="number"
              step="any"
              placeholder="Latitude"
              value={form.lat}
              onChange={(e) => set('lat', e.target.value)}
              className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
            <input
              type="number"
              step="any"
              placeholder="Longitude"
              value={form.lng}
              onChange={(e) => set('lng', e.target.value)}
              className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        {/* Description */}
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-2">Description</label>
          <textarea
            rows={3}
            placeholder="Brief situation description…"
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
            className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 resize-none"
          />
        </div>

        {/* Optional fields */}
        <details>
          <summary className="text-xs text-gray-500 cursor-pointer select-none">
            Optional details ›
          </summary>
          <div className="mt-3 space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Water depth (m)</label>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  placeholder="0.0"
                  value={form.waterDepth}
                  onChange={(e) => set('waterDepth', e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">People affected</label>
                <input
                  type="number"
                  min="0"
                  placeholder="0"
                  value={form.peopleCount}
                  onChange={(e) => set('peopleCount', e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Photo URL</label>
              <input
                type="url"
                placeholder="https://…"
                value={form.photoUrl}
                onChange={(e) => set('photoUrl', e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>
        </details>

        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full py-3 rounded-lg bg-blue-600 text-white font-semibold text-sm disabled:opacity-40 disabled:cursor-not-allowed hover:bg-blue-500 active:scale-[0.98] transition-all"
        >
          {mutation.isPending ? 'Submitting…' : 'Submit Report'}
        </button>
      </form>
    </div>
  )
}
