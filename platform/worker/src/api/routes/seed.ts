import { Hono } from 'hono';
import type { AppEnv } from '../../middleware/requestId';
import { drizzle } from 'drizzle-orm/d1';
import {
  orgs, users, memberships, roles, rolePermissions, incidents,
  disasterEvents, roadStatuses, responseTeams, tasks,
  shelters, recommendations, areaAssessments, incidentReports,
} from '../../db/schema';
import { ulid, nowMs } from '../../lib/ulid';
import { sha256, writeAudit } from '../../lib/audit';
import { eq } from 'drizzle-orm';

export const seedRoutes = new Hono<AppEnv>();

const DEMO_USERS = [
  { email: 'admin@demo.disaster', name: 'Demo Admin', role: 'admin' },
  { email: 'emergency_manager@demo.disaster', name: 'Emergency Manager', role: 'emergency_manager' },
  { email: 'responder_coordinator@demo.disaster', name: 'Responder Coordinator', role: 'responder_coordinator' },
  { email: 'field_responder@demo.disaster', name: 'Field Responder', role: 'field_responder' },
  { email: 'shelter_manager@demo.disaster', name: 'Shelter Manager', role: 'shelter_manager' },
  { email: 'viewer@demo.disaster', name: 'Viewer', role: 'viewer' },
];

const RIVERTOWN_ROADS = [
  { name: 'Main Street', geometry: '{"type":"LineString","coordinates":[[-80.0,26.0],[-80.01,26.01]]}', status: 'open' as const },
  { name: 'River Road', geometry: '{"type":"LineString","coordinates":[[-80.02,26.02],[-80.03,26.03]]}', status: 'blocked' as const },
];

