import { useEffect, useState } from 'react';
import { api } from '../lib/api';

interface EventItem { id: string; name: string; type: string; status: string; incidentId: string }
interface Summary {
  total_reports: number; roads_blocked: number; pending_tasks: number;
  shelters_open: number; alerts_active: number; critical_areas: number;
  high_areas: number; last_updated: number;
}
interface Recommendation { id: string; title: string; status: string; urgency: string }
interface Shelter { id: string; name: string; status: string; currentOccupancy: number; totalCapacity: number }

export default function Dashboard() {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [selectedIncident, setSelectedIncident] = useState<string | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [shelters, setShelters] = useState<Shelter[]>([]);
  const [sitrep, setSitrep] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getEvents().then((r) => {
      setEvents(r.items);
      const active = r.items.find((e) => e.status === 'active');
      if (active) setSelectedIncident(active.incidentId);
    }).catch((e) => setError(e instanceof Error ? e.message : 'Failed to load events'));
  }, []);

  useEffect(() => {
    if (!selectedIncident) return;
    const poll = () => {
      Promise.all([
        api.getDashboardSummary(selectedIncident),
        api.getRecommendations(selectedIncident),
        api.getShelters(selectedIncident),
      ]).then(([s, recs, sh]) => {
        setSummary(s);
        setRecommendations(recs.items as Recommendation[]);
        setShelters(sh.items as Shelter[]);
      }).catch((e) => setError(e instanceof Error ? e.message : 'Failed to load dashboard'));
    };
    poll();
    const interval = setInterval(poll, 15000);
    return () => clearInterval(interval);
  }, [selectedIncident]);

  async function handleApprove(recId: string) {
    if (!selectedIncident) return;
    await api.approveRecommendation(selectedIncident, recId);
    const recs = await api.getRecommendations(selectedIncident);
    setRecommendations(recs.items as Recommendation[]);
  }

  async function handleSitRep() {
    if (!selectedIncident) return;
    const text = await api.getSituationReport(selectedIncident, 'text');
    setSitrep(text);
  }

  if (error) return <div className="p-4 text-red-400">{error}</div>;

  return (
    <div className="flex h-screen flex-col bg-slate-900 text-white">
      <header className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
        <h1 className="text-lg font-bold">Command Center Dashboard</h1>
        <div className="flex items-center gap-3">
          <select
            value={selectedIncident ?? ''}
            onChange={(e) => setSelectedIncident(e.target.value)}
            className="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-sm"
          >
            {events.map((e) => <option key={e.id} value={e.incidentId}>{e.name}</option>)}
          </select>
          <button onClick={handleSitRep} className="rounded bg-blue-600 px-3 py-1 text-sm">Sit Rep</button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-auto p-4">
          {summary && (
            <div className="grid grid-cols-4 gap-3">
              <KPI label="Reports" value={summary.total_reports} />
              <KPI label="Roads Blocked" value={summary.roads_blocked} />
              <KPI label="Pending Tasks" value={summary.pending_tasks} />
              <KPI label="Open Shelters" value={summary.shelters_open} />
              <KPI label="Active Alerts" value={summary.alerts_active} />
              <KPI label="Critical Areas" value={summary.critical_areas} />
              <KPI label="High Areas" value={summary.high_areas} />
            </div>
          )}
          {sitrep && (
            <pre className="mt-4 overflow-auto rounded bg-slate-800 p-4 text-sm text-slate-300">{sitrep}</pre>
          )}
        </div>

        <aside className="w-80 overflow-auto border-l border-slate-700 p-4">
          <h2 className="mb-2 text-sm font-semibold text-slate-400">Recommendations</h2>
          {recommendations.map((r) => (
            <div key={r.id} className="mb-2 rounded bg-slate-800 p-3">
              <p className="text-sm font-medium">{r.title}</p>
              <div className="mt-1 flex items-center justify-between">
                <span className="text-xs text-slate-400">{r.status} · {r.urgency}</span>
                {r.status === 'draft' && (
                  <button onClick={() => handleApprove(r.id)} className="rounded bg-green-700 px-2 py-0.5 text-xs">Approve</button>
                )}
              </div>
            </div>
          ))}
          <h2 className="mb-2 mt-4 text-sm font-semibold text-slate-400">Shelters</h2>
          {shelters.map((s) => (
            <div key={s.id} className="mb-2 rounded bg-slate-800 p-3">
              <p className="text-sm font-medium">{s.name}</p>
              <p className="text-xs text-slate-400">{s.currentOccupancy}/{s.totalCapacity} · {s.status}</p>
            </div>
          ))}
        </aside>
      </div>
    </div>
  );
}

function KPI({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-slate-800 p-3">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  );
}
