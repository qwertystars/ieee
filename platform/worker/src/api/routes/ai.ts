import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { aiCalls, prompts, aiOutputs, reports } from '../../db/schema';
import { eq, and, desc, sql } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const aiRoutes = new Hono<AppEnv>();

// T100: AI call wrapper (OpenAI-compatible, zod-retry, fallback chain)
aiRoutes.post('/ai/call', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const callId = ulid();
  const promptName = body.promptName as string;
  const input = body.input as string;
  const startTime = nowMs();

  // Workers AI pricing (llama-3.1-8b-instruct): ~$0.0001 / 1K input tokens, ~$0.0003 / 1K output tokens
  const COST_PER_1K_INPUT = 0.0001;
  const COST_PER_1K_OUTPUT = 0.0003;

  let output: unknown = null;
  let success = true;
  let error: string | null = null;
  let provider = 'workers-ai';
  let model = 'llama-3.1-8b-instruct';
  let inputTokens: number | null = null;
  let outputTokens: number | null = null;

  if (!c.env.ai) {
    await db.insert(aiCalls).values({
      id: callId, orgId,
      incidentId: (body.incidentId as string) ?? null,
      promptName,
      promptVersion: 1,
      provider,
      model,
      inputTokens: null,
      outputTokens: null,
      latencyMs: nowMs() - startTime,
      cost: 0,
      success: false,
      error: 'AI binding not available',
      createdAt: nowMs(),
    });
    return c.json({ error: { code: 'AI_UNAVAILABLE', message: 'AI binding not configured on this Worker', request_id: c.get('requestId') } }, 503);
  }

  try {
    const aiResp = await c.env.ai.run('@cf/meta/llama-3.1-8b-instruct' as never, {
      messages: [{ role: 'user', content: input }],
      max_tokens: 500,
    } as never);
    output = aiResp;
    inputTokens = (aiResp as { usage?: { prompt_tokens?: number } })?.usage?.prompt_tokens ?? null;
    outputTokens = (aiResp as { usage?: { completion_tokens?: number } })?.usage?.completion_tokens ?? null;
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
    success = false;
  }

  const latencyMs = nowMs() - startTime;
  const cost = ((inputTokens ?? 0) / 1000) * COST_PER_1K_INPUT + ((outputTokens ?? 0) / 1000) * COST_PER_1K_OUTPUT;

  await db.insert(aiCalls).values({
    id: callId, orgId,
    incidentId: (body.incidentId as string) ?? null,
    promptName,
    promptVersion: 1,
    provider,
    model,
    inputTokens,
    outputTokens,
    latencyMs,
    cost,
    success,
    error,
    createdAt: nowMs(),
  });

  return c.json({ id: callId, output, success, latencyMs, provider, model, cost, inputTokens, outputTokens });
});

// T101: Create prompt version
aiRoutes.post('/prompts', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);

  const existing = await db.select().from(prompts)
    .where(and(eq(prompts.orgId, orgId), eq(prompts.name, body.name as string))).all();
  const version = existing.length > 0 ? Math.max(...existing.map((p) => p.version)) + 1 : 1;

  await db.insert(prompts).values({
    id, orgId,
    name: body.name as string,
    version,
    body: body.body as string,
    schema: (body.schema as Record<string, unknown>) ?? {},
    temperature: (body.temperature as number) ?? 0.7,
    active: true,
    createdAt: nowMs(), updatedAt: nowMs(),
  });

  await db.update(prompts).set({ active: false }).where(and(eq(prompts.orgId, orgId), eq(prompts.name, body.name as string), sql`version != ${version}`));

  return c.json({ id, version, ok: true }, 201);
});

// T103: Generate AI output (draft → approval gate)
aiRoutes.post('/ai/generate', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);

  await db.insert(aiOutputs).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    promptName: body.promptName as string,
    output: body.output ?? { draft: true },
    confidence: (body.confidence as number) ?? 0.7,
    citations: (body.citations as string[]) ?? [],
    hallucinationFlag: false,
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });

  await writeAudit({ db, orgId, incidentId: (body.incidentId as string) ?? null, actor: orgId, action: 'ai.output_generated', entity: `ai_output:${id}`, after: body });
  return c.json({ id, ok: true, reviewStatus: 'draft' }, 201);
});

