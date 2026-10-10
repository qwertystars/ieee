import { useState } from 'react'
import { OperationsPanel } from './OperationsPanel'

export function DronePanel() {
  const [showControls, setShowControls] = useState(false)
  const base = import.meta.env.VITE_DRONE_URL ?? 'http://192.168.4.1/'
  const mixedContent = window.location.protocol === 'https:' && base.startsWith('http:')
  return (
    <OperationsPanel title="Drone flight controls" status="Direct WiFi connection">
      <p className="text-sm text-slate-300">Pair your controller with the phone, then join the drone’s esp32-drone WiFi network.</p>
      <dl className="my-4 grid grid-cols-2 gap-3 text-xs">
        {[
          ['Right trigger', 'Increase throttle'], ['Left trigger', 'Decrease throttle'],
          ['Left stick', 'Forward / back / left / right'], ['Right stick', 'Yaw / spin'],
          ['Start', 'Arm at zero throttle'], ['B / Circle', 'STOP'],
        ].map(([control, action]) => <div key={control}><dt className="text-slate-500">{control}</dt><dd className="mt-1 text-slate-200">{action}</dd></div>)}
      </dl>
      <p className="mb-4 text-xs text-slate-400">Manual motor control: releasing a trigger holds throttle, not altitude.</p>
      <a href={base} target="_blank" rel="noopener noreferrer" className="inline-block rounded bg-cyan-700 px-4 py-2 text-sm text-white">Open drone controller</a>
      {!mixedContent && <button type="button" onClick={() => setShowControls(v => !v)} className="ml-3 rounded border border-slate-600 px-3 py-2 text-sm text-slate-200">{showControls ? 'Close' : 'Show'} embedded controls</button>}
      {mixedContent && <p className="mt-3 text-xs text-slate-400">Open the controller in its own tab when using this dashboard over HTTPS.</p>}
      {showControls && <iframe src={base} title="ESP32 drone controller" allow="gamepad" className="mt-4 h-[600px] w-full rounded-lg border border-slate-700" />}
      <p className="mt-3 text-xs text-slate-500">The controller shows connection and flight telemetry after you connect. Opening this panel does not arm the drone.</p>
    </OperationsPanel>
  )
}
