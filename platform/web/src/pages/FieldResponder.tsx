import { useEffect, useState } from 'react';
import { api } from '../lib/api';

interface Task { id: string; title: string; status: string; priority: string }
interface Road { id: string; roadName: string; status: string }
interface EventItem { id: string; name: string; incidentId: string }

type Tab = 'tasks' | 'report' | 'roads';

export default function FieldResponder() {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('tasks');
  const [tasks, setTasks] = useState<Task[]>([]);
  const [roads, setRoads] = useState<Road[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [reportCategory, setReportCategory] = useState('flooding');
  const [reportDesc, setReportDesc] = useState('');
  const [reportLat, setReportLat] = useState('26.0');
  const [reportLng, setReportLng] = useState('-80.0');
  const [reportUrgency, setReportUrgency] = useState('high');
  const [submitMsg, setSubmitMsg] = useState<string | null>(null);

  useEffect(() => {
    api.getEvents().then((r) => {
      setEvents(r.items);
      const active = r.items.find((e) => e.status === 'active') ?? r.items[0];
      if (active) setIncidentId(active.incidentId);
    }).catch((e) => setError(e instanceof Error ? e.message : 'Failed to load events'));
  }, []);

  useEffect(() => {
    if (!incidentId) return;
    refreshData();
    const interval = setInterval(refreshData, 15000);
    return () => clearInterval(interval);
  }, [incidentId]);

  function refreshData() {
    if (!incidentId) return;
    Promise.all([
      api.getTasks(incidentId),
      api.getRoads(incidentId),
    ]).then(([t, r]) => {
      setTasks(t.items as Task[]);
      setRoads(r.items as Road[]);
    }).catch((e) => setError(e instanceof Error ? e.message : 'Failed to load data'));
  }

  async function handleSubmitReport(e: React.FormEvent) {
    e.preventDefault();
    if (!incidentId) return;
    setSubmitMsg(null);
    try {
      await api.createReport(incidentId, {
        reporterType: 'field_responder',
        reportCategory,
        description: reportDesc,
        geometry: { type: 'Point', coordinates: [parseFloat(reportLng), parseFloat(reportLat)] },
        urgency: reportUrgency,
      });
      setSubmitMsg('Report submitted successfully');
      setReportDesc('');
      refreshData();
    } catch (err) {
      setSubmitMsg(err instanceof Error ? err.message : 'Submit failed');
    }
  }

  async function handleTaskStatus(taskId: string, status: string) {
    await api.updateTaskStatus(taskId, status);
    refreshData();
  }

  async function handleRoadStatus(roadId: string, status: string) {
    await api.updateRoadStatus(roadId, { status, reason: `Field update: ${status}`, confidenceScore: 0.9 });
    refreshData();
  }

  if (error) return <div className="p-4 text-red-400">{error}</div>;

  return (
    <div className="flex min-h-screen flex-col bg-slate-900 text-white">
      <header className="border-b border-slate-700 px-4 py-3">
        <h1 className="text-lg font-bold">Field Responder</h1>
        <select
          value={incidentId ?? ''}
          onChange={(e) => setIncidentId(e.target.value)}
          className="mt-1 rounded border border-slate-600 bg-slate-800 px-2 py-1 text-sm"
        >
          {events.map((e) => <option key={e.id} value={e.incidentId}>{e.name}</option>)}
        </select>
      </header>

      <nav className="flex border-b border-slate-700">
        {(['tasks', 'report', 'roads'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 py-2 text-sm font-medium capitalize ${tab === t ? 'border-b-2 border-blue-500 text-blue-400' : 'text-slate-400'}`}
          >
            {t}
          </button>
        ))}
      </nav>

      <div className="flex-1 overflow-auto p-4">
        {tab === 'tasks' && (
          <div className="space-y-2">
            {tasks.length === 0 && <p className="text-sm text-slate-500">No tasks assigned</p>}
            {tasks.map((t) => (
              <div key={t.id} className="rounded bg-slate-800 p-3">
                <p className="font-medium">{t.title}</p>
                <div className="mt-1 flex items-center justify-between">
                  <span className="text-xs text-slate-400">{t.status} · {t.priority}</span>
                  {t.status === 'assigned' && (
                    <button onClick={() => handleTaskStatus(t.id, 'accepted')} className="rounded bg-green-700 px-2 py-0.5 text-xs">Accept</button>
                  )}
                  {t.status === 'accepted' && (
                    <button onClick={() => handleTaskStatus(t.id, 'en_route')} className="rounded bg-blue-700 px-2 py-0.5 text-xs">En Route</button>
                  )}
                  {t.status === 'en_route' && (
                    <button onClick={() => handleTaskStatus(t.id, 'on_site')} className="rounded bg-blue-700 px-2 py-0.5 text-xs">On Site</button>
                  )}
                  {t.status === 'on_site' && (
                    <button onClick={() => handleTaskStatus(t.id, 'completed')} className="rounded bg-green-700 px-2 py-0.5 text-xs">Complete</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === 'report' && (
          <form onSubmit={handleSubmitReport} className="space-y-3">
            <div>
              <label className="mb-1 block text-sm text-slate-300">Category</label>
              <select value={reportCategory} onChange={(e) => setReportCategory(e.target.value)} className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2">
                <option value="flooding">Flooding</option>
                <option value="trapped_person">Trapped Person</option>
                <option value="road_blocked">Road Blocked</option>
                <option value="power_outage">Power Outage</option>
                <option value="medical_emergency">Medical Emergency</option>
                <option value="fire">Fire</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="mb-1 block text-sm text-slate-300">Latitude</label>
                <input type="text" value={reportLat} onChange={(e) => setReportLat(e.target.value)} className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2" />
              </div>
              <div>
                <label className="mb-1 block text-sm text-slate-300">Longitude</label>
                <input type="text" value={reportLng} onChange={(e) => setReportLng(e.target.value)} className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2" />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-sm text-slate-300">Urgency</label>
              <select value={reportUrgency} onChange={(e) => setReportUrgency(e.target.value)} className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm text-slate-300">Description</label>
              <textarea value={reportDesc} onChange={(e) => setReportDesc(e.target.value)} className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2" rows={3} />
            </div>
            {submitMsg && <p className="text-sm text-slate-400">{submitMsg}</p>}
            <button type="submit" className="w-full rounded bg-blue-600 py-2 font-medium">Submit Report</button>
          </form>
        )}

        {tab === 'roads' && (
          <div className="space-y-2">
            {roads.length === 0 && <p className="text-sm text-slate-500">No road data</p>}
            {roads.map((r) => (
              <div key={r.id} className="rounded bg-slate-800 p-3">
                <div className="flex items-center justify-between">
                  <p className="font-medium">{r.roadName}</p>
                  <span className="text-xs text-slate-400">{r.status}</span>
                </div>
                <div className="mt-2 flex gap-2">
                  <button onClick={() => handleRoadStatus(r.id, 'blocked')} className="rounded bg-red-700 px-2 py-0.5 text-xs">Block</button>
                  <button onClick={() => handleRoadStatus(r.id, 'open')} className="rounded bg-green-700 px-2 py-0.5 text-xs">Open</button>
                  <button onClick={() => handleRoadStatus(r.id, 'dangerous')} className="rounded bg-orange-700 px-2 py-0.5 text-xs">Dangerous</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
