import type { Env } from '../index';

const MAX_SOCKETS = 256;

// T21: IncidentRoom DO — Hibernatable WebSocket fanout, presence, live panel deltas.
// FEATURES.md:136 — one IncidentRoom per incident.
// Metis C5: cap 256 concurrent sockets per DO; overflow shards or falls back to polling.
export class IncidentRoom implements DurableObject {
  state: DurableObjectState;
  env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/ws') {
      if (request.headers.get('Upgrade') !== 'websocket') {
        return new Response('Expected websocket', { status: 426 });
      }

      const connectedCount = (await this.state.storage.get<number>('connectionCount')) ?? 0;
      if (connectedCount >= MAX_SOCKETS) {
        const partition = Math.floor(connectedCount / MAX_SOCKETS);
        return new Response(
          JSON.stringify({ redirect: true, partition, message: 'Use shard DO' }),
          { status: 302, headers: { 'Content-Type': 'application/json' } },
        );
      }

      const pair = new WebSocketPair();
      const client = pair[0];
      const server = pair[1];
      if (!client || !server) return new Response('WebSocket creation failed', { status: 500 });
      this.state.acceptWebSocket(server);

      await this.state.storage.put('connectionCount', connectedCount + 1);
      server.serializeAttachment({ userId: url.searchParams.get('userId') ?? 'anonymous' });

      server.send(JSON.stringify({ type: 'connected', message: 'IncidentRoom connected' }));
      return new Response(null, { status: 101, webSocket: client });
    }

    if (url.pathname === '/broadcast') {
      const body = await request.json() as Record<string, unknown>;
      const msg = JSON.stringify({ type: 'delta', panel: body.panel, data: body.data });
      const sockets = this.state.getWebSockets();
      for (const ws of sockets) {
        try { ws.send(msg); } catch { /* disconnected */ }
      }
      return new Response(JSON.stringify({ sent: sockets.length }), { headers: { 'Content-Type': 'application/json' } });
    }

    if (url.pathname === '/presence') {
      const sockets = this.state.getWebSockets();
      const users = sockets.map((ws) => {
        const att = ws.deserializeAttachment() as { userId: string } | null;
        return att?.userId ?? 'unknown';
      });
      return new Response(JSON.stringify({ users }), { headers: { 'Content-Type': 'application/json' } });
    }

    if (url.pathname === '/state') {
      const state = await this.state.storage.list({ limit: 50 });
      return new Response(JSON.stringify(Object.fromEntries(state)), { headers: { 'Content-Type': 'application/json' } });
    }

    return new Response('Not found', { status: 404 });
  }

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    let msg: Record<string, unknown>;
    try { msg = typeof message === 'string' ? JSON.parse(message) : {}; } catch { return; }

    if (msg.type === 'ping') {
      ws.send(JSON.stringify({ type: 'pong' }));
      return;
    }

    if (msg.type === 'position') {
      const att = ws.deserializeAttachment() as { userId: string } | null;
      await this.state.storage.put(`pos:${att?.userId ?? 'unknown'}`, msg.data);
      const broadcast = JSON.stringify({ type: 'delta', panel: 'responder_position', data: { userId: att?.userId, position: msg.data } });
      for (const other of this.state.getWebSockets()) {
        if (other !== ws) { try { other.send(broadcast); } catch { /* */ } }
      }
    }
  }

  async webSocketClose(ws: WebSocket): Promise<void> {
    const count = (await this.state.storage.get<number>('connectionCount')) ?? 1;
    await this.state.storage.put('connectionCount', Math.max(0, count - 1));
    const att = ws.deserializeAttachment() as { userId: string } | null;
    if (att?.userId) await this.state.storage.delete(`pos:${att.userId}`);
  }
}
