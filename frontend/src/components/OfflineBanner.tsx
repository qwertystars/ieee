import { WifiOff, RefreshCw } from 'lucide-react';
import { useOffline } from '../lib/hooks/useOffline';

export default function OfflineBanner() {
  const { isOffline, pendingSyncs } = useOffline();

  if (!isOffline) return null;

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-amber-900/90 backdrop-blur-sm border border-amber-700 text-amber-100 px-4 py-2.5 rounded-lg shadow-lg">
      <WifiOff size={18} className="text-amber-400" />
      <span className="text-sm font-medium">You are offline. Changes will sync when connection is restored.</span>
      {pendingSyncs > 0 && (
        <span className="flex items-center gap-1.5 text-xs bg-amber-800 px-2 py-0.5 rounded-full">
          <RefreshCw size={12} className="animate-spin" />
          {pendingSyncs} pending
        </span>
      )}
    </div>
  );
}
