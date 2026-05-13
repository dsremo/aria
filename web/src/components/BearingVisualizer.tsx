/**
 * Bearing Status Visualizer — habitat ring bearing mode + diagnostics.
 *
 * Shows magnetic primary vs roller backup bearing status with:
 * - Mode indicator (MAGNETIC / ROLLER / OFF)
 * - Maglev coil temperature + powered hours
 * - Roller L10 life consumed + EHL film thickness
 * - Trip/restore controls for operator drills
 *
 * Polls /api/bearing every 2s.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type BearingState } from '../api/aria';

export function BearingVisualizer() {
  const [b, setB] = useState<BearingState | null>(null);

  useEffect(() => {
    const refresh = () => ariaApi.bearing().then(setB).catch(() => {});
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);

  if (!b) return <div className="p-4 text-sm text-ui-text-dim">Loading bearing data...</div>;

  const trip = async () => setB(await ariaApi.bearingTrip('operator drill'));
  const restore = async () => setB(await ariaApi.bearingRestore());

  const modeColor = b.mode === 'magnetic' ? 'text-sev-ok' : b.mode === 'roller' ? 'text-sev-warn' : 'text-sev-crit';
  const modeBg = b.mode === 'magnetic' ? 'bg-sev-ok/30 border-sev-ok/50' : b.mode === 'roller' ? 'bg-sev-warn/30 border-sev-warn/50' : 'bg-sev-crit/30 border-sev-crit/50';

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Habitat Ring Bearing System</h2>
        <p className="text-xs text-ui-text-dim">
          Magnetic primary + roller backup. Ring mass: {(b.config.ring_mass_kg / 1e6).toFixed(1)} kt ·
          {b.config.ring_rpm.toFixed(2)} RPM · R = {b.config.ring_radius_m} m
        </p>
      </div>

      {/* Mode indicator — large and prominent */}
      <div className={`p-6 rounded-xl border mb-4 text-center ${modeBg}`}>
        <div className="text-[10px] uppercase tracking-widest text-ui-text-faint mb-2">Bearing Mode</div>
        <div className={`text-4xl font-bold ${modeColor}`}>{b.mode.toUpperCase()}</div>
        <div className="text-sm text-ui-text-dim mt-1">
          {b.mode === 'magnetic' ? 'Superconducting maglev — frictionless, unlimited life' :
           b.mode === 'roller' ? 'Emergency roller backup — limited L10 life' :
           'BEARING OFFLINE — ring not rotating'}
        </div>
        {!b.operational && (
          <div className="mt-2 text-sev-crit font-bold">NON-OPERATIONAL</div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Maglev status */}
        <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-wider text-sev-ok font-bold mb-3">
            Magnetic Levitation (Primary)
          </div>
          <div className="space-y-2">
            <StatusRow label="Powered" value={b.maglev.powered ? 'ON' : 'OFF'}
                       color={b.maglev.powered ? 'text-sev-ok' : 'text-sev-crit'} />
            <StatusRow label="Coil temperature" value={`${b.maglev.winding_temp_k.toFixed(0)} K`}
                       color={b.maglev.winding_temp_k < 100 ? 'text-sev-ok' : 'text-sev-warn'} />
            <StatusRow label="Powered hours" value={`${b.maglev.total_powered_hours.toFixed(0)} hr`} />
            <StatusRow label="Trip rate" value={`${b.maglev.trip_rate_per_yr.toFixed(4)} /yr`} />
          </div>
        </div>

        {/* Roller status */}
        <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-wider text-sev-warn font-bold mb-3">
            Roller Backup (Emergency)
          </div>
          <div className="space-y-2">
            <StatusRow label="Revolutions" value={b.roller.revolutions.toLocaleString()} />
            <div>
              <div className="flex justify-between text-xs mb-0.5">
                <span className="text-ui-text-dim">L10 life consumed</span>
                <span className={`font-mono ${b.roller.life_consumed_pct > 50 ? 'text-sev-crit' : 'text-ui-text'}`}>
                  {b.roller.life_consumed_pct.toFixed(4)}%
                </span>
              </div>
              <div className="h-2 bg-ui-bg-2 rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${b.roller.life_consumed_pct > 50 ? 'bg-sev-crit' : 'bg-sev-warn'}`}
                     style={{ width: `${Math.min(100, b.roller.life_consumed_pct)}%` }} />
              </div>
            </div>
            <StatusRow label="EHL film" value={`${b.roller.lube_film_um.toFixed(2)} µm`}
                       color={b.roller.lube_film_um < 0.5 ? 'text-sev-crit' : 'text-ui-text'} />
            <StatusRow label="Roller temp" value={`${b.roller.temperature_k.toFixed(0)} K`} />
            <StatusRow label="Loading factor" value={`${(b.roller.loading_factor * 100).toFixed(1)}%`} />
          </div>
        </div>
      </div>

      {/* Statistics + controls */}
      <div className="mt-4 flex items-center justify-between">
        <div className="text-[10px] text-ui-text-faint">
          Total trips: {b.stats.total_trips} · Alarms: {b.stats.total_alarms}
          {b.stats.last_trip_at_yr != null && ` · Last trip: yr ${b.stats.last_trip_at_yr.toFixed(3)}`}
        </div>
        <div className="flex gap-2">
          <button onClick={trip}
                  className="px-3 py-1.5 rounded-lg border border-sev-warn bg-sev-warn/40 text-sev-warn hover:bg-sev-warn/60 text-xs font-bold">
            Force Trip
          </button>
          <button onClick={restore}
                  className="px-3 py-1.5 rounded-lg border border-sev-ok bg-sev-ok/40 text-sev-ok hover:bg-sev-ok/60 text-xs font-bold">
            Restore Maglev
          </button>
        </div>
      </div>
    </div>
  );
}

function StatusRow({ label, value, color }:
  { label: string; value: string; color?: string }) {
  return (
    <div className="flex justify-between text-xs">
      <span className="text-ui-text-dim">{label}</span>
      <span className={`font-mono ${color || 'text-ui-text'}`}>{value}</span>
    </div>
  );
}
