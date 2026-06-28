import type { Env } from '../index';
import { drizzle } from 'drizzle-orm/d1';
import { incidentReports } from '../db/schema';
import { ulid, nowMs } from '../lib/ulid';
import { checkIdempotency, recordIdempotency } from '../lib/idempotency';
import { writeAudit } from '../lib/audit';

// Queue consumers for all 7 queues declared in wrangler.jsonc.
// Each consumer is idempotent (checks idempotency table) and writes audit entries.

type MessageBody = Record<string, unknown>;

export async function ingestConsumer(batch: MessageBatch<MessageBody>, env: Env): Promise<void> {
  const db = drizzle(env.db);
  for (const msg of batch.messages) {
    const body = msg.body;
    const idemKey = (body.__idempotencyKey as string) ?? msg.id;

    const existing = await checkIdempotency(db, 'ingest', idemKey);
    if (existing) { msg.ack(); continue; }

    try {
      const incidentId = body.incidentId as string;
      const orgId = body.orgId as string;
      const reportCategory = (body.reportCategory as string) ?? 'unknown';
      const geometry = (body.geometry as string) ?? JSON.stringify({ type: 'Point', coordinates: [0, 0] });
      const reporterType = (body.reporterType as 'citizen' | 'field_responder' | 'sensor' | 'official') ?? 'sensor';

      const id = ulid();
      await db.insert(incidentReports).values({
        id, orgId, incidentId,
        reporterType,
        reportCategory,
        description: (body.description as string) ?? null,
        geometry,
        photoUrl: (body.photoUrl as string) ?? null,
        urgency: ((body.urgency as string) ?? 'medium') as 'low' | 'medium' | 'high' | 'critical',
        verificationStatus: 'unverified',
        confidenceScore: 0.3,
        visibility: 'internal',
        reviewStatus: 'draft',
        createdAt: nowMs(), updatedAt: nowMs(),
      });

      await writeAudit({ db, orgId, incidentId, actor: 'ingest-queue', action: 'report.ingest', entity: `report:${id}`, after: body });
      await recordIdempotency(db, 'ingest', idemKey, { id });
      msg.ack();
    } catch (e) {
      msg.retry();
    }
  }
}

export async function alertConsumer(batch: MessageBatch<MessageBody>, env: Env): Promise<void> {
  const db = drizzle(env.db);
  for (const msg of batch.messages) {
    const body = msg.body;
    const idemKey = (body.__idempotencyKey as string) ?? msg.id;

    const existing = await checkIdempotency(db, 'alert', idemKey);
    if (existing) { msg.ack(); continue; }

    try {
      // Alert queue handles both alert creation and fanout
      const type = body.type as string;
      const orgId = (body.orgId as string) ?? 'system';
      const incidentId = body.incidentId as string;

      if (type === 'task_sla_breached') {
        // Escalation alert — could fan out to notifications, SMS, etc.
        await writeAudit({
          db, orgId, incidentId,
          actor: 'alert-queue',
          action: 'alert.task_sla_breached',
          entity: `task:${body.taskId}`,
          after: { escalationLevel: body.escalationLevel },
        });
      }

      await recordIdempotency(db, 'alert', idemKey, { processed: true });
      msg.ack();
    } catch (e) {
      msg.retry();
    }
  }
}

export async function aiConsumer(batch: MessageBatch<MessageBody>, env: Env): Promise<void> {
  const db = drizzle(env.db);
  for (const msg of batch.messages) {
    const body = msg.body;
    const idemKey = (body.__idempotencyKey as string) ?? msg.id;

    const existing = await checkIdempotency(db, 'ai', idemKey);
    if (existing) { msg.ack(); continue; }

    try {
      // AI queue: process embeddings, generate summaries, etc.
      // All AI output lands as review_status=draft per AGENTS.md
      const orgId = (body.orgId as string) ?? 'system';
      const incidentId = body.incidentId as string;
      const task = body.task as string;

      await writeAudit({
        db, orgId, incidentId,
        actor: 'ai-queue',
        action: `ai.${task}`,
        entity: `incident:${incidentId}`,
        after: { status: 'draft', task },
      });

      await recordIdempotency(db, 'ai', idemKey, { processed: true });
      msg.ack();
    } catch (e) {
      msg.retry();
    }
  }
}

