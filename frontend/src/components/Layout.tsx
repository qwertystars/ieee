import { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Home, AlertTriangle, Map, Users, Building2, Radio, FileText, Settings } from 'lucide-react';
import OfflineBanner from './OfflineBanner';
import Sidebar from './Sidebar';
import Header from './Header';

// TODO: Phase 2 — add CommandPalette + InstallPrompt once their skipped deps
// (cmdk / vite-plugin-pwa) are decided on.

const navItems = [
  { path: '/dashboard', icon: Home, label: 'Dashboard' },
  { path: '/incidents', icon: AlertTriangle, label: 'Incidents' },
  { path: '/map', icon: Map, label: 'Map' },
  { path: '/tasks', icon: Users, label: 'Tasks' },
  { path: '/shelters', icon: Building2, label: 'Shelters' },
  { path: '/communications', icon: Radio, label: 'Communications' },
  { path: '/reports', icon: FileText, label: 'Reports' },
  { path: '/settings', icon: Settings, label: 'Settings' },
];

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();
  return (
    <div className="flex h-screen">
      <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col">
        <div className="p-4 border-b border-slate-800">
          <h1 className="text-lg font-bold text-red-500">DRC Command</h1>
        </div>
        <nav className="flex-1 p-2">
          {navItems.map(({ path, icon: Icon, label }) => (
            <Link
              key={path}
              to={path}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg mb-1 ${
                location.pathname === path
                  ? 'bg-red-600/20 text-red-400'
                  : 'text-slate-400 hover:bg-slate-800'
              }`}
            >
              <Icon size={18} />
              <span>{label}</span>
            </Link>
          ))}
        </nav>
      </aside>
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto bg-slate-950">{children}</main>
      </div>
      <OfflineBanner />
    </div>
  );
}
