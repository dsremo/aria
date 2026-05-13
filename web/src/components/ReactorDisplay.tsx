/**
 * Reactor Status Display — fusion reactor health + thermal output.
 *
 * Shows reactor online/offline status, duty cycle, first-wall temperature,
 * thermal power output, health percentage, and failure mode (if any).
 * Uses /api/inspect/part/reactor_engine for detailed part data.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type PartSnapshot, type PropThermalState } from '../api/aria';

export function ReactorDisplay() {
  const [reactor, setReactor] = useState<PartSnapshot | null>(null);
  const [thermal, setThermal] = useState<PropThermalState | null>(null);

  useEffect(() => {
    const refreshR = () => ariaApi.inspectPart('reactor_engine').then(setReactor).catch(() => {});
    const refreshT = () => ariaApi.propulsionThermal().then(setThermal).catch(() => {});
    refreshR(); refreshT();
    const t1 = setInterval(refreshR, 3000);
    const t2 = setInterval(refreshT, 3000);
    return () => { clearInterval(t1); clearInterval(t2); };
  }, []);

  if (!reactor) return <div className="p-4 text-sm text-ui-text-dim">Loading reactor data...</div>;

  const tempK = reactor.temperature_k ?? 0;
  const tempC = tempK > 0 ? tempK - 273.15 : 0;
  const dutyPct = reactor.duty_cycle_pct ?? 0;
  const powerW = reactor.power_draw_w ?? 0;

  const statusColor = !reactor.operational ? 'text-sev-crit' : dutyPct > 80 ? 'text-sev-warn' : 'text-sev-ok';
  const statusBg = !reactor.operational ? 'bg-sev-crit/30 border-sev-crit' : 'bg-sev-ok/20 border-sev-ok/50';

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Fusion Reactor (D/He-3)</h2>
        <p className="text-xs text-ui-text-dim">{reactor.description}</p>
      </div>

      {/* Main status */}
      <div className={`p-6 rounded-xl border mb-4 text-center ${statusBg}`}>
        <div className={`text-4xl font-bold ${statusColor}`}>
          {reactor.operational ? 'ONLINE' : 'OFFLINE'}
        </div>
        {reactor.failure_mode && (
          <div className="text-sm text-sev-crit mt-2">{reactor.failure_mode}</div>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
        {/* Health */}
        <GaugeCard label="Health" value={reactor.health_pct} unit="%" max={100}
                   color={reactor.health_pct > 80 ? '#22c55e' : reactor.health_pct > 50 ? '#eab308' : '#ef4444'} />
        {/* Duty cycle */}
        <GaugeCard label="Duty Cycle" value={dutyPct} unit="%" max={100}
                   color={dutyPct < 50 ? '#06b6d4' : dutyPct < 80 ? '#eab308' : '#ef4444'} />
        {/* Temperature */}
        <GaugeCard label="First-Wall Temp" value={tempC} unit="°C" max={600}
                   color={tempC < 300 ? '#22c55e' : tempC < 500 ? '#eab308' : '#ef4444'} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Power output */}
        <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-wider text-ui-text-faint font-bold mb-2">Power Output</div>
          <div className="text-2xl font-bold font-mono text-ui-accent mb-1">
            {powerW >= 1e9 ? `${(powerW / 1e9).toFixed(1)} GW` :
             powerW >= 1e6 ? `${(powerW / 1e6).toFixed(1)} MW` :
             powerW >= 1e3 ? `${(powerW / 1e3).toFixed(0)} kW` :
             `${powerW.toFixed(0)} W`}
          </div>
          <div className="text-[9px] text-ui-text-faint">Thermal power output</div>
          <div className="text-xs text-ui-text-dim mt-2">
            Mass: {(reactor.mass_kg / 1000).toFixed(0)} t · Material: {reactor.material}
          </div>
        </div>

        {/* Propulsion thermal feedback */}
        {thermal && (
          <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-4">
            <div className="text-[10px] uppercase tracking-wider text-ui-text-faint font-bold mb-2">Propulsion Thermal</div>
            <div className="space-y-1.5 text-xs">
              <div className="flex justify-between">
                <span className="text-ui-text-dim">Thrust requested</span>
                <span className="text-ui-text font-mono">{(thermal.thrust.requested_frac * 100).toFixed(0)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-ui-text-dim">Thrust actual</span>
                <span className={`font-mono ${thermal.thrust.throttle_active ? 'text-sev-warn' : 'text-ui-text'}`}>
                  {(thermal.thrust.actual_frac * 100).toFixed(0)}%
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-ui-text-dim">Plume back-rad</span>
                <span className="text-ui-text font-mono">{(thermal.thermal.back_radiated_w / 1e6).toFixed(2)} MW</span>
              </div>
              <div className="flex justify-between">
                <span className="text-ui-text-dim">Radiator margin</span>
                <span className={`font-mono ${thermal.thermal.margin_w > 0 ? 'text-sev-ok' : 'text-sev-crit'}`}>
                  {(thermal.thermal.margin_w / 1e6).toFixed(1)} MW
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-ui-text-dim">Hull aft cap temp</span>
                <span className="text-ui-text font-mono">{thermal.thermal.hull_aft_cap_temp_k.toFixed(0)} K</span>
              </div>
              {thermal.thrust.throttle_active && (
                <div className="mt-2 p-2 rounded bg-sev-warn/40 border border-sev-warn text-sev-warn text-[10px]">
                  AUTO-THROTTLE ACTIVE — thermal margin negative at requested thrust
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Sources */}
      <div className="mt-3 text-[9px] text-ui-text-faint">
        Sources: {reactor.sources.slice(0, 3).join(' · ')}
      </div>
    </div>
  );
}

function GaugeCard({ label, value, unit, max, color }:
  { label: string; value: number; unit: string; max: number; color: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-3 text-center">
      <div className="text-[9px] uppercase tracking-wider text-ui-text-faint mb-1">{label}</div>
      <div className="relative w-20 h-20 mx-auto mb-1">
        <svg viewBox="0 0 80 80" className="w-full h-full">
          <circle cx={40} cy={40} r={34} fill="none" stroke="#1e293b" strokeWidth={6} />
          <circle cx={40} cy={40} r={34} fill="none" stroke={color} strokeWidth={6}
                  strokeDasharray={`${pct * 2.14} 214`}
                  strokeLinecap="round" transform="rotate(-90 40 40)" />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-sm font-bold font-mono text-ui-text">{value.toFixed(0)}</span>
        </div>
      </div>
      <div className="text-[9px] text-ui-text-faint">{unit}</div>
    </div>
  );
}
