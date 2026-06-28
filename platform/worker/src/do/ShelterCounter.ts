import type { Env } from '../index';

// T65: ShelterCounter DO — live occupancy per shelter.
// Provides atomic increment/decrement of shelter occupancy with capacity enforcement.
// Storage: shelterId, totalCapacity, currentOccupancy.

interface ShelterState {
  shelterId: string;
  totalCapacity: number;
  currentOccupancy: number;
}

export class ShelterCounter implements DurableObject {
  constructor(readonly state: DurableObjectState, readonly env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/init' && request.method === 'POST') {
      const body = await request.json() as { shelterId: string; totalCapacity: number; currentOccupancy?: number };
      const state: ShelterState = {
        shelterId: body.shelterId,
        totalCapacity: body.totalCapacity,
        currentOccupancy: body.currentOccupancy ?? 0,
      };
      await this.state.storage.put('shelter', state);
      return Response.json({ ok: true, ...state });
    }

    if (url.pathname === '/checkin' && request.method === 'POST') {
      const body = await request.json() as { count?: number };
      const count = body.count ?? 1;
      const state = await this.state.storage.get<ShelterState>('shelter');
      if (!state) return Response.json({ error: 'Shelter not initialized' }, { status: 404 });

      if (state.currentOccupancy + count > state.totalCapacity) {
        return Response.json({
          ok: false,
          error: 'CAPACITY_EXCEEDED',
          currentOccupancy: state.currentOccupancy,
          totalCapacity: state.totalCapacity,
          available: state.totalCapacity - state.currentOccupancy,
        }, { status: 409 });
      }

      state.currentOccupancy += count;
      await this.state.storage.put('shelter', state);
      return Response.json({
        ok: true,
        currentOccupancy: state.currentOccupancy,
        totalCapacity: state.totalCapacity,
        available: state.totalCapacity - state.currentOccupancy,
      });
    }

    if (url.pathname === '/checkout' && request.method === 'POST') {
      const body = await request.json() as { count?: number };
      const count = body.count ?? 1;
      const state = await this.state.storage.get<ShelterState>('shelter');
      if (!state) return Response.json({ error: 'Shelter not initialized' }, { status: 404 });

      state.currentOccupancy = Math.max(0, state.currentOccupancy - count);
      await this.state.storage.put('shelter', state);
      return Response.json({
        ok: true,
        currentOccupancy: state.currentOccupancy,
        totalCapacity: state.totalCapacity,
        available: state.totalCapacity - state.currentOccupancy,
      });
    }

    if (url.pathname === '/status' && request.method === 'GET') {
      const state = await this.state.storage.get<ShelterState>('shelter');
      if (!state) return Response.json({ error: 'Shelter not initialized' }, { status: 404 });
      return Response.json({
        shelterId: state.shelterId,
        currentOccupancy: state.currentOccupancy,
        totalCapacity: state.totalCapacity,
        available: state.totalCapacity - state.currentOccupancy,
        isFull: state.currentOccupancy >= state.totalCapacity,
      });
    }

    if (url.pathname === '/reset' && request.method === 'POST') {
      const state = await this.state.storage.get<ShelterState>('shelter');
      if (!state) return Response.json({ error: 'Shelter not initialized' }, { status: 404 });
      state.currentOccupancy = 0;
      await this.state.storage.put('shelter', state);
      return Response.json({ ok: true, ...state });
    }

    return new Response('Not found', { status: 404 });
  }
}
