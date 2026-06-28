import { sqliteTable, text, real, index } from 'drizzle-orm/sqlite-core';
import { ulidPk, nowMs, updatedAt, visibility, reviewStatus } from './columns';
import { orgId } from './orgs';

export const sciFiOutputs = sqliteTable('scifi_outputs', {
  id: ulidPk(),
  orgId: orgId(),
  incidentId: text('incident_id'),
  featureType: text('feature_type', {
    enum: ['digital_twin', 'ai_plan', 'hyperlocal_risk', 'voice_briefing', 'drone_swarm', 'auto_briefing', 'voice_command', 'ar_export', 'wearable', 'sensor_fusion', 'memory_graph', 'ai_debate', 'ethical_review', 'contradiction_detect', 'missing_advisor'],
  }).notNull(),
  output: text('output', { mode: 'json' }).$type<unknown>(),
  confidence: real('confidence'),
  citations: text('citations', { mode: 'json' }).$type<string[]>(),
  visibility: visibility(),
  reviewStatus: reviewStatus(),
  createdAt: nowMs(),
  updatedAt: updatedAt(),
}, (t) => ({
  scifiOrgIdx: index('idx_scifi_outputs_org').on(t.orgId),
  scifiFeatureIdx: index('idx_scifi_outputs_feature').on(t.featureType),
}));
