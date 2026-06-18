// Displays confidence score + data age in a compact badge (DESIGN §12)

import React from 'react'
import { formatConfidence, formatRelative } from '../lib/format'

interface Props {
  confidence: number
  updatedAt: string
  className?: string
}

export default function ConfidenceBadge({ confidence, updatedAt, className = '' }: Props) {
  const pct = Math.round(confidence * 100)
  const color =
    pct >= 80 ? 'text-green-400' : pct >= 50 ? 'text-yellow-400' : 'text-red-400'

  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-mono text-gray-400 ${className}`}>
      <span className={`font-semibold ${color}`}>{formatConfidence(confidence)}</span>
      <span className="text-gray-600">·</span>
      <span>{formatRelative(updatedAt)}</span>
    </span>
  )
}
