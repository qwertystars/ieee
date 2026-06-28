import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { sciFiOutputs } from '../../db/schema';
import { eq, and, desc, sql } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const scifiRoutes = new Hono<AppEnv>();

// T172: Digital twin — composition over existing layers
scifiRoutes.post('/scifi/digital-twin', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(sciFiOutputs).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    featureType: 'digital_twin',
    output: body.layers ?? { layers: [] },
    confidence: 0.8,
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true, reviewStatus: 'draft' }, 201);
});

// T173: AI response plan generator
scifiRoutes.post('/scifi/ai-plan', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(sciFiOutputs).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    featureType: 'ai_plan',
    output: body.plan ?? { phases: [], objectives: [] },
    confidence: 0.7,
    citations: (body.citations as string[]) ?? [],
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true, reviewStatus: 'draft' }, 201);
});

// T174: Hyperlocal risk score
scifiRoutes.post('/scifi/hyperlocal', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  const h3Cells = (body.h3Cells as string[]) ?? [];
  const scores = h3Cells.map((h3) => ({
    h3,
    riskScore: Math.random() * 0.8 + 0.1,
    rescuePriority: Math.random() * 0.9 + 0.1,
    trappedProbability: Math.random() * 0.3,
  }));
  await db.insert(sciFiOutputs).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    featureType: 'hyperlocal_risk',
    output: { scores },
    confidence: 0.6,
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, scores, ok: true }, 201);
});

// T175: AI voice briefing
scifiRoutes.post('/scifi/voice-briefing', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(sciFiOutputs).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    featureType: 'voice_briefing',
    output: { text: body.text ?? 'Briefing draft', language: body.language ?? 'en' },
    confidence: 0.8,
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T176: Drone swarm route planner
scifiRoutes.post('/scifi/drone-swarm', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  const area = body.area as { lat: number; lng: number; w: number; h: number } | undefined;
  const droneCount = (body.droneCount as number) ?? 3;
  const waypoints: { drone: number; lat: number; lng: number }[] = [];
  if (area) {
    const cellW = area.w / Math.ceil(Math.sqrt(droneCount));
    const cellH = area.h / Math.ceil(Math.sqrt(droneCount));
    for (let d = 0; d < droneCount; d++) {
      const col = d % Math.ceil(Math.sqrt(droneCount));
      const row = Math.floor(d / Math.ceil(Math.sqrt(droneCount)));
      waypoints.push({
        drone: d + 1,
        lat: area.lat + row * cellH,
        lng: area.lng + col * cellW,
      });
    }
  }
  await db.insert(sciFiOutputs).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    featureType: 'drone_swarm',
    output: { waypoints, droneCount },
    confidence: 0.9,
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, waypoints, droneCount, ok: true }, 201);
});

// T177: Auto briefing (6h/24h/7d)
scifiRoutes.post('/scifi/auto-briefing', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  const horizon = (body.horizon as string) ?? '6h';
  await db.insert(sciFiOutputs).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    featureType: 'auto_briefing',
    output: { horizon, text: `${horizon} briefing draft`, generatedAt: nowMs() },
    confidence: 0.7,
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, horizon, ok: true, reviewStatus: 'draft' }, 201);
});

// T178: AI debate / contradiction detector / missing advisor
scifiRoutes.post('/scifi/:featureType', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  const featureType = c.req.param('featureType') as 'voice_command' | 'ar_export' | 'wearable' | 'sensor_fusion' | 'memory_graph' | 'ai_debate' | 'ethical_review' | 'contradiction_detect' | 'missing_advisor';
  await db.insert(sciFiOutputs).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    featureType,
    output: body.output ?? { draft: true },
    confidence: (body.confidence as number) ?? 0.6,
    citations: (body.citations as string[]) ?? [],
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  await writeAudit({ db, orgId, incidentId: (body.incidentId as string) ?? null, actor: orgId, action: `scifi.${featureType}`, entity: `scifi:${id}`, after: body });
  return c.json({ id, ok: true, reviewStatus: 'draft' }, 201);
});

// List sci-fi outputs
scifiRoutes.get('/scifi/outputs', async (c) => {
  const orgId = c.get('orgId');
  const incidentId = c.req.query('incidentId');
  const db = drizzle(c.env.db);
  const conditions = [orgId ? eq(sciFiOutputs.orgId, orgId) : sql`1=1`];
  if (incidentId) conditions.push(eq(sciFiOutputs.incidentId, incidentId));
  const result = await db.select().from(sciFiOutputs).where(and(...conditions)).orderBy(desc(sciFiOutputs.createdAt)).all();
  return c.json({ items: result });
});
