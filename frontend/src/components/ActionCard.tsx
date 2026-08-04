import { useState, type ReactNode } from 'react'
import type { Alert } from '../api/types'
import { ActionCardControls } from './ActionCardControls'

export interface ObservationRef {
  id: string
  label: string
}

export interface BenefitRange {
  low: number
  high: number
  unit: string
}

export interface Alternative {
  action: string
  failureProbability: number
}

export interface ActionCardData {
  id: string
  proposedAction: string
  operationalObjective: string
  benefitRange: BenefitRange
  timeSensitivity: string
  resourcesRequired: string[]
  primaryEvidence: ObservationRef[]
  contradictingEvidence: string
  assumptions: string[]
  confidence: number
  calibration: string
  alternatives: Alternative[]
  failureContingency: string
  equityImpact: string
}

export interface ActionCardProps {
  action: ActionCardData
  status?: string
  onApprove?: (id: string) => void
  onDismiss?: (id: string) => void
  onModify?: (id: string) => void
  onDispatchRequest?: (id: string) => void
  dispatchPending?: boolean
  onEvidenceClick?: (obsId: string) => void
}

/** Map a real API Alert to the ActionCard view model. */
export function alertToActionCard(alert: Alert): ActionCardData {
  const cv = alert.confidence_vector ?? {}
  const confidence = typeof cv.c === 'number' ? cv.c : 0.5
  const support = typeof cv.s === 'number' ? cv.s : undefined
  const supportPct = support !== undefined ? Math.round(support * 100) : null
  const confPct = Math.round(confidence * 100)
  return {
    id: alert.id,
    proposedAction: alert.recommended_action ?? alert.title,
    operationalObjective: alert.title,
    benefitRange: { low: 0, high: 0, unit: 'Not quantified' },
    timeSensitivity: alert.severity,
    resourcesRequired: alert.recommended_action
      ? [alert.recommended_action]
      : ['Not specified'],
    primaryEvidence: [{ id: alert.id, label: alert.message }],
    contradictingEvidence: alert.review_rationale ?? 'None identified in current data',
    assumptions: [`Based on ${alert.alert_type} alert data`],
    confidence,
    calibration: supportPct !== null
      ? `Support ${supportPct}%, Confidence ${confPct}%`
      : `Confidence ${confPct}%`,
    alternatives: [],
    failureContingency: 'Reassess when new data arrives',
    equityImpact: 'Not assessed in current data',
  }
}

function Section({ label, testId, children }: { label: string; testId: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5" data-testid={testId}>
      <span className="text-[10px] font-bold uppercase tracking-wider text-gray-500">{label}</span>
      <div className="text-xs text-gray-200">{children}</div>
    </div>
  )
}

export function ActionCard({ action, status, onApprove, onDismiss, onModify, onDispatchRequest, dispatchPending = false, onEvidenceClick }: ActionCardProps) {
  const [internalStatus, setInternalStatus] = useState(status ?? 'pending')
  const current = dispatchPending ? 'dispatch_pending' : status ?? internalStatus
  const isResolved = current === 'approved' || current === 'dismissed'

  const confidencePct = Math.round(action.confidence * 100)

  const handleApprove = () => {
    setInternalStatus('approved')
    onApprove?.(action.id)
  }
  const handleDismiss = () => {
    setInternalStatus('dismissed')
    onDismiss?.(action.id)
  }
  const handleModify = () => {
    setInternalStatus('modified')
    onModify?.(action.id)
  }
  const handleDispatchRequest = () => {
    setInternalStatus('dispatch_pending')
    onDispatchRequest?.(action.id)
  }

  return (
    <div
      data-testid="action-card"
      data-action-id={action.id}
      data-status={current}
      className="w-96 rounded-lg border border-gray-700 bg-gray-900/95 p-4 shadow-xl"
      role="article"
      aria-label={`Action card: ${action.proposedAction}`}
    >
      <div className="mb-3 flex items-start justify-between gap-2">
        <h3 className="text-sm font-bold text-gray-100" data-testid="proposed-action">
          {action.proposedAction}
        </h3>
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
          current === 'approved' ? 'bg-green-900 text-green-300' :
          current === 'dismissed' ? 'bg-red-900 text-red-300' :
          current === 'modified' ? 'bg-blue-900 text-blue-300' :
          'bg-gray-700 text-gray-300'
        }`} aria-label={`Status: ${current}`}>
          {current === 'dispatch_pending' ? 'dispatch pending' : current}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        <Section label="Operational Objective" testId="operational-objective">
          {action.operationalObjective}
        </Section>

        <Section label="Expected Benefit Range" testId="benefit-range-section">
          <span data-testid="benefit-range">
            [{action.benefitRange.low}, {action.benefitRange.high}] {action.benefitRange.unit}
          </span>
        </Section>

        <Section label="Time Sensitivity / Urgency" testId="time-sensitivity">
          {action.timeSensitivity}
        </Section>

        <Section label="Resources Required" testId="resources-required">
          <ul className="flex flex-wrap gap-1">
            {action.resourcesRequired.map((r, i) => (
              <li key={i} className="rounded bg-gray-800 px-1.5 py-0.5 text-[11px] text-gray-300">
                {r}
              </li>
            ))}
          </ul>
        </Section>

        <Section label="Supporting Evidence" testId="primary-evidence">
          <ul className="flex flex-col gap-0.5">
            {action.primaryEvidence.map(obs => (
              <li key={obs.id}>
                <button
                  data-testid={`evidence-link-${obs.id}`}
                  onClick={() => onEvidenceClick?.(obs.id)}
                  className="text-left text-blue-400 underline hover:text-blue-300"
                  aria-label={`Evidence: ${obs.label}`}
                >
                  {obs.label}
                </button>
              </li>
            ))}
          </ul>
        </Section>

        <Section label="Contradicting Evidence" testId="contradicting-evidence">
          {action.contradictingEvidence}
        </Section>

        <Section label="Assumptions" testId="assumptions">
          <ul className="flex flex-col gap-0.5">
            {action.assumptions.map((a, i) => (
              <li key={i} className="text-gray-300">• {a}</li>
            ))}
          </ul>
        </Section>

        <Section label="Uncertainty / Calibration" testId="confidence-calibration">
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-20 rounded-full bg-gray-700" role="progressbar" aria-valuenow={confidencePct} aria-valuemin={0} aria-valuemax={100}>
              <div className="h-1.5 rounded-full bg-blue-500" style={{ width: `${confidencePct}%` }} />
            </div>
            <span data-testid="confidence-value">{confidencePct}%</span>
            <span className="text-[11px] text-gray-400">{action.calibration}</span>
          </div>
        </Section>

        <Section label="Alternative Actions" testId="alternative-actions">
          {action.alternatives.length === 0 ? (
            <span className="text-gray-500">None proposed</span>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {action.alternatives.map((alt, i) => (
                <li key={i} className="text-gray-300">
                  • {alt.action} ({Math.round(alt.failureProbability * 100)}% failure probability)
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section label="Failure Contingency" testId="failure-contingency">
          {action.failureContingency}
        </Section>

        <Section label="Equity Impact" testId="equity-impact">
          {action.equityImpact}
        </Section>
      </div>

      <ActionCardControls
        actionLabel={action.proposedAction}
        isResolved={isResolved}
        dispatchPending={current === 'dispatch_pending'}
        onApprove={handleApprove}
        onDismiss={handleDismiss}
        onModify={handleModify}
        onDispatchRequest={handleDispatchRequest}
      />
    </div>
  )
}

export default ActionCard
