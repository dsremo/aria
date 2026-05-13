/**
 * Agriculture Dashboard — crop yields, food balance, and harvest cycles.
 *
 * Detailed view of the 5-crop hydroponic farm: wheat, soy, sweet potato,
 * lettuce, tilapia. Shows per-crop cycle progress, cumulative yield,
 * and overall kcal/protein balance. Polls /api/agriculture every 3s.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type AgricultureState } from '../api/aria';

const CROP_ICONS: Record<string, string> = {
  wheat: '🌾', soy: '🫘', sweet_potato: '🍠', lettuce: '🥬', tilapia: '🐟',
};

export function AgricultureDashboard() {
  const [ag, setAg] = useState<AgricultureState | null>(null);

  useEffect(() => {
    const refresh = () => ariaApi.agriculture().then(setAg).catch(() => {});
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);

  if (!ag) return <div className="p-4 text-sm text-ui-text-dim">Loading agriculture...</div>;

  const balance = ag.totals.kcal_produced - ag.totals.kcal_consumed;
  const protBalance = ag.totals.protein_g_produced - ag.totals.protein_g_consumed;

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Hydroponic Agriculture</h2>
        <p className="text-xs text-ui-text-dim">
          {(ag.total_area_m2 / 1000).toFixed(0)}k m² farm · {ag.crew_size} crew ·
          Food store: {(ag.food_store_kg / 1000).toFixed(1)} t
        </p>
      </div>

      {/* Energy/Protein balance */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className={`bg-ui-bg-1/60 border rounded-lg p-3 ${balance >= 0 ? 'border-sev-ok/50' : 'border-sev-crit/50'}`}>
          <div className="text-[9px] uppercase tracking-wider text-ui-text-faint">Energy Balance</div>
          <div className={`text-xl font-bold font-mono ${balance >= 0 ? 'text-sev-ok' : 'text-sev-crit'}`}>
            {balance >= 0 ? '+' : ''}{(balance / 1e6).toFixed(2)} M
          </div>
          <div className="text-[9px] text-ui-text-faint">
            kcal (produced {(ag.totals.kcal_produced / 1e6).toFixed(2)}M − consumed {(ag.totals.kcal_consumed / 1e6).toFixed(2)}M)
          </div>
          {ag.totals.days_short_kcal > 0 && (
            <div className="text-[9px] text-sev-crit mt-1">{ag.totals.days_short_kcal} days short!</div>
          )}
        </div>
        <div className={`bg-ui-bg-1/60 border rounded-lg p-3 ${protBalance >= 0 ? 'border-sev-ok/50' : 'border-sev-crit/50'}`}>
          <div className="text-[9px] uppercase tracking-wider text-ui-text-faint">Protein Balance</div>
          <div className={`text-xl font-bold font-mono ${protBalance >= 0 ? 'text-sev-ok' : 'text-sev-crit'}`}>
            {protBalance >= 0 ? '+' : ''}{(protBalance / 1000).toFixed(1)} kg
          </div>
          <div className="text-[9px] text-ui-text-faint">
            g (produced {(ag.totals.protein_g_produced / 1000).toFixed(1)}kg − consumed {(ag.totals.protein_g_consumed / 1000).toFixed(1)}kg)
          </div>
        </div>
      </div>

      {/* Per-crop cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {ag.crops.map(crop => {
          const icon = CROP_ICONS[crop.id] || '🌱';
          const yieldColor = crop.yield_modifier < 0.5 ? 'bg-sev-crit' : crop.yield_modifier < 1 ? 'bg-sev-warn' : 'bg-sev-ok';
          return (
            <div key={crop.id} className={`bg-ui-bg-1/60 border rounded-lg p-3 ${
              crop.failure_active ? 'border-sev-crit' : 'border-ui-border'
            }`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{icon}</span>
                  <span className="text-sm font-bold text-ui-text">{crop.name}</span>
                </div>
                {crop.failure_active && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-sev-crit/60 border border-sev-crit text-sev-crit">
                    {crop.failure_active}
                  </span>
                )}
              </div>

              {/* Cycle progress */}
              <div className="mb-2">
                <div className="flex justify-between text-[10px] mb-0.5">
                  <span className="text-ui-text-dim">Cycle</span>
                  <span className="font-mono text-ui-text">{crop.cycle_progress_pct.toFixed(1)}% / {crop.days_to_harvest} d</span>
                </div>
                <div className="h-2 bg-ui-bg-2 rounded-full overflow-hidden">
                  <div className={`h-full ${yieldColor} rounded-full transition-all`}
                       style={{ width: `${crop.cycle_progress_pct}%` }} />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-1 text-[9px]">
                <div>
                  <span className="text-ui-text-faint">Area:</span>{' '}
                  <span className="text-ui-text">{crop.area_m2.toLocaleString()} m²</span>
                </div>
                <div>
                  <span className="text-ui-text-faint">Yield mod:</span>{' '}
                  <span className={crop.yield_modifier < 0.7 ? 'text-sev-crit' : 'text-ui-text'}>
                    {(crop.yield_modifier * 100).toFixed(0)}%
                  </span>
                </div>
                <div>
                  <span className="text-ui-text-faint">Last harvest:</span>{' '}
                  <span className="text-ui-text">{(crop.last_harvest_kg / 1000).toFixed(2)} t</span>
                </div>
                <div>
                  <span className="text-ui-text-faint">Cumulative:</span>{' '}
                  <span className="text-ui-accent">{(crop.cumulative_yield_kg / 1000).toFixed(1)} t</span>
                </div>
              </div>

              <div className="text-[8px] text-ui-text-faint mt-1 italic">{crop.citation}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
