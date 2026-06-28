import type { Env } from '../index';
import { drizzle } from 'drizzle-orm/d1';
import { incidents, disasterEvents } from '../db/schema';
import { eq } from 'drizzle-orm';
import { writeAudit } from '../lib/audit';

export async function healthCheckCron(env: Env): Promise<void> {
  const db = drizzle(env.db);

  try {
    await env.db.prepare('SELECT 1').first();

    const activeIncidents = await db.select().from(incidents)
      .where(eq(incidents.status, 'active')).all();

    await env.cache.put('cron:health:lastRun', JSON.stringify({
      ts: Date.now(),
      activeIncidents: activeIncidents.length,
    }), { expirationTtl: 600 });
  } catch (e) {
    console.error('healthCheckCron failed:', e);
  }
}

export async function hourlyRetentionCron(env: Env): Promise<void> {
  const db = drizzle(env.db);

  try {
    const now = Date.now();
    await env.db.prepare('DELETE FROM sessions WHERE expires_at < ?').bind(now).run();

    const cutoff = now - 7 * 24 * 60 * 60 * 1000;
    await env.db.prepare('DELETE FROM idempotency WHERE created_at < ?').bind(cutoff).run();

    await writeAudit({
      db,
      orgId: 'system',
      actor: 'cron:hourly-retention',
      action: 'retention.cleanup',
      entity: 'system',
      after: { cutoff },
    });
  } catch (e) {
    console.error('hourlyRetentionCron failed:', e);
  }
}

export async function dailyBackupCron(env: Env): Promise<void> {
  const db = drizzle(env.db);

  try {
    const activeEvents = await db.select().from(disasterEvents)
      .where(eq(disasterEvents.status, 'active')).all();

    const snapshot = {
      ts: Date.now(),
      activeEvents: activeEvents.length,
      events: activeEvents.map((e) => ({ id: e.id, name: e.name, type: e.type })),
    };

    const key = `backups/daily-${new Date().toISOString().slice(0, 10)}.json`;
    await env.exports.put(key, JSON.stringify(snapshot, null, 2), {
      customMetadata: { type: 'daily-backup', createdAt: String(Date.now()) },
    });

    await writeAudit({
      db,
      orgId: 'system',
      actor: 'cron:daily-backup',
      action: 'backup.snapshot',
      entity: 'system',
      after: { key, events: activeEvents.length },
    });
  } catch (e) {
    console.error('dailyBackupCron failed:', e);
  }
}
