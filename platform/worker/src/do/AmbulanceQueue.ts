import type { Env } from '../index';

// T116: AmbulanceQueue DO — medical dispatch priority queue.
// Maintains a priority queue of ambulance requests ordered by urgency then time.
// Storage: queue items array.

type Urgency = 'critical' | 'high' | 'medium' | 'low';

const URGENCY_WEIGHT: Record<Urgency, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
};

interface AmbulanceRequest {
  id: string;
  patientLocation: { lat: number; lng: number };
  urgency: Urgency;
  description?: string;
  requestedAt: number;
}

export class AmbulanceQueue implements DurableObject {
  constructor(readonly state: DurableObjectState, readonly env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/enqueue' && request.method === 'POST') {
      const body = await request.json() as Omit<AmbulanceRequest, 'requestedAt'> & { requestedAt?: number };
      const queue = (await this.state.storage.get<AmbulanceRequest[]>('queue')) ?? [];
      const item: AmbulanceRequest = {
        ...body,
        requestedAt: body.requestedAt ?? Date.now(),
      };
      queue.push(item);
      queue.sort(sortByPriority);
      await this.state.storage.put('queue', queue);
      return Response.json({ ok: true, id: item.id, position: queue.findIndex((q) => q.id === item.id) + 1 }, { status: 201 });
    }

    if (url.pathname === '/dequeue' && request.method === 'POST') {
      const queue = (await this.state.storage.get<AmbulanceRequest[]>('queue')) ?? [];
      if (queue.length === 0) {
        return Response.json({ ok: false, message: 'Queue is empty' }, { status: 404 });
      }
      const next = queue.shift()!;
      await this.state.storage.put('queue', queue);
      return Response.json({ ok: true, request: next, remaining: queue.length });
    }

    if (url.pathname === '/peek' && request.method === 'GET') {
      const queue = (await this.state.storage.get<AmbulanceRequest[]>('queue')) ?? [];
      if (queue.length === 0) {
        return Response.json({ ok: false, message: 'Queue is empty' }, { status: 404 });
      }
      return Response.json({ ok: true, next: queue[0], queueLength: queue.length });
    }

    if (url.pathname === '/list' && request.method === 'GET') {
      const queue = (await this.state.storage.get<AmbulanceRequest[]>('queue')) ?? [];
      return Response.json({ items: queue, count: queue.length });
    }

    if (url.pathname === '/remove' && request.method === 'POST') {
      const body = await request.json() as { id: string };
      const queue = (await this.state.storage.get<AmbulanceRequest[]>('queue')) ?? [];
      const filtered = queue.filter((q) => q.id !== body.id);
      await this.state.storage.put('queue', filtered);
      return Response.json({ ok: true, removed: queue.length - filtered.length, remaining: filtered.length });
    }

    if (url.pathname === '/status' && request.method === 'GET') {
      const queue = (await this.state.storage.get<AmbulanceRequest[]>('queue')) ?? [];
      const byUrgency = queue.reduce<Record<string, number>>((acc, q) => {
        acc[q.urgency] = (acc[q.urgency] ?? 0) + 1;
        return acc;
      }, {});
      return Response.json({ total: queue.length, byUrgency });
    }

    return new Response('Not found', { status: 404 });
  }
}

function sortByPriority(a: AmbulanceRequest, b: AmbulanceRequest): number {
  const urgencyDiff = URGENCY_WEIGHT[b.urgency] - URGENCY_WEIGHT[a.urgency];
  if (urgencyDiff !== 0) return urgencyDiff;
  return a.requestedAt - b.requestedAt;
}
