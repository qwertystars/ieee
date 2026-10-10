// Explicit, visible parameter presets for the digital-twin fault controls.
export const SIMULATION_FAULTS: { type: string; label: string; kwargs: Record<string, string | number> }[] = [
  { type: 'battery_drain', label: 'Battery drain (20%)', kwargs: { rate: 20 } },
  { type: 'sensor_degradation', label: 'Degrade thermal sensor', kwargs: { sensor: 'thermal' } },
  { type: 'connectivity_loss', label: 'Link loss (30 seconds)', kwargs: { duration: 30 } },
  { type: 'blocked_route', label: 'Blocked route (turn 90°)', kwargs: { alternative_heading: 90 } },
  { type: 'thermal_hotspot', label: 'Thermal hotspot (60°C)', kwargs: { temperature: 60 } },
  { type: 'human_heat_signature', label: 'Simulated human heat signature', kwargs: { location: 'scenario-target' } },
  { type: 'water_depth', label: 'Water depth (2 m)', kwargs: { depth: 2 } },
  { type: 'motion', label: 'Motion heading (180°)', kwargs: { direction: 180 } },
  { type: 'vibration', label: 'Vibration (5 m/s²)', kwargs: { intensity: 5 } },
  { type: 'environmental_temp', label: 'Environment (40°C)', kwargs: { temp: 40 } },
]
