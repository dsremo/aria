/**
 * Propellant Graph — fuel consumption display with tank-by-tank breakdown.
 *
 * Shows all fuel tanks from /api/fuel with fill bars, burn rates, and
 * time-to-empty estimates.  Each tank now carries a 60-sample fill
 * sparkline that ring-buffers the last ~2 min of state (2 s poll x 60
 * = 120 s), plus a pulsing red border when contents drop below 5 %.
 *
 * 2026-04-24: the "it's fine" → "TANK EMPTY" alarm was too binary —
 * ops get no warning until the tank is dry.  The sparkline gives an
 * at-a-glance trend so a 2 %/min drain is visible even when the fill
 * number hasn't crossed the red threshold yet.
 */

import { useEffect, useRef, useState } from 'react';
import { ariaApi, type FuelInventory } from '../api/aria';

const HISTORY_LEN = 60;

export function PropellantGraph() {
  const [fuel, setFuel] = useState<FuelInventory | null>(null);
  // tank_id → rolling [0..1] fill fraction samples, newest-last.
  const historyRef = useRef<Record<string, number[]>>({});
  const [, bumpRender] = useState(0);

  useEffect(() => {
    const refresh = async () => {
      try {
        const f = await ariaApi.fuel();
        setFuel(f);
        const h = historyRef.current;
        for (const t of f.tanks) {
          const arr = (h[t.tank_id] = h[t.tank_id] || []);
          arr.push(t.fill_fraction);
          if (arr.length > HISTORY_LEN) arr.splice(0, arr.length - HISTORY_LEN);
        }
        // Re-render so sparklines update even if only the history changed.
        bumpRender((n) => (n + 1) % 1_000_000);
      } catch { /* keep last-known */ }
    };
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);

  if (!fuel) return <div className="p-4 text-sm text-ui-text-dim">Loading fuel data...</div>;

  const { tanks, summary } = fuel;

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Propellant Inventory</h2>
        <p className="text-xs text-ui-text-dim">
          Main fill: {summary.main_fill_pct.toFixed(2)}% · Burn rate: {summary.main_burn_rate_kg_s.toFixed(1)} kg/s ·
          {summary.time_to_empty_main_yr != null && summary.time_to_empty_main_yr < 1e6
            ? ` TTE: ${formatTte(summary.time_to_empty_main_yr)}`
            : ' TTE: ∞'}
        </p>
      </div>

      {/* Alarms */}
      {(summary.alarm_low || summary.alarm_critical) && (
        <div className={`p-3 rounded-lg border mb-3 ${
          summary.alarm_critical ? 'bg-sev-crit/40 border-sev-crit text-sev-crit animate-pulse' : 'bg-sev-warn/40 border-sev-warn text-sev-warn'
        }`}>
          {summary.alarm_critical ? '🔴 TANK EMPTY — mission at risk' : '🟡 Tank below 5% — conservation mode recommended'}
        </div>
      )}

      {/* Tank cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {tanks.map(tank => {
          const fillPct = tank.fill_fraction * 100;
          const color = fillPct > 50 ? 'bg-sev-ok' : fillPct > 10 ? 'bg-sev-warn' : 'bg-sev-crit';
          const history = historyRef.current[tank.tank_id] ?? [];
          const critical = fillPct < 5;
          // Per-tank TTE (s) from local first-derivative estimate, falls
          // back to the backend burn_rate when history is short.
          const tte = estimateTteSeconds(tank, history);
          return (
            <div key={tank.tank_id}
                 className={`bg-ui-bg-1/60 border rounded-lg p-4 ${
                   critical ? 'border-sev-crit animate-pulse' :
                   fillPct < 20 ? 'border-sev-warn' : 'border-ui-border'
                 }`}>
              <div className="flex items-center justify-between mb-2">
                <div>
                  <div className="text-sm font-bold text-ui-text">{tank.label}</div>
                  <div className="text-[9px] text-ui-text-faint">{tank.fuel_type} · {tank.tank_id}</div>
                </div>
                <div className="text-right">
                  <div className="text-xl font-bold font-mono text-ui-accent">
                    {fillPct.toFixed(1)}%
                  </div>
                </div>
              </div>

              {/* Tank visual */}
              <div className="relative h-20 bg-ui-bg-2 rounded-lg overflow-hidden border border-ui-border mb-2">
                <div
                  className={`absolute bottom-0 left-0 right-0 ${color} transition-all`}
                  style={{ height: `${fillPct}%` }}
                />
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-sm font-mono text-white font-bold drop-shadow-lg">
                    {tank.fuel_type === 'D-He3'
                      ? `${(tank.contents_kg / 1e6).toFixed(3)} kt`
                      : `${(tank.contents_kg / 1e3).toFixed(2)} t`}
                  </span>
                </div>
              </div>

              {/* Fill-history sparkline — last ~2 min of polling */}
              <div className="mb-2">
                <Sparkline values={history} critical={critical} />
                <div className="flex justify-between text-[9px] text-ui-text-faint mt-0.5">
                  <span>2 min ago</span>
                  <span>{history.length >= 2 ? trendLabel(history) : '—'}</span>
                  <span>now</span>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-1 text-[9px]">
                <div>
                  <div className="text-ui-text-faint">Capacity</div>
                  <div className="text-ui-text font-mono">
                    {tank.fuel_type === 'D-He3'
                      ? `${(tank.capacity_kg / 1e6).toFixed(0)} kt`
                      : `${(tank.capacity_kg / 1e3).toFixed(2)} t`}
                  </div>
                </div>
                <div>
                  <div className="text-ui-text-faint">Drawn</div>
                  <div className="text-ui-text font-mono">
                    {(tank.cumulative_drawn_kg / 1e3).toFixed(1)} t
                  </div>
                </div>
                <div>
                  <div className="text-ui-text-faint">Local TTE</div>
                  <div className={`font-mono ${tte && tte < 3600 ? 'text-sev-crit' : 'text-ui-text'}`}>
                    {tte == null ? '—' : formatTteSeconds(tte)}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Inline SVG sparkline, 0..1 domain.  Single path, no deps.  Red fill
 *  if `critical` so a rapidly-emptying tank reads at a glance even
 *  when a reader's eyes are elsewhere on the page. */
function Sparkline({ values, critical }: { values: number[]; critical: boolean }) {
  const W = 240, H = 24;
  if (values.length < 2) {
    return (
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`}
           preserveAspectRatio="none"
           className="border border-ui-border rounded bg-ui-bg-0">
        <text x={W/2} y={H/2 + 4} fontSize={10} textAnchor="middle"
              fill="#64748b" fontFamily="monospace">
          gathering samples…
        </text>
      </svg>
    );
  }
  const min = Math.min(...values), max = Math.max(...values);
  const span = Math.max(max - min, 0.01);
  const path = values.map((v, i) => {
    const x = (i / (values.length - 1)) * W;
    const y = H - ((v - min) / span) * (H - 4) - 2;
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(' ');
  const fillPath = `${path} L${W} ${H} L0 ${H} Z`;
  const stroke = critical ? '#f87171' : '#22d3ee';
  const fill   = critical ? 'rgba(248,113,113,0.18)' : 'rgba(34,211,238,0.12)';
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`}
         preserveAspectRatio="none"
         className="border border-ui-border rounded bg-ui-bg-0">
      <path d={fillPath} fill={fill} />
      <path d={path} stroke={stroke} strokeWidth={1.5} fill="none" />
    </svg>
  );
}

function trendLabel(h: number[]): string {
  if (h.length < 2) return '—';
  const dt = (h[h.length - 1] - h[0]) * 100;  // pct points
  if (Math.abs(dt) < 0.05) return 'steady';
  const sign = dt > 0 ? '↑' : '↓';
  return `${sign} ${Math.abs(dt).toFixed(2)}%`;
}

/** Best-effort local TTE in seconds: use the last-N-sample slope if
 *  we have it (more responsive to recent burn changes), else back off
 *  to the backend-reported burn_rate. */
function estimateTteSeconds(
  tank: FuelInventory['tanks'][number],
  history: number[],
): number | null {
  if (tank.fill_fraction <= 0) return 0;
  if (history.length >= 6) {
    const dt_samples = history.length - 1;         // 2-s spacing per sample
    const df = history[history.length - 1] - history[0];
    // Negative df = draining. Positive = refill → no TTE.
    if (df < -1e-4) {
      const slopePerSec = df / (dt_samples * 2);
      const secondsLeft = -tank.fill_fraction / slopePerSec;
      if (isFinite(secondsLeft) && secondsLeft > 0) return secondsLeft;
    } else if (df >= 0) {
      return null;   // not burning → no TTE
    }
  }
  // Backend burn_rate fallback (kg/s → s by dividing contents)
  const burn = (tank as any).burn_rate_kg_s as number | undefined;
  if (burn && burn > 1e-6) return tank.contents_kg / burn;
  return null;
}

function formatTte(yr: number): string {
  if (yr < 1/365) return `${(yr * 365 * 24).toFixed(1)} h`;
  if (yr < 1)     return `${(yr * 365).toFixed(1)} d`;
  return `${yr.toFixed(1)} yr`;
}

function formatTteSeconds(s: number): string {
  if (s < 60)    return `${s.toFixed(0)} s`;
  if (s < 3600)  return `${(s / 60).toFixed(1)} min`;
  if (s < 86400) return `${(s / 3600).toFixed(1)} h`;
  if (s < 86400 * 365) return `${(s / 86400).toFixed(1)} d`;
  return `${(s / (86400 * 365.25)).toFixed(1)} yr`;
}
