import React from 'react'
import type { PriorityLevel, Urgency } from '../types'

const LEVEL_STYLES: Record<string, string> = {
  critical: 'bg-red-600 text-white',
  high: 'bg-orange-500 text-white',
  medium: 'bg-yellow-500 text-gray-900',
  low: 'bg-green-600 text-white',
  monitoring: 'bg-blue-500 text-white',
  unknown: 'bg-gray-600 text-white',
}

interface Props {
  level: PriorityLevel | Urgency
  className?: string
}

export default function PriorityBadge({ level, className = '' }: Props) {
  const style = LEVEL_STYLES[level] ?? LEVEL_STYLES['unknown']
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-bold uppercase tracking-wide ${style} ${className}`}>
      {level}
    </span>
  )
}
