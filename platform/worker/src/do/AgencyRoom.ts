import type { Env } from '../index';

// T157: AgencyRoom DO — inter-agency chat channel.
// Hibernatable WebSocket channel for multi-agency coordination.
// Storage: message history (last 100), presence.

const MAX_HISTORY = 100;
const MAX_SOCKETS = 64;

interface ChatMessage {
  id: string;
  agencyId: string;
  agencyName: string;
  body: string;
  ts: number;
}

export class AgencyRoom implements DurableObject {
  constructor(readonly state: DurableObjectState, readonly env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/ws') {
      if (request.headers.get('Upgrade') !== 'websocket') {
        return new Response('Expected websocket', { status: 426 });
      }

      const connectedCount = (await this.state.storage.get<number>('connectionCount')) ?? 0;
      if (connectedCount >= MAX_SOCKETS) {
        return new Response(JSON.stringify({ error: 'Channel at capacity' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      const pair = new WebSocketPair();
      const client = pair[0];
      const server = pair[1];
      if (!client || !server) return new Response('WebSocket creation failed', { status: 500 });
      this.state.acceptWebSocket(server);

      await this.state.storage.put('connectionCount', connectedCount + 1);
      server.serializeAttachment({
        agencyId: url.searchParams.get('agencyId') ?? 'unknown',
        agencyName: url.searchParams.get('agencyName') ?? 'Unknown Agency',
      });

      const history = (await this.state.storage.get<ChatMessage[]>('history')) ?? [];
      server.send(JSON.stringify({ type: 'connected', history }));
      return new Response(null, { status: 101, webSocket: client });
    }

    if (url.pathname === '/messages' && request.method === 'GET') {
      const history = (await this.state.storage.get<ChatMessage[]>('history')) ?? [];
      return Response.json({ messages: history });
    }

    if (url.pathname === '/messages' && request.method === 'POST') {
      const body = await request.json() as { agencyId: string; agencyName: string; body: string };
      const msg: ChatMessage = {
        id: crypto.randomUUID(),
        agencyId: body.agencyId,
        agencyName: body.agencyName,
        body: body.body,
        ts: Date.now(),
      };

      const history = (await this.state.storage.get<ChatMessage[]>('history')) ?? [];
      history.push(msg);
      if (history.length > MAX_HISTORY) history.shift();
      await this.state.storage.put('history', history);

      const broadcast = JSON.stringify({ type: 'message', message: msg });
      for (const ws of this.state.getWebSockets()) {
        try { ws.send(broadcast); } catch { /* disconnected */ }
      }

      return Response.json({ ok: true, message: msg }, { status: 201 });
    }

    if (url.pathname === '/presence' && request.method === 'GET') {
      const sockets = this.state.getWebSockets();
      const agencies = sockets.map((ws) => {
        const att = ws.deserializeAttachment() as { agencyId: string; agencyName: string } | null;
        return att ?? { agencyId: 'unknown', agencyName: 'Unknown' };
      });
      return Response.json({ agencies, count: agencies.length });
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

    if (msg.type === 'chat') {
      const att = ws.deserializeAttachment() as { agencyId: string; agencyName: string } | null;
      const chatMsg: ChatMessage = {
        id: crypto.randomUUID(),
        agencyId: att?.agencyId ?? 'unknown',
        agencyName: att?.agencyName ?? 'Unknown',
        body: String(msg.body ?? ''),
        ts: Date.now(),
      };

      const history = (await this.state.storage.get<ChatMessage[]>('history')) ?? [];
      history.push(chatMsg);
      if (history.length > MAX_HISTORY) history.shift();
      await this.state.storage.put('history', history);

      const broadcast = JSON.stringify({ type: 'message', message: chatMsg });
      for (const other of this.state.getWebSockets()) {
        try { other.send(broadcast); } catch { /* */ }
      }
    }
  }

  async webSocketClose(ws: WebSocket): Promise<void> {
    const count = (await this.state.storage.get<number>('connectionCount')) ?? 1;
    await this.state.storage.put('connectionCount', Math.max(0, count - 1));
    void ws;
  }
}
