/**
 * Atmosphere Monitor — ECLSS trace contaminants + O2/CO2 display.
 *
 * Shows 4 trace contaminants from /api/eclss/contaminants with SMAC
 * margin bars, cabin volume, scrubber efficiency, and alarm status.
 * Presented as a dedicated full-screen tab for the ECLSS operator.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type ContaminantsStatus } from '../api/aria';

export function AtmosphereMonitor() {
  const [data, setData] = useState<ContaminantsStatus | null>(null);

  useEffect(() => {
    const refresh = () => ariaApi.eclssContaminants().then(setData).catch(() => {});
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);

  if (!data) return <div className="p-4 text-sm text-ui-text-dim">Loading atmosphere...</div>;

  const contaminants = Object.entries(data.contaminants);
  const anyAlarm = contaminants.some(([_, c]) => c.alarm);

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">ECLSS Atmosphere Monitor</h2>
        <p className="text-xs text-ui-text-dim">
          Cabin volume: {(data.cabin_volume_m3 / 1000).toFixed(0)}k m³ ·
          Crew: {data.crew_size} ·
          Scrubber: {(data.scrubber_efficiency_frac * 100).toFixed(0)}% eff ·
          {anyAlarm ? <span className="text-sev-crit ml-1">ALARM ACTIVE</span> : <span className="text-sev-ok ml-1">NOMINAL</span>}
        </p>
      </div>

      {/* Overall status */}
      <div className={`p-3 rounded-lg border mb-4 ${anyAlarm ? 'bg-sev-crit/30 border-sev-crit' : 'bg-sev-ok/20 border-sev-ok/50'}`}>
        <div className="flex items-center gap-2">
          <div className={`w-4 h-4 rounded-full ${anyAlarm ? 'bg-sev-crit animate-pulse' : 'bg-sev-ok'}`} />
          <span className={`text-sm font-bold ${anyAlarm ? 'text-sev-crit' : 'text-sev-ok'}`}>
            {anyAlarm ? 'SMAC BREACH — contaminant exceeds 180-day limit' : 'All contaminants within SMAC limits'}
          </span>
        </div>
      </div>

      {/* Contaminant cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {contaminants.map(([key, c]) => {
          const margin = c.margin_to_smac_180d_pct;
          const barPct = Math.max(2, Math.min(100, 100 - margin));
          const barColor = margin > 50 ? 'bg-sev-ok' : margin > 10 ? 'bg-sev-warn' : 'bg-sev-crit';

          return (
            <div key={key} className={`bg-ui-bg-1/60 border rounded-lg p-4 ${c.alarm ? 'border-sev-crit' : 'border-ui-border'}`}>
              <div className="flex items-center justify-between mb-2">
                <div>
                  <span className="text-sm font-bold text-ui-text">{c.name}</span>
                  <span className="text-xs text-ui-text-faint ml-2">({c.formula})</span>
                </div>
                {c.alarm && <span className="text-[9px] px-2 py-0.5 rounded bg-sev-crit/15 border border-sev-crit text-sev-crit">ALARM</span>}
              </div>

              {/* Concentration bar */}
              <div className="mb-2">
                <div className="flex justify-between text-[10px] mb-0.5">
                  <span className="text-ui-text-dim">Concentration</span>
                  <span className="font-mono text-ui-text">
                    {c.concentration_mg_m3.toFixed(3)} / {c.smac_180day} mg/m³
                  </span>
                </div>
                <div className="h-3 bg-ui-bg-2 rounded-full overflow-hidden">
                  <div className={`h-full ${barColor} rounded-full transition-all`} style={{ width: `${barPct}%` }} />
                </div>
                <div className="flex justify-between text-[8px] text-ui-text-faint mt-0.5">
                  <span>0</span>
                  <span>SMAC-7d: {c.smac_7day}</span>
                  <span>SMAC-180d: {c.smac_180day}</span>
                </div>
              </div>

              {/* Stats */}
              <div className="grid grid-cols-2 gap-1 text-[9px]">
                <div>
                  <span className="text-ui-text-faint">Margin to 180d:</span>{' '}
                  <span className={margin > 50 ? 'text-sev-ok' : margin > 10 ? 'text-sev-warn' : 'text-sev-crit'}>
                    {margin.toFixed(1)}%
                  </span>
                </div>
                <div>
                  <span className="text-ui-text-faint">Generated:</span>{' '}
                  <span className="text-ui-text">{c.cumulative_generated_mg.toFixed(1)} mg</span>
                </div>
                <div>
                  <span className="text-ui-text-faint">Removed:</span>{' '}
                  <span className="text-ui-text">{c.cumulative_removed_mg.toFixed(1)} mg</span>
                </div>
                <div>
                  <span className="text-ui-text-faint">Source:</span>{' '}
                  <span className="text-ui-text-dim italic">{c.source}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Reference */}
      <div className="mt-3 text-[9px] text-ui-text-faint">
        SMAC = Spacecraft Maximum Allowable Concentration (NASA JSC-20584).
        7-day and 180-day limits per contaminant.
      </div>
    </div>
  );
}
