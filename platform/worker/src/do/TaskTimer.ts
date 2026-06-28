import type { Env } from '../index';

// T49: TaskTimer DO — per-task SLA alarm + escalation.
// Manages a timer for a task; when the SLA window elapses, escalates via alarm.
// Storage: taskId, slaMs, startedAt, escalationLevel, status.

interface TaskTimerState {
  taskId: string;
  slaMs: number;
  startedAt: number;
  escalationLevel: number;
  status: 'pending' | 'escalated' | 'cancelled' | 'completed';
}

const DEFAULT_SLA_MS = 30 * 60 * 1000; // 30 minutes

export class TaskTimer implements DurableObject {
  constructor(readonly state: DurableObjectState, readonly env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/start' && request.method === 'POST') {
      const body = await request.json() as { taskId: string; slaMs?: number };
      const state: TaskTimerState = {
        taskId: body.taskId,
        slaMs: body.slaMs ?? DEFAULT_SLA_MS,
        startedAt: Date.now(),
        escalationLevel: 0,
        status: 'pending',
      };
      await this.state.storage.put('timer', state);
      await this.state.storage.setAlarm(state.startedAt + state.slaMs);
      return Response.json({ ok: true, ...state });
    }

    if (url.pathname === '/cancel' && request.method === 'POST') {
      const existing = await this.state.storage.get<TaskTimerState>('timer');
      if (existing) {
        existing.status = 'cancelled';
        await this.state.storage.put('timer', existing);
      }
      await this.state.storage.deleteAlarm();
      return Response.json({ ok: true });
    }

    if (url.pathname === '/complete' && request.method === 'POST') {
      const existing = await this.state.storage.get<TaskTimerState>('timer');
      if (existing) {
        existing.status = 'completed';
        await this.state.storage.put('timer', existing);
      }
      await this.state.storage.deleteAlarm();
      return Response.json({ ok: true });
    }

    if (url.pathname === '/status' && request.method === 'GET') {
      const state = await this.state.storage.get<TaskTimerState>('timer');
      const alarm = await this.state.storage.getAlarm();
      return Response.json({ state, alarmScheduledAt: alarm });
    }

    if (url.pathname === '/extend' && request.method === 'POST') {
      const body = await request.json() as { additionalMs: number };
      const existing = await this.state.storage.get<TaskTimerState>('timer');
      if (!existing) return Response.json({ error: 'No active timer' }, { status: 404 });
      existing.slaMs += body.additionalMs;
      await this.state.storage.put('timer', existing);
      await this.state.storage.setAlarm(existing.startedAt + existing.slaMs);
      return Response.json({ ok: true, ...existing });
    }

    return new Response('Not found', { status: 404 });
  }

  async alarm(): Promise<void> {
    const state = await this.state.storage.get<TaskTimerState>('timer');
    if (!state || state.status === 'cancelled' || state.status === 'completed') return;

    state.escalationLevel++;
    state.status = 'escalated';
    await this.state.storage.put('timer', state);

    // Enqueue an alert for the escalation
    try {
      await this.env.alertQ.send({
        type: 'task_sla_breached',
        taskId: state.taskId,
        escalationLevel: state.escalationLevel,
        slaMs: state.slaMs,
        timestamp: Date.now(),
      });
    } catch {
      // Queue may not be bound in all environments
    }
  }
}
