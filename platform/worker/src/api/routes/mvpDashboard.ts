import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import {
  incidentReports, roadStatuses, responseTeams, tasks,
  shelters, alerts, areaAssessments,
  disasterEvents,
} from '../../db/schema';
import { eq, and, sql, count } from 'drizzle-orm';
import { nowMs } from '../../lib/ulid';

export const dashboardRoutes = new Hono<AppEnv>();

dashboardRoutes.get('/events/:incidentId/dashboard-summary', async (c) => {
  const orgId = c.get('orgId');
  const incidentId = c.req.param('incidentId');
  const db = drizzle(c.env.db);

  const orgFilter = orgId ? eq(incidentReports.orgId, orgId) : sql`1=1`;

  const [reportsCount, roadsBlocked, pendingTasks, openShelters, activeAlerts, criticalAreas, highAreas] = await Promise.all([
    db.select({ c: count() }).from(incidentReports).where(and(eq(incidentReports.incidentId, incidentId), orgFilter)).all(),
    db.select({ c: count() }).from(roadStatuses).where(and(eq(roadStatuses.incidentId, incidentId), eq(roadStatuses.status, 'blocked'), orgId ? eq(roadStatuses.orgId, orgId) : sql`1=1`)).all(),
    db.select({ c: count() }).from(tasks).where(and(eq(tasks.incidentId, incidentId), sql`status IN ('assigned','accepted','en_route','on_site','blocked')`, orgId ? eq(tasks.orgId, orgId) : sql`1=1`)).all(),
    db.select({ c: count() }).from(shelters).where(and(eq(shelters.incidentId, incidentId), eq(shelters.status, 'open'), orgId ? eq(shelters.orgId, orgId) : sql`1=1`)).all(),
    db.select({ c: count() }).from(alerts).where(and(eq(alerts.incidentId, incidentId), eq(alerts.acknowledged, false), orgId ? eq(alerts.orgId, orgId) : sql`1=1`)).all(),
    db.select({ c: count() }).from(areaAssessments).where(and(eq(areaAssessments.incidentId, incidentId), eq(areaAssessments.priorityLevel, 'critical'), orgId ? eq(areaAssessments.orgId, orgId) : sql`1=1`)).all(),
    db.select({ c: count() }).from(areaAssessments).where(and(eq(areaAssessments.incidentId, incidentId), eq(areaAssessments.priorityLevel, 'high'), orgId ? eq(areaAssessments.orgId, orgId) : sql`1=1`)).all(),
  ]);

  return c.json({
    total_reports: reportsCount[0]?.c ?? 0,
    roads_blocked: roadsBlocked[0]?.c ?? 0,
    pending_tasks: pendingTasks[0]?.c ?? 0,
    shelters_open: openShelters[0]?.c ?? 0,
    alerts_active: activeAlerts[0]?.c ?? 0,
    critical_areas: criticalAreas[0]?.c ?? 0,
    high_areas: highAreas[0]?.c ?? 0,
    last_updated: nowMs(),
  });
});

dashboardRoutes.get('/events/:incidentId/map-layers', async (c) => {
  const orgId = c.get('orgId');
  const incidentId = c.req.param('incidentId');
  const bbox = c.req.query('bbox');

  if (bbox) {
    const parts = bbox.split(',');
    if (parts.length !== 4 || parts.some((p) => Number.isNaN(parseFloat(p)))) {
      return c.json({ error: { code: 'INVALID_BBOX', message: 'Invalid bbox; expected minx,miny,maxx,maxy', request_id: c.get('requestId') } }, 400);
    }
  }

  const db = drizzle(c.env.db);
  const orgFilter = orgId ? eq(incidentReports.orgId, orgId) : sql`1=1`;

  const [reports, roads, teams, taskList, shelterList, areas] = await Promise.all([
    db.select().from(incidentReports).where(and(eq(incidentReports.incidentId, incidentId), orgFilter)).all(),
    db.select().from(roadStatuses).where(and(eq(roadStatuses.incidentId, incidentId), orgId ? eq(roadStatuses.orgId, orgId) : sql`1=1`)).all(),
    db.select().from(responseTeams).where(and(eq(responseTeams.incidentId, incidentId), orgId ? eq(responseTeams.orgId, orgId) : sql`1=1`)).all(),
    db.select().from(tasks).where(and(eq(tasks.incidentId, incidentId), orgId ? eq(tasks.orgId, orgId) : sql`1=1`)).all(),
    db.select().from(shelters).where(and(eq(shelters.incidentId, incidentId), orgId ? eq(shelters.orgId, orgId) : sql`1=1`)).all(),
    db.select().from(areaAssessments).where(and(eq(areaAssessments.incidentId, incidentId), orgId ? eq(areaAssessments.orgId, orgId) : sql`1=1`)).all(),
  ]);

  return c.json({
    areas: areas.map((a) => ({ ...a, geometry: a.geometry ? JSON.parse(a.geometry) : null })),
    reports: reports.map((r) => ({ ...r, geometry: r.geometry ? JSON.parse(r.geometry) : null })),
    roads: roads.map((r) => ({ ...r, geometry: r.geometry ? JSON.parse(r.geometry) : null })),
    shelters: shelterList.map((s) => ({ ...s, geometry: s.geometry ? JSON.parse(s.geometry) : null })),
    teams: teams.map((t) => ({ ...t, currentLocation: t.currentLocation ? JSON.parse(t.currentLocation) : null })),
    observations: [],
    tasks: taskList.map((t) => ({ ...t, location: t.location ? JSON.parse(t.location) : null })),
  });
});