seedRoutes.post('/demo', async (c) => {
  const db = drizzle(c.env.db);
  const passwordHash = await sha256('demo1234');

  const existingOrg = await db.select().from(orgs).where(eq(orgs.slug, 'rivertown-demo')).limit(1).all();
  let orgId: string;
  let isNew = false;

  if (existingOrg[0]) {
    orgId = existingOrg[0].id;
  } else {
    orgId = ulid();
    await db.insert(orgs).values({
      id: orgId, name: 'Rivertown Demo', slug: 'rivertown-demo',
      kind: 'tenant', locked: false, createdAt: nowMs(), updatedAt: nowMs(),
    });
    isNew = true;
  }

  const roleId = ulid();
  if (isNew) {
    await db.insert(roles).values({ id: roleId, orgId, name: 'admin', system: true, createdAt: nowMs() });
    await db.insert(rolePermissions).values({ id: ulid(), roleId, action: '*', subject: '*' });

    for (const u of DEMO_USERS) {
      const userId = ulid();
      await db.insert(users).values({
        id: userId, orgId, email: u.email, name: u.name,
        role: u.role, status: 'active', passwordHash,
        createdAt: nowMs(), updatedAt: nowMs(),
      });
      await db.insert(memberships).values({ id: ulid(), userId, orgId, roleId, createdAt: nowMs() });
    }
  }

  const existingIncidents = await db.select().from(incidents)
    .where(eq(incidents.title, 'Rivertown Urban Flood')).limit(1).all();

  let incidentId: string;
  if (existingIncidents[0]) {
    incidentId = existingIncidents[0].id;
  } else {
    incidentId = ulid();
    await db.insert(incidents).values({
      id: incidentId, orgId, type: 'flood', severity: 'severe', status: 'active',
      title: 'Rivertown Urban Flood',
      description: 'Major river overflow affecting downtown Rivertown',
      geometry: JSON.stringify({
        type: 'Polygon',
        coordinates: [[[-80.05, 25.95], [-80.05, 26.10], [-79.90, 26.10], [-79.90, 25.95], [-80.05, 25.95]]],
      }),
      startsAt: nowMs(), createdAt: nowMs(), updatedAt: nowMs(),
    });
  }

  const existingEvents = await db.select().from(disasterEvents)
    .where(eq(disasterEvents.incidentId, incidentId)).limit(1).all();
  if (!existingEvents[0]) {
    await db.insert(disasterEvents).values({
      id: ulid(), orgId, incidentId,
      name: 'Rivertown Urban Flood', type: 'flood', status: 'active',
      description: 'Major river overflow affecting downtown Rivertown',
      affectedRegion: JSON.stringify({
        type: 'Polygon',
        coordinates: [[[-80.05, 25.95], [-80.05, 26.10], [-79.90, 26.10], [-79.90, 25.95], [-80.05, 25.95]]],
      }),
      startsAt: nowMs(),
      createdBy: 'system',
      createdAt: nowMs(), updatedAt: nowMs(),
    });
  }

  const existingRoads = await db.select().from(roadStatuses)
    .where(eq(roadStatuses.incidentId, incidentId)).limit(1).all();
  if (existingRoads.length === 0) {
    for (const road of RIVERTOWN_ROADS) {
      await db.insert(roadStatuses).values({
        id: ulid(), orgId, incidentId,
        roadName: road.name, geometry: road.geometry,
        status: road.status, reason: road.status === 'blocked' ? 'Flood water covering road' : null,
        confidenceScore: 0.9, visibility: 'internal', reviewStatus: 'reviewed',
        createdAt: nowMs(), updatedAt: nowMs(),
      });
    }
  }

  const existingShelters = await db.select().from(shelters)
    .where(eq(shelters.incidentId, incidentId)).limit(1).all();
  if (existingShelters.length === 0) {
    await db.insert(shelters).values({
      id: ulid(), orgId, incidentId,
      name: 'Rivertown Community Center',
      geometry: JSON.stringify({ type: 'Point', coordinates: [-80.0, 26.05] }),
      totalCapacity: 500, currentOccupancy: 120,
      foodStatus: 'adequate', waterStatus: 'adequate',
      medicalSupport: true, accessibilitySupport: true,
      status: 'open', visibility: 'public', reviewStatus: 'official',
      createdAt: nowMs(), updatedAt: nowMs(),
    });
  }

  const existingTeams = await db.select().from(responseTeams)
    .where(eq(responseTeams.incidentId, incidentId)).limit(1).all();
  let teamId: string;
  if (existingTeams.length === 0) {
    teamId = ulid();
    await db.insert(responseTeams).values({
      id: teamId, orgId, incidentId,
      name: 'Alpha Rescue Team', teamType: 'search_rescue',
      currentLocation: JSON.stringify({ type: 'Point', coordinates: [-80.01, 26.04] }),
      status: 'available', capacity: 6,
      visibility: 'internal', reviewStatus: 'reviewed',
      createdAt: nowMs(), updatedAt: nowMs(),
    });
  } else {
    teamId = (existingTeams[0] ?? { id: ulid() }).id;
  }

  const existingTasks = await db.select().from(tasks)
    .where(eq(tasks.incidentId, incidentId)).limit(1).all();
  let taskId: string;
  if (existingTasks.length === 0) {
    taskId = ulid();
    await db.insert(tasks).values({
      id: taskId, orgId, incidentId,
      assignedTeamId: teamId,
      title: 'Evacuate residents from River Road',
      description: 'Conduct evacuation of residents along River Road due to flooding',
      location: JSON.stringify({ type: 'Point', coordinates: [-80.02, 26.02] }),
      priority: 'high', status: 'assigned',
      visibility: 'internal', reviewStatus: 'reviewed',
      createdAt: nowMs(), updatedAt: nowMs(),
    });
  } else {
    taskId = (existingTasks[0] ?? { id: ulid() }).id;
  }

  const existingAreas = await db.select().from(areaAssessments)
    .where(eq(areaAssessments.incidentId, incidentId)).limit(1).all();
  if (existingAreas.length === 0) {
    await db.insert(areaAssessments).values({
      id: ulid(), orgId, incidentId,
      areaName: 'Downtown Rivertown',
      geometry: JSON.stringify({
        type: 'Polygon',
        coordinates: [[[-80.02, 26.0], [-80.02, 26.05], [-79.98, 26.05], [-79.98, 26.0], [-80.02, 26.0]]],
      }),
      hazardScore: 75, exposureScore: 80, accessScore: 40,
      infrastructureScore: 60, vulnerabilityScore: 70,
      trendScore: 65, reportScore: 55,
      overallPriorityScore: 68,
      priorityLevel: 'high',
      summary: 'Downtown area severely affected by flooding with high population exposure.',
      visibility: 'internal', reviewStatus: 'reviewed',
      createdAt: nowMs(), updatedAt: nowMs(),
    });
  }

  const existingRecs = await db.select().from(recommendations)
    .where(eq(recommendations.incidentId, incidentId)).limit(1).all();
  if (existingRecs.length === 0) {
    await db.insert(recommendations).values({
      id: ulid(), orgId, incidentId,
      recommendationType: 'evacuation',
      title: 'Evacuate Downtown Rivertown',
      description: 'Initiate evacuation of downtown area due to severe flooding',
      reasoning: 'High hazard score combined with high population exposure and limited access routes.',
      confidenceScore: 0.85,
      urgency: 'high',
      status: 'draft',
      visibility: 'internal', reviewStatus: 'draft',
      createdAt: nowMs(), updatedAt: nowMs(),
    });
  }

  const existingReports = await db.select().from(incidentReports)
    .where(eq(incidentReports.incidentId, incidentId)).limit(1).all();
  if (existingReports.length === 0) {
    await db.insert(incidentReports).values({
      id: ulid(), orgId, incidentId,
      reporterType: 'field_responder',
      reportCategory: 'flooding',
      description: 'Water rising rapidly at 3rd Street and Main. Several vehicles submerged.',
      geometry: JSON.stringify({ type: 'Point', coordinates: [-80.0, 26.0] }),
      urgency: 'high',
      verificationStatus: 'unverified',
      confidenceScore: 0.7,
      visibility: 'internal', reviewStatus: 'draft',
      createdAt: nowMs(), updatedAt: nowMs(),
    });
  }

  if (isNew) {
    await writeAudit({ db, orgId, incidentId, actor: 'system', action: 'seed.demo', entity: `org:${orgId}`, after: { users: DEMO_USERS.length, incidentId } });
  }

  const userCount = await db.select().from(users).where(eq(users.orgId, orgId)).all();
  const roadCount = await db.select().from(roadStatuses).where(eq(roadStatuses.incidentId, incidentId)).all();
  const teamCount = await db.select().from(responseTeams).where(eq(responseTeams.incidentId, incidentId)).all();
  const taskCount = await db.select().from(tasks).where(eq(tasks.incidentId, incidentId)).all();

  return c.json({
    orgId,
    incidentId,
    event: 'Rivertown Urban Flood',
    users: userCount.length,
    roads: roadCount.length,
    teams: teamCount.length,
    tasks: taskCount.length,
    login: { email: 'admin@demo.disaster', password: 'demo1234' },
  }, 201);
});