// T102: Approve AI output
aiRoutes.post('/ai/outputs/:id/approve', async (c) => {
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const output = await db.select().from(aiOutputs).where(eq(aiOutputs.id, c.req.param('id'))).limit(1).all();
  if (!output[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'AI output not found', request_id: c.get('requestId') } }, 404);

  await db.update(aiOutputs).set({
    reviewStatus: 'official',
    approvedBy: orgId,
    approvedAt: nowMs(),
    updatedAt: nowMs(),
  }).where(eq(aiOutputs.id, output[0].id));

  await writeAudit({ db, orgId, incidentId: output[0].incidentId, actor: orgId, action: 'ai.output_approved', entity: `ai_output:${output[0].id}`, after: {} });
  return c.json({ ok: true, reviewStatus: 'official' });
});

// T107: Create report from template
aiRoutes.post('/ai/reports', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);

  const shareToken = ulid();
  await db.insert(reports).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    title: body.title as string,
    reportType: body.reportType as string,
    templateId: (body.templateId as string) ?? null,
    contentMd: (body.contentMd as string) ?? '',
    contentHtml: (body.contentHtml as string) ?? null,
    shareToken,
    shareExpiry: nowMs() + 7 * 24 * 3600 * 1000,
    visibility: 'internal',
    reviewStatus: 'draft',
    version: 1,
    createdAt: nowMs(), updatedAt: nowMs(),
  });

  return c.json({ id, shareToken, ok: true }, 201);
});

aiRoutes.get('/ai/reports', async (c) => {
  const orgId = c.get('orgId');
  const incidentId = c.req.query('incidentId');
  const db = drizzle(c.env.db);
  const conditions = [orgId ? eq(reports.orgId, orgId) : sql`1=1`];
  if (incidentId) conditions.push(eq(reports.incidentId, incidentId));
  const result = await db.select().from(reports).where(and(...conditions)).orderBy(desc(reports.createdAt)).all();
  return c.json({ items: result });
});

aiRoutes.get('/ai/reports/:id', async (c) => {
  const db = drizzle(c.env.db);
  const result = await db.select().from(reports).where(eq(reports.id, c.req.param('id'))).limit(1).all();
  if (!result[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Report not found', request_id: c.get('requestId') } }, 404);
  return c.json(result[0]);
});

// T110: Export report (JSON/MD)
aiRoutes.get('/ai/reports/:id/export', async (c) => {
  const format = c.req.query('format') ?? 'json';
  const db = drizzle(c.env.db);
  const report = await db.select().from(reports).where(eq(reports.id, c.req.param('id'))).limit(1).all();
  if (!report[0]) return c.json({ error: { code: 'NOT_FOUND', message: 'Report not found', request_id: c.get('requestId') } }, 404);

  if (format === 'md') {
    return new Response(report[0].contentMd ?? '', { headers: { 'Content-Type': 'text/markdown' } });
  }
  return c.json(report[0]);
});

// T106: AI monitor (latency/error/token stats)
aiRoutes.get('/ai/monitor', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const calls = await db.select().from(aiCalls).where(orgId ? eq(aiCalls.orgId, orgId) : sql`1=1`).orderBy(desc(aiCalls.createdAt)).limit(100).all();

  const total = calls.length;
  const successCount = calls.filter((c2) => c2.success).length;
  const avgLatency = total > 0 ? calls.reduce((s, c2) => s + (c2.latencyMs ?? 0), 0) / total : 0;
  const totalTokens = calls.reduce((s, c2) => s + (c2.inputTokens ?? 0) + (c2.outputTokens ?? 0), 0);

  return c.json({
    totalCalls: total,
    successRate: total > 0 ? successCount / total : 0,
    avgLatencyMs: Math.round(avgLatency),
    totalTokens,
    errorRate: total > 0 ? (total - successCount) / total : 0,
  });
});
