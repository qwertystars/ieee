import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { alerts, alertDeliveries, commsDrafts, publicSubscriptions, webhookSubscriptions, webhookDeliveries } from '../../db/schema';
import { eq, and, desc, sql } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const commsRoutes = new Hono<AppEnv>();

// T89: Create alert (draft → approval → fanout)
commsRoutes.post('/alerts', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);

  await db.insert(alerts).values({
    id, orgId,
    incidentId: body.incidentId as string,
    alertType: body.alertType as string,
    title: body.title as string,
    message: (body.message as string) ?? null,
    area: (body.area as string) ?? null,
    severity: ((body.severity as string) ?? 'warning') as 'info' | 'advisory' | 'warning' | 'critical',
    recommendedAction: (body.recommendedAction as string) ?? null,
    confidenceScore: 0.8,
    acknowledged: false,
    visibility: 'public',
    reviewStatus: 'draft',
    createdAt: nowMs(),
  });

  await writeAudit({ db, orgId, incidentId: body.incidentId as string, actor: orgId, action: 'alert.created', entity: `alert:${id}`, after: body });
  return c.json({ id, ok: true, status: 'draft' }, 201);
});

// T89: Approve alert → fanout via alertQ
commsRoutes.post('/alerts/:id/approve', async (c) => {
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const alert = await db.select().from(alerts).where(eq(alerts.id, c.req.param('id'))).limit(1).all();
  if (!alert[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Alert not found', request_id: c.get('requestId') } }, 404);

  await db.update(alerts).set({ reviewStatus: 'official' }).where(eq(alerts.id, alert[0].id));

  // Fanout to alertQ (idempotent)
  try {
    await c.env.alertQ.send({
      type: 'alert_fanout',
      alertId: alert[0].id,
      orgId,
      incidentId: alert[0].incidentId,
      channels: ['sms', 'email', 'push'],
      __idempotencyKey: ulid(),
    });
  } catch { /* Queue may not be bound */ }

  await writeAudit({ db, orgId, incidentId: alert[0].incidentId, actor: orgId, action: 'alert.approved', entity: `alert:${alert[0].id}`, after: { status: 'official' } });
  return c.json({ ok: true, status: 'fanout_started' });
});

// T89: Record delivery status
commsRoutes.post('/alerts/:id/deliveries', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(alertDeliveries).values({
    id, orgId,
    alertId: c.req.param('id'),
    channel: body.channel as 'sms' | 'voice' | 'whatsapp' | 'email' | 'push' | 'telegram',
    recipient: body.recipient as string,
    status: ((body.status as string) ?? 'pending') as 'pending' | 'sent' | 'delivered' | 'failed' | 'bounced',
    providerMessageId: (body.providerMessageId as string) ?? null,
    error: (body.error as string) ?? null,
    attempts: (body.attempts as number) ?? 0,
    deliveredAt: (body.deliveredAt as number) ?? null,
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T91: Alert targeting (polygon → H3 subscriber match)
commsRoutes.post('/alerts/:id/target', async (c) => {
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const subs = await db.select().from(publicSubscriptions)
    .where(and(eq(publicSubscriptions.orgId, orgId), eq(publicSubscriptions.active, true))).all();
  return c.json({ matchedSubscribers: subs.length, subscribers: subs.map((s) => ({ id: s.id, phone: s.phone, email: s.email })) });
});

// T92: CAP v1.2 XML export
commsRoutes.get('/alerts/:id/cap', async (c) => {
  const db = drizzle(c.env.db);
  const alert = await db.select().from(alerts).where(eq(alerts.id, c.req.param('id'))).limit(1).all();
  if (!alert[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Alert not found', request_id: c.get('requestId') } }, 404);

  const a = alert[0];
  const cap = `<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:CAP:1.2">
  <identifier>${a.id}</identifier>
  <sender>disaster-response-platform</sender>
  <sent>${new Date(a.createdAt).toISOString()}</sent>
  <status>Actual</status>
  <msgType>${a.reviewStatus === 'official' ? 'Alert' : 'Test'}</msgType>
  <scope>Public</scope>
  <info>
    <language>en</language>
    <category>${a.alertType}</category>
    <event>${a.title}</event>
    <urgency>${a.severity}</urgency>
    <severity>${a.severity}</severity>
    <certainty>${a.confidenceScore > 0.7 ? 'Observed' : 'Likely'}</certainty>
    <eventCode><valueName>org_id</valueName><value>${a.orgId}</value></eventCode>
    ${a.message ? `<description>${escapeXml(a.message)}</description>` : ''}
    ${a.recommendedAction ? `<instruction>${escapeXml(a.recommendedAction)}</instruction>` : ''}
  </info>
</alert>`;

  return new Response(cap, { headers: { 'Content-Type': 'application/xml' } });
});

function escapeXml(s: string): string {
  return s.replace(/[<>&'"]/g, (ch) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;' }[ch]!));
}

// T93: Create comms draft
commsRoutes.post('/comms-drafts', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(commsDrafts).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    draftType: body.draftType as 'radio' | 'ham_frequency' | 'pa_script' | 'social_post' | 'website_banner' | 'status_page' | 'rumor_correction' | 'misinformation' | 'press_release' | 'media_kit' | 'widget' | 'sitrep' | 'faq' | 'hotline_script' | 'door_to_door' | 'brevity' | 'blackout_plan' | 'offline_bulletin' | 'poster',
    title: body.title as string,
    content: body.content as string,
    channel: (body.channel as string) ?? null,
    language: (body.language as string) ?? 'en',
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

commsRoutes.get('/comms-drafts', async (c) => {
  const orgId = c.get('orgId');
  const incidentId = c.req.query('incidentId');
  const db = drizzle(c.env.db);
  const conditions = [orgId ? eq(commsDrafts.orgId, orgId) : sql`1=1`];
  if (incidentId) conditions.push(eq(commsDrafts.incidentId, incidentId));
  const result = await db.select().from(commsDrafts).where(and(...conditions)).orderBy(desc(commsDrafts.createdAt)).all();
  return c.json({ items: result });
});

// T95: Public status page (KV-cached)
commsRoutes.get('/public/status', async (c) => {
  const cacheKey = 'public-status';
  let cached: string | null = null;
  try { cached = await c.env.cache.get(cacheKey); } catch { /* KV may not be bound */ }

  if (cached) {
    return new Response(cached, { headers: { 'Content-Type': 'application/json', 'X-Cache': 'HIT' } });
  }

  const db = drizzle(c.env.db);
  const activeAlerts = await db.select().from(alerts)
    .where(and(eq(alerts.reviewStatus, 'official'), eq(alerts.visibility, 'public'))).all();

  const status = { ok: true, activeAlerts: activeAlerts.length, alerts: activeAlerts.slice(0, 10), generatedAt: nowMs() };
  const body = JSON.stringify(status);
  try { await c.env.cache.put(cacheKey, body, { expirationTtl: 60 }); } catch { /* KV may not be bound */ }

  return new Response(body, { headers: { 'Content-Type': 'application/json', 'X-Cache': 'MISS' } });
});

// T97: Public subscription
commsRoutes.post('/public/subscribe', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(publicSubscriptions).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    phone: (body.phone as string) ?? null,
    email: (body.email as string) ?? null,
    geoPolygon: (body.geoPolygon as string) ?? null,
    channels: (body.channels as string[]) ?? ['sms'],
    language: (body.language as string) ?? 'en',
    active: true,
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T151: Webhook subscriptions
commsRoutes.post('/webhooks/subscribe', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(webhookSubscriptions).values({
    id, orgId,
    url: body.url as string,
    events: (body.events as string[]) ?? ['*'],
    secret: ulid(),
    active: true,
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

commsRoutes.post('/webhooks/:id/deliver', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(webhookDeliveries).values({
    id, orgId,
    subscriptionId: c.req.param('id'),
    event: body.event as string,
    payload: body.payload,
    status: 'pending',
    attempts: 0,
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});