dashboardRoutes.get('/events/:incidentId/alerts', async (c) => {
  const orgId = c.get('orgId');
  const db = drizzle(c.env.db);
  const result = await db.select().from(alerts)
    .where(and(
      eq(alerts.incidentId, c.req.param('incidentId')),
      orgId ? eq(alerts.orgId, orgId) : sql`1=1`,
    )).all();
  return c.json({ items: result });
});

dashboardRoutes.post('/events/:incidentId/situation-report', async (c) => {
  const body = await c.req.json().catch(() => ({ format: 'text' } as Record<string, unknown>));
  const format = (body.format as string) ?? 'text';

  if (format === 'pdf') {
    return c.json({ error: { code: 'NOT_IMPLEMENTED', message: 'PDF situation reports are outside the MVP slice', request_id: c.get('requestId') } }, 501);
  }

  const orgId = c.get('orgId');
  const incidentId = c.req.param('incidentId');
  const db = drizzle(c.env.db);

  const [event, summary] = await Promise.all([
    db.select().from(disasterEvents).where(eq(disasterEvents.incidentId, incidentId)).limit(1).all(),
    (async () => {
      const orgFilter = orgId ? eq(incidentReports.orgId, orgId) : sql`1=1`;
      const [r, rb, t, s, a] = await Promise.all([
        db.select({ c: count() }).from(incidentReports).where(and(eq(incidentReports.incidentId, incidentId), orgFilter)).all(),
        db.select({ c: count() }).from(roadStatuses).where(and(eq(roadStatuses.incidentId, incidentId), eq(roadStatuses.status, 'blocked'), orgId ? eq(roadStatuses.orgId, orgId) : sql`1=1`)).all(),
        db.select({ c: count() }).from(tasks).where(and(eq(tasks.incidentId, incidentId), orgId ? eq(tasks.orgId, orgId) : sql`1=1`)).all(),
        db.select().from(shelters).where(and(eq(shelters.incidentId, incidentId), orgId ? eq(shelters.orgId, orgId) : sql`1=1`)).limit(20).all(),
        db.select().from(alerts).where(and(eq(alerts.incidentId, incidentId), orgId ? eq(alerts.orgId, orgId) : sql`1=1`)).limit(10).all(),
      ]);
      return { reports: r[0]?.c ?? 0, roadsBlocked: rb[0]?.c ?? 0, tasks: t[0]?.c ?? 0, shelters: s, alerts: a };
    })(),
  ]);

  const evt = event[0];
  const lines = [
    `SITUATION REPORT`,
    `Event: ${evt?.name ?? 'Unknown'}`,
    `Type: ${evt?.type ?? 'Unknown'}`,
    `Status: ${evt?.status ?? 'Unknown'}`,
    `Generated: ${new Date().toISOString()}`,
    ``,
    `SUMMARY:`,
    `  Total Reports: ${summary.reports}`,
    `  Roads Blocked: ${summary.roadsBlocked}`,
    `  Active Tasks: ${summary.tasks}`,
    `  Open Shelters: ${summary.shelters.length}`,
    `  Active Alerts: ${summary.alerts.length}`,
    ``,
    `SHELTERS:`,
    ...summary.shelters.map((s) => `  - ${s.name}: ${s.currentOccupancy}/${s.totalCapacity} (${s.status})`),
    ``,
    `ALERTS:`,
    ...summary.alerts.map((a) => `  - [${a.severity}] ${a.title}: ${a.message ?? 'No details'}`),
  ];

  return new Response(lines.join('\n'), {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
});
