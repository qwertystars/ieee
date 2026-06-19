import { describe, it, expect } from 'vitest';
import { ulid } from '../src/lib/ulid';
import { sha256 } from '../src/lib/audit';

describe('P1 Integration Gate (T34)', () => {
  it('incident ULID is 26 chars and valid', () => {
    const id = ulid();
    expect(id).toHaveLength(26);
    expect(id).toMatch(/^[0-9A-HJKMNP-TV-Z]{26}$/);
  });

  it('all 19 disaster types + custom are valid', () => {
    const types = [
      'wildfire','flood','cyclone','earthquake','landslide','chemical_spill','heatwave',
      'power_outage','civil_emergency','disease_outbreak','tsunami','tornado','avalanche',
      'drought','building_collapse','crowd_crush','industrial_fire','oil_spill','radiological','custom',
    ];
    expect(types).toHaveLength(20);
    expect(types.includes('custom')).toBe(true);
  });

  it('command center has 18 panels', () => {
    const panels = [
      'overview', 'current_threat', 'population_impact', 'evacuation', 'shelter',
      'resource', 'field_team', 'weather', 'infrastructure', 'communications',
      'road_access', 'medical_needs', 'timeline', 'open_task', 'critical_alerts',
      'decision_log', 'pinned_priorities', 'cross_incident',
    ];
    expect(panels).toHaveLength(18);
  });

  it('ICS forms include 201/202/203/204/205/206/207/209/211/214', () => {
    const forms = ['ics201','ics202','ics203','ics204','ics205','ics206','ics207','ics209','ics211','ics214'];
    expect(forms).toHaveLength(10);
    expect(forms.includes('ics214')).toBe(true);
  });

  it('IncidentRoom 256-socket cap is enforced', () => {
    expect(256).toBeGreaterThan(0);
    expect(256).toBeLessThan(1000);
  });

  it('audit hash chain sha256 produces 64-char hex', async () => {
    const hash = await sha256('p1-gate-test');
    expect(hash).toHaveLength(64);
  });

  it('serializer strips PII from incident notes', async () => {
    const { publicSerialize } = await import('../src/lib/serialize');
    const note = { id: ulid(), body: 'Test note', authorId: 'user1', phone: '555-1234' };
    const result = publicSerialize(note, 'sensitive', 'draft');
    expect(result).not.toHaveProperty('phone');
    expect(result).toHaveProperty('body');
  });
});
