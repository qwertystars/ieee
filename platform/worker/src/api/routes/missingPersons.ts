import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { missingPersons, foundPersons, missingPersonNotes, reunificationCases } from '../../db/schema';
import { eq, and, desc, sql } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';
import { jaroWinkler } from '../../lib/dedupe/tasks';

export const missingPersonRoutes = new Hono<AppEnv>();

// T71: Create missing person report
missingPersonRoutes.post('/missing-persons', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);

  const fullName = (body.fullName as string) ?? 'Unknown';
  const fullNameSplit = fullName.toLowerCase().trim().replace(/\s+/g, ' ');

  await db.insert(missingPersons).values({
    id, orgId,
    incidentId: body.incidentId as string,
    fullName,
    fullNameSplit,
    ageGroup: ((body.ageGroup as string) ?? 'unknown') as 'child' | 'adult' | 'senior' | 'unknown',
    ageExact: (body.ageExact as number) ?? null,
    sex: ((body.sex as string) ?? 'unknown') as 'male' | 'female' | 'other' | 'unknown',
    photoR2Key: (body.photoR2Key as string) ?? null,
    lastKnownLocation: (body.lastKnownLocation as string) ?? null,
    lastSeenAt: (body.lastSeenAt as number) ?? null,
    medicalCondition: (body.medicalCondition as string) ?? null,
    vulnerability: ((body.vulnerability as string) ?? 'none') as 'none' | 'medical' | 'disability' | 'child' | 'elderly' | 'pregnant',
    description: (body.description as string) ?? null,
    contactName: (body.contactName as string) ?? null,
    contactPhone: (body.contactPhone as string) ?? null,
    status: 'missing',
    pfifId: `PFIF-${id}`,
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });

  await writeAudit({ db, orgId, incidentId: body.incidentId as string, actor: orgId, action: 'missing_person.created', entity: `missing_person:${id}`, after: body });
  return c.json({ id, pfifId: `PFIF-${id}`, ok: true }, 201);
});

// T71: List missing persons
missingPersonRoutes.get('/missing-persons', async (c) => {
  const orgId = c.get('orgId');
  const incidentId = c.req.query('incidentId');
  const db = drizzle(c.env.db);
  const conditions = [orgId ? eq(missingPersons.orgId, orgId) : sql`1=1`];
  if (incidentId) conditions.push(eq(missingPersons.incidentId, incidentId));
  const result = await db.select().from(missingPersons).where(and(...conditions)).orderBy(desc(missingPersons.createdAt)).all();
  return c.json({ items: result });
});

// T71: Create found person report
missingPersonRoutes.post('/found-persons', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);

  const fullName = (body.fullName as string) ?? 'Unknown';
  const fullNameSplit = fullName.toLowerCase().trim().replace(/\s+/g, ' ');

  await db.insert(foundPersons).values({
    id, orgId,
    incidentId: body.incidentId as string,
    fullName,
    fullNameSplit,
    ageGroup: ((body.ageGroup as string) ?? 'unknown') as 'child' | 'adult' | 'senior' | 'unknown',
    sex: ((body.sex as string) ?? 'unknown') as 'male' | 'female' | 'other' | 'unknown',
    photoR2Key: (body.photoR2Key as string) ?? null,
    foundLocation: (body.foundLocation as string) ?? null,
    foundAt: (body.foundAt as number) ?? nowMs(),
    source: ((body.source as string) ?? 'shelter') as 'shelter' | 'hospital' | 'field' | 'hotline' | 'public',
    sourceRef: (body.sourceRef as string) ?? null,
    shelterCheckinId: (body.shelterCheckinId as string) ?? null,
    pfifId: `PFIF-${id}`,
    matchStatus: 'pending',
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });

  // Auto-suggest matches against missing persons
  const missing = await db.select().from(missingPersons)
    .where(and(eq(missingPersons.incidentId, body.incidentId as string), eq(missingPersons.status, 'missing'))).all();

  const suggestions: { missingId: string; score: number }[] = [];
  for (const m of missing) {
    const score = jaroWinkler(fullNameSplit, m.fullNameSplit ?? '');
    // Boost score if age group + sex match
    let adjustedScore = score;
    if (m.ageGroup === ((body.ageGroup as string) ?? 'unknown')) adjustedScore += 0.1;
    if (m.sex === ((body.sex as string) ?? 'unknown')) adjustedScore += 0.05;
    if (adjustedScore > 0.6) suggestions.push({ missingId: m.id, score: Math.min(adjustedScore, 1) });
  }

  if (suggestions.length > 0) {
    const best = suggestions.sort((a, b) => b.score - a.score)[0]!;
    await db.update(foundPersons).set({ matchedMissingId: best.missingId, matchScore: best.score, matchStatus: 'suggested' }).where(eq(foundPersons.id, id));
  }

  await writeAudit({ db, orgId, incidentId: body.incidentId as string, actor: orgId, action: 'found_person.created', entity: `found_person:${id}`, after: body });
  return c.json({ id, pfifId: `PFIF-${id}`, ok: true, suggestions }, 201);
});

