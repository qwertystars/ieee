import type { Env } from '../index';
import { drizzle } from 'drizzle-orm/d1';
import { mapLayers, incidentNotes } from '../db/schema';
import { ulid, nowMs } from './ulid';
import { writeAudit } from './audit';

export async function onIncidentCreate(env: Env, incidentId: string, orgId: string): Promise<void> {
  const db = drizzle(env.db);

  await db.insert(incidentNotes).values({
    id: ulid(), orgId, incidentId,
    authorId: 'system', body: 'AI Summary (draft): Incident created. Summary pending review.', createdAt: nowMs(),
  });

  await db.insert(incidentNotes).values({
    id: ulid(), orgId, incidentId,
    authorId: 'system', body: 'Response Checklist (draft): 1. Assess situation 2. Activate ICS 3. Establish command 4. Brief teams 5. Begin operations', createdAt: nowMs(),
  });

  await db.insert(incidentNotes).values({
    id: ulid(), orgId, incidentId,
    authorId: 'system', body: 'Operational Period #1 (draft): Objectives TBD by Incident Commander', createdAt: nowMs(),
  });

  const defaultLayers = ['satellite', 'street', 'terrain', 'dark'];
  for (let i = 0; i < defaultLayers.length; i++) {
    await db.insert(mapLayers).values({
      id: ulid(), orgId, incidentId, name: defaultLayers[i]!,
      kind: 'base', source: 'pmtiles', style: { type: defaultLayers[i] },
      visibility: 'internal', reviewStatus: 'draft', sort: i, version: 1,
      createdAt: nowMs(), updatedAt: nowMs(),
    });
  }

  await db.insert(incidentNotes).values({
    id: ulid(), orgId, incidentId,
    authorId: 'system', body: 'Public Alert (draft): [ALERT TEXT PENDING REVIEW] Do not publish without approval.', createdAt: nowMs(),
  });

  await db.insert(incidentNotes).values({
    id: ulid(), orgId, incidentId,
    authorId: 'system', body: 'ICS-201 Briefing (draft): Incident Briefing form pending completion by IC.', createdAt: nowMs(),
  });

  await writeAudit({ db, orgId, actor: 'system', action: 'incident.auto_seed', entity: `incident:${incidentId}`, after: { drafts: 6 } });
}
