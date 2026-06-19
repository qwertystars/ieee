import { drizzle } from 'drizzle-orm/d1';
import { events } from '../db/schema';
import { eq, desc } from 'drizzle-orm';
import { ulid, nowMs } from './ulid';

type Db = ReturnType<typeof drizzle>;

interface AuditInput {
  db: Db;
  orgId: string;
  incidentId?: string | null;
  actor: string;
  action: string;
  entity: string;
  before?: unknown;
  after?: unknown;
}

/**
 * Append an audit event to the hash-chained events table.
 * FEATURES.md:40 — hash = sha256(prev_hash ‖ payload), append-only, tamper-evident.
 *
 * @returns the created event row with its hash
 */
export async function writeAudit(input: AuditInput): Promise<{ id: string; hash: string; prevHash: string }> {
  const { db, orgId, incidentId, actor, action, entity, before, after } = input;
  const id = ulid();
  const ts = nowMs();

  const lastEvent = await db
    .select({ hash: events.hash })
    .from(events)
    .where(eq(events.orgId, orgId))
    .orderBy(desc(events.ts))
    .limit(1)
    .all();

  const prevHash = lastEvent[0]?.hash ?? '0000000000000000000000000000000000000000000000000000000000000000';

  const payload = JSON.stringify({ id, orgId, incidentId, actor, action, entity, before, after, ts, prevHash });
  const hash = await sha256(prevHash + payload);

  await db.insert(events).values({
    id,
    orgId,
    incidentId: incidentId ?? null,
    actor,
    action,
    entity,
    before: before ? JSON.stringify(before) : null,
    after: after ? JSON.stringify(after) : null,
    ts,
    prevHash,
    hash,
  });

  return { id, hash, prevHash };
}

/**
 * Verify the hash-chain integrity of the audit log for a given org.
 * FEATURES.md:40 — tamper detection: if any row is modified, verifyChain returns false.
 *
 * @returns { valid: boolean; brokenAt?: string } — index of first tampered row
 */
export async function verifyChain(db: Db, orgId: string): Promise<{ valid: boolean; brokenAt?: string }> {
  const rows = await db
    .select()
    .from(events)
    .where(eq(events.orgId, orgId))
    .orderBy(events.ts)
    .all();

  let expectedPrev = '0000000000000000000000000000000000000000000000000000000000000000';

  for (const row of rows) {
    if (row.prevHash !== expectedPrev) {
      return { valid: false, brokenAt: row.id };
    }

    const beforeVal = row.before ? JSON.parse(row.before as string) : undefined;
    const afterVal = row.after ? JSON.parse(row.after as string) : undefined;

    const payload = JSON.stringify({
      id: row.id,
      orgId: row.orgId,
      incidentId: row.incidentId,
      actor: row.actor,
      action: row.action,
      entity: row.entity,
      before: beforeVal,
      after: afterVal,
      ts: row.ts,
      prevHash: row.prevHash,
    });

    const computedHash = await sha256(row.prevHash + payload);
    if (computedHash !== row.hash) {
      return { valid: false, brokenAt: row.id };
    }

    expectedPrev = row.hash;
  }

  return { valid: true };
}

async function sha256(data: string): Promise<string> {
  const encoder = new TextEncoder();
  const buffer = encoder.encode(data);
  const digest = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

export { sha256 };