export async function droneConsumer(batch: MessageBatch<MessageBody>, env: Env): Promise<void> {
  const db = drizzle(env.db);
  for (const msg of batch.messages) {
    const body = msg.body;
    const idemKey = (body.__idempotencyKey as string) ?? msg.id;

    const existing = await checkIdempotency(db, 'drone', idemKey);
    if (existing) { msg.ack(); continue; }

    try {
      const orgId = (body.orgId as string) ?? 'system';
      const incidentId = body.incidentId as string;

      await writeAudit({
        db, orgId, incidentId,
        actor: 'drone-queue',
        action: 'drone.survey',
        entity: `incident:${incidentId}`,
        after: { missionId: body.missionId },
      });

      await recordIdempotency(db, 'drone', idemKey, { processed: true });
      msg.ack();
    } catch (e) {
      msg.retry();
    }
  }
}

export async function geocodeConsumer(batch: MessageBatch<MessageBody>, env: Env): Promise<void> {
  const db = drizzle(env.db);
  for (const msg of batch.messages) {
    const body = msg.body;
    const idemKey = (body.__idempotencyKey as string) ?? msg.id;

    const existing = await checkIdempotency(db, 'geocode', idemKey);
    if (existing) { msg.ack(); continue; }

    try {
      const address = body.address as string;
      if (address) {
        const resp = await fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(address)}&format=json&limit=1`, {
          headers: { 'User-Agent': 'disaster-response-platform/1.0' },
        });
        const data = await resp.json() as Array<{ lat: string; lon: string }>;
        if (data[0]) {
          await env.cache.put(`geocode:${idemKey}`, JSON.stringify({
            lat: parseFloat(data[0].lat),
            lng: parseFloat(data[0].lon),
          }), { expirationTtl: 86400 });
        }
      }

      await recordIdempotency(db, 'geocode', idemKey, { processed: true });
      msg.ack();
    } catch (e) {
      msg.retry();
    }
  }
}

export async function webhookIngestConsumer(batch: MessageBatch<MessageBody>, env: Env): Promise<void> {
  const db = drizzle(env.db);
  for (const msg of batch.messages) {
    const body = msg.body;
    const idemKey = (body.__idempotencyKey as string) ?? msg.id;
    const deliveryId = (body.deliveryId as string) ?? idemKey;

    const existing = await checkIdempotency(db, 'webhook-ingest', deliveryId);
    if (existing) { msg.ack(); continue; }

    try {
      const orgId = (body.orgId as string) ?? 'system';
      const source = (body.source as string) ?? 'unknown';

      await writeAudit({
        db, orgId,
        actor: 'webhook-ingest-queue',
        action: 'webhook.received',
        entity: `webhook:${source}`,
        after: { deliveryId, source },
      });

      await recordIdempotency(db, 'webhook-ingest', deliveryId, { processed: true });
      msg.ack();
    } catch (e) {
      msg.retry();
    }
  }
}

export async function webhookDeliveryConsumer(batch: MessageBatch<MessageBody>, env: Env): Promise<void> {
  const db = drizzle(env.db);
  for (const msg of batch.messages) {
    const body = msg.body;
    const idemKey = (body.__idempotencyKey as string) ?? msg.id;
    const deliveryId = (body.deliveryId as string) ?? idemKey;

    const existing = await checkIdempotency(db, 'webhook-delivery', deliveryId);
    if (existing) { msg.ack(); continue; }

    try {
      const url = body.url as string;
      const payload = body.payload as Record<string, unknown>;

      if (url) {
        const resp = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });

        await writeAudit({
          db,
          orgId: (body.orgId as string) ?? 'system',
          actor: 'webhook-delivery-queue',
          action: 'webhook.delivered',
          entity: `webhook:${deliveryId}`,
          after: { status: resp.status, url },
        });
      }

      await recordIdempotency(db, 'webhook-delivery', deliveryId, { delivered: true });
      msg.ack();
    } catch (e) {
      msg.retry();
    }
  }
}
