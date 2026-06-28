import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import { roadEdges, evacZones, medicalFacilities, triagePatients, logisticsStock, logisticsMovements, resourceRequests, infraAssets, infraAssetDeps } from '../../db/schema';
import { eq, and } from 'drizzle-orm';
import { ulid, nowMs } from '../../lib/ulid';
import { writeAudit } from '../../lib/audit';

export const domainP8Routes = new Hono<AppEnv>();

// T112: Register road edge
domainP8Routes.post('/routing/edge', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(roadEdges).values({
    id, orgId,
    regionId: body.regionId as string,
    fromNode: body.fromNode as string,
    toNode: body.toNode as string,
    length: (body.length as number) ?? 1,
    capacity: (body.capacity as number) ?? 100,
    oneway: (body.oneway as boolean) ?? false,
    hazardWeight: (body.hazardWeight as number) ?? 0,
    contraflow: false,
    createdAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T112: Route via Dijkstra (in-Worker, ≤50,000 edges)
domainP8Routes.post('/routing/route', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const regionId = body.regionId as string;
  const fromNode = body.fromNode as string;
  const toNode = body.toNode as string;

  const edges = await db.select().from(roadEdges)
    .where(and(eq(roadEdges.orgId, orgId), eq(roadEdges.regionId, regionId))).all();

  if (edges.length > 50000) {
    return c.json({
      error: {
        code: 'GRAPH_TOO_LARGE',
        message: `Road graph has ${edges.length} edges (cap: 50,000). Delegate to external Valhalla/OSRM router.`,
        request_id: c.get('requestId'),
      },
    }, 413);
  }

  // Simple Dijkstra
  const graph = new Map<string, { to: string; weight: number }[]>();
  for (const e of edges) {
    if (!graph.has(e.fromNode)) graph.set(e.fromNode, []);
    const weight = e.length * (1 + e.hazardWeight);
    graph.get(e.fromNode)!.push({ to: e.toNode, weight });
    if (!e.oneway) {
      if (!graph.has(e.toNode)) graph.set(e.toNode, []);
      graph.get(e.toNode)!.push({ to: e.fromNode, weight });
    }
  }

  const dist = new Map<string, number>();
  const prev = new Map<string, string>();
  const visited = new Set<string>();
  dist.set(fromNode, 0);
  const queue: { node: string; d: number }[] = [{ node: fromNode, d: 0 }];

  while (queue.length > 0) {
    queue.sort((a, b) => a.d - b.d);
    const curr = queue.shift()!;
    if (visited.has(curr.node)) continue;
    visited.add(curr.node);
    if (curr.node === toNode) break;
    const neighbors = graph.get(curr.node) ?? [];
    for (const n of neighbors) {
      if (visited.has(n.to)) continue;
      const newDist = curr.d + n.weight;
      if (!dist.has(n.to) || newDist < (dist.get(n.to) ?? Infinity)) {
        dist.set(n.to, newDist);
        prev.set(n.to, curr.node);
        queue.push({ node: n.to, d: newDist });
      }
    }
  }

  if (!dist.has(toNode)) return c.json({ error: { code: 'NO_ROUTE', message: 'No route found', request_id: c.get('requestId') } }, 404);

  const path: string[] = [];
  let node: string | undefined = toNode;
  while (node) { path.unshift(node); node = prev.get(node); }

  return c.json({ path, distance: dist.get(toNode), edgeCount: edges.length });
});

// T113: Create evacuation zone
domainP8Routes.post('/evac-zones', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(evacZones).values({
    id, orgId,
    incidentId: body.incidentId as string,
    zoneName: body.zoneName as string,
    geometry: body.geometry as string,
    status: ((body.status as string) ?? 'advisory') as 'advisory' | 'ordered' | 'cleared' | 'nogo',
    priority: (body.priority as number) ?? 1,
    estimatedPop: (body.estimatedPop as number) ?? null,
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T116: Register medical facility
domainP8Routes.post('/medical/facilities', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(medicalFacilities).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    name: body.name as string,
    type: body.type as 'hospital' | 'clinic' | 'field_hospital' | 'mobile_unit',
    geo: (body.geo as string) ?? null,
    totalBeds: (body.totalBeds as number) ?? 0,
    availableBeds: (body.availableBeds as number) ?? 0,
    icuBeds: (body.icuBeds as number) ?? 0,
    erBeds: (body.erBeds as number) ?? 0,
    ambulances: (body.ambulances as number) ?? 0,
    status: 'open',
    fhirId: (body.fhirId as string) ?? null,
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T116: Triage patient
domainP8Routes.post('/medical/triage', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(triagePatients).values({
    id, orgId,
    incidentId: body.incidentId as string,
    facilityId: (body.facilityId as string) ?? null,
    qrWristband: (body.qrWristband as string) ?? ulid(),
    triageCategory: body.triageCategory as 'immediate' | 'delayed' | 'minor' | 'expectant',
    severity: ((body.severity as string) ?? 'minor') as 'critical' | 'serious' | 'moderate' | 'minor',
    name: (body.name as string) ?? null,
    age: (body.age as number) ?? null,
    sex: (body.sex as string) ?? null,
    mciMode: (body.mciMode as boolean) ?? false,
    transportStatus: 'pending',
    visibility: 'internal',
    reviewStatus: 'draft',
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T118: Logistics movement (idempotent)
domainP8Routes.post('/logistics/movements', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const idempotencyKey = (body.idempotencyKey as string) ?? ulid();

  const existing = await db.select().from(logisticsMovements)
    .where(eq(logisticsMovements.idempotencyKey, idempotencyKey)).limit(1).all();
  if (existing[0]) return c.json({ id: existing[0].id, ok: true, duplicate: true });

  const id = ulid();
  await db.insert(logisticsMovements).values({
    id, orgId,
    itemId: body.itemId as string,
    fromLocation: (body.fromLocation as string) ?? null,
    toLocation: (body.toLocation as string) ?? null,
    qty: body.qty as number,
    lot: (body.lot as string) ?? null,
    movementType: body.movementType as 'receive' | 'transfer' | 'dispatch' | 'consume' | 'adjust' | 'return',
    idempotencyKey,
    reference: (body.reference as string) ?? null,
    createdAt: nowMs(),
  });

  // Update stock level
  const stock = await db.select().from(logisticsStock)
    .where(and(eq(logisticsStock.itemId, body.itemId as string), eq(logisticsStock.locationId, (body.toLocation as string) ?? ''))).limit(1).all();
  if (stock[0]) {
    await db.update(logisticsStock).set({ qty: stock[0].qty + (body.qty as number), updatedAt: nowMs() }).where(eq(logisticsStock.id, stock[0].id));
  } else {
    await db.insert(logisticsStock).values({
      id: ulid(), orgId,
      itemId: body.itemId as string,
      locationId: (body.toLocation as string) ?? '',
      qty: body.qty as number,
      lot: (body.lot as string) ?? null,
      expiry: null,
      updatedAt: nowMs(),
    });
  }

  return c.json({ id, ok: true }, 201);
});

// T119: Resource request
domainP8Routes.post('/resource-requests', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(resourceRequests).values({
    id, orgId,
    incidentId: body.incidentId as string,
    itemType: body.itemType as string,
    quantity: (body.quantity as number) ?? 1,
    urgency: ((body.urgency as string) ?? 'medium') as 'low' | 'medium' | 'high' | 'critical',
    status: 'requested',
    requestedBy: (body.requestedBy as string) ?? orgId,
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T119: Approve resource request
domainP8Routes.post('/resource-requests/:id/approve', async (c) => {
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  await db.update(resourceRequests).set({ status: 'approved', approvedBy: orgId, updatedAt: nowMs() }).where(eq(resourceRequests.id, c.req.param('id')));
  return c.json({ ok: true });
});

// T123: Register infra asset
domainP8Routes.post('/infra/assets', async (c) => {
  const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
  const orgId = c.get('orgId') ?? 'system';
  const id = ulid();
  const db = drizzle(c.env.db);
  await db.insert(infraAssets).values({
    id, orgId,
    incidentId: (body.incidentId as string) ?? null,
    type: body.type as string,
    name: body.name as string,
    geo: (body.geo as string) ?? null,
    status: ((body.status as string) ?? 'unknown') as 'operational' | 'degraded' | 'failed' | 'restored' | 'unknown',
    restoreEta: (body.restoreEta as number) ?? null,
    parentId: (body.parentId as string) ?? null,
    createdAt: nowMs(), updatedAt: nowMs(),
  });
  return c.json({ id, ok: true }, 201);
});

// T123: BFS cascade failure
domainP8Routes.post('/infra/:assetId/cascade', async (c) => {
  const orgId = c.get('orgId') ?? 'system';
  const db = drizzle(c.env.db);
  const assetId = c.req.param('assetId');

  const deps = await db.select().from(infraAssetDeps).where(eq(infraAssetDeps.orgId, orgId)).all();
  const children = new Map<string, string[]>();
  for (const d of deps) {
    if (!children.has(d.parentId)) children.set(d.parentId, []);
    children.get(d.parentId)!.push(d.childId);
  }

  const affected: string[] = [assetId];
  const queue = [assetId];
  const visited = new Set<string>([assetId]);

  while (queue.length > 0) {
    const curr = queue.shift()!;
    const kids = children.get(curr) ?? [];
    for (const k of kids) {
      if (visited.has(k)) continue;
      visited.add(k);
      affected.push(k);
      queue.push(k);
    }
  }

  // Mark all affected as degraded
  for (const a of affected) {
    await db.update(infraAssets).set({ status: 'degraded', updatedAt: nowMs() }).where(eq(infraAssets.id, a));
  }

  await writeAudit({ db, orgId, incidentId: null, actor: orgId, action: 'infra.cascade', entity: `infra:${assetId}`, after: { affected } });
  return c.json({ affected, count: affected.length });
});
