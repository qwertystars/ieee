import { useEffect, useState } from 'react';
import { api } from './lib/api';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import FieldResponder from './pages/FieldResponder';

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [route, setRoute] = useState(window.location.hash.slice(1) || '/dashboard');

  useEffect(() => {
    if (!api.getToken()) { setAuthed(false); return; }
    api.me().then(() => setAuthed(true)).catch(() => { setAuthed(false); api.setToken(null); });
  }, []);

  useEffect(() => {
    const onHash = () => setRoute(window.location.hash.slice(1) || '/dashboard');
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  if (authed === null) return <div className="flex h-screen items-center justify-center bg-slate-900 text-slate-400">Loading...</div>;
  if (!authed) return <Login />;

  const nav = (
    <nav className="flex gap-2 border-b border-slate-700 bg-slate-800 px-4 py-2">
      <a href="#/dashboard" className={`rounded px-3 py-1 text-sm ${route === '/dashboard' ? 'bg-blue-600 text-white' : 'text-slate-400'}`}>Dashboard</a>
      <a href="#/field" className={`rounded px-3 py-1 text-sm ${route === '/field' ? 'bg-blue-600 text-white' : 'text-slate-400'}`}>Field Responder</a>
      <button onClick={() => { api.logout(); window.location.reload(); }} className="ml-auto rounded px-3 py-1 text-sm text-red-400">Logout</button>
    </nav>
  );

  if (route === '/field') {
    return <div className="flex h-screen flex-col bg-slate-900">{nav}<FieldResponder /></div>;
  }
  return <div className="flex h-screen flex-col bg-slate-900">{nav}<Dashboard /></div>;
}