// T72: List found persons
missingPersonRoutes.get('/found-persons', async (c) => {
  const orgId = c.get('orgId');
  const incidentId = c.req.query('incidentId');
  const db = drizzle(c.env.db);
  const conditions = [orgId ? eq(foundPersons.orgId, orgId) : sql`1=1`];
  if (incidentId) conditions.push(eq(foundPersons.incidentId, incidentId));
  const result = await db.select().from(foundPersons).where(and(...conditions)).orderBy(desc(foundPersons.createdAt)).all();
  return c.json({ items: result });
});

// T72: Approve a match
missingPersonRoutes.post('/found-persons/:id/approve-match', async (c) => {
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const found = await db.select().from(foundPersons).where(eq(foundPersons.id, c.req.param('id'))).limit(1).all();
  if (!found[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Found person not found', request_id: c.get('requestId') } }, 404);

  await db.update(foundPersons).set({ matchStatus: 'approved', updatedAt: nowMs() }).where(eq(foundPersons.id, found[0].id));

  // Create reunification case
  if (found[0].matchedMissingId) {
    const caseId = ulid();
    await db.insert(reunificationCases).values({
      id: caseId, orgId,
      incidentId: found[0].incidentId,
      missingPersonId: found[0].matchedMissingId,
      foundPersonId: found[0].id,
      status: 'initiated',
      createdAt: nowMs(), updatedAt: nowMs(),
    });
    await db.update(missingPersons).set({ status: 'found', updatedAt: nowMs() }).where(eq(missingPersons.id, found[0].matchedMissingId));
    await writeAudit({ db, orgId, incidentId: found[0].incidentId, actor: orgId, action: 'reunification.initiated', entity: `reunification:${caseId}`, after: { foundId: found[0].id, missingId: found[0].matchedMissingId } });
    return c.json({ ok: true, caseId });
  }

  return c.json({ ok: true });
});

// T72: Add case note
missingPersonRoutes.post('/missing-persons/:id/notes', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(missingPersonNotes).values({
    id, orgId,
    missingPersonId: c.req.param('id'),
    authorId: (body.authorId as string) ?? orgId,
    note: body.note as string,
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T73: Complete reunification
missingPersonRoutes.post('/reunification/:id/complete', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const rCase = await db.select().from(reunificationCases).where(eq(reunificationCases.id, c.req.param('id'))).limit(1).all();
  if (!rCase[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Reunification case not found', request_id: c.get('requestId') } }, 404);

  await db.update(reunificationCases).set({
    status: 'completed',
    approvedBy: (body.approvedBy as string) ?? orgId,
    approvedAt: nowMs(),
    safeAndWell: (body.safeAndWell as boolean) ?? true,
    updatedAt: nowMs(),
  }).where(eq(reunificationCases.id, rCase[0].id));

  if (rCase[0].missingPersonId) {
    await db.update(missingPersons).set({ status: 'reunited', updatedAt: nowMs() }).where(eq(missingPersons.id, rCase[0].missingPersonId));
  }

  await writeAudit({ db, orgId, incidentId: rCase[0].incidentId, actor: orgId, action: 'reunification.completed', entity: `reunification:${rCase[0].id}`, after: body });
  return c.json({ ok: true, status: 'completed' });
});

// T73: PFIF export (simplified JSON in PFIF format)
missingPersonRoutes.get('/pfif/export', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const missing = await db.select().from(missingPersons).where(orgId ? eq(missingPersons.orgId, orgId) : sql`1=1`).all();
  const found = await db.select().from(foundPersons).where(orgId ? eq(foundPersons.orgId, orgId) : sql`1=1`).all();

  const pfif = {
    pfif_version: '1.4',
    persons: [
      ...missing.map((m) => ({
        person_record_id: m.pfifId,
        entry_date: new Date(m.createdAt).toISOString(),
        author_name: 'system',
        full_name: m.fullName,
        sex: m.sex,
        age: m.ageExact,
        home_city: m.lastKnownLocation,
        photo: m.photoR2Key,
        note: m.description,
        source_date: m.lastSeenAt ? new Date(m.lastSeenAt).toISOString() : undefined,
      })),
      ...found.map((f) => ({
        note_record_id: f.pfifId,
        entry_date: new Date(f.createdAt).toISOString(),
        author_name: 'system',
        full_name: f.fullName,
        sex: f.sex,
        found_location: f.foundLocation,
        source_date: f.foundAt ? new Date(f.foundAt).toISOString() : undefined,
      })),
    ],
  };

  return c.json(pfif);
});
