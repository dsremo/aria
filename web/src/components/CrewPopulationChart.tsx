/**
 * Crew Population Chart — demographics display with generation tracking.
 *
 * Shows current crew count, effective-g, and 5 health metrics from
 * /api/crew/health. Displays a visual representation of population
 * health bands and generation progression.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type CrewHealth } from '../api/aria';

export function CrewPopulationChart() {
  const [crew, setCrew] = useState<CrewHealth | null>(null);
  const [history, setHistory] = useState<{ yr: number; bone: number; vo2: number; psych: number }[]>([]);

  useEffect(() => {
    const refresh = async () => {
      try {
        const c = await ariaApi.crewHealth();
        setCrew(c);
        setHistory(h => {
          const snap = { yr: c.elapsed_yr, bone: c.metrics.bone_density_pct, vo2: c.metrics.vo2max_pct, psych: c.metrics.psych_cohesion_pct };
          const next = [...h, snap];
          return next.length > 100 ? next.slice(-100) : next;
        });
      } catch {}
    };
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);

  if (!crew) return <div className="p-4 text-sm text-ui-text-dim">Loading crew data...</div>;

  const m = crew.metrics;

  const healthMetrics = [
    { label: 'Bone Density', value: m.bone_density_pct, warn: 80, danger: 70, desc: 'Sibonga 2007' },
    { label: 'VO₂max', value: m.vo2max_pct, warn: 80, danger: 65, desc: 'Convertino 1996' },
    { label: 'Psych Cohesion', value: m.psych_cohesion_pct, warn: 70, danger: 50, desc: 'Clément 2006' },
  ];

  const adverseMetrics = [
    { label: 'SANS Prevalence', value: m.sans_prevalence_pct, warn: 5, danger: 20, desc: 'Mader 2011' },
    { label: 'Vestibular Unadapted', value: m.vestibular_unadapted_pct, warn: 30, danger: 60, desc: 'Clément 2006' },
  ];

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Crew Population & Health</h2>
        <p className="text-xs text-ui-text-dim">
          {crew.crew_size} crew · {crew.effective_g.toFixed(2)} g effective · {crew.elapsed_yr.toFixed(2)} yr mission time
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Population overview */}
        <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-wider text-ui-text-faint font-bold mb-3">Population</div>
          <div className="flex items-center justify-center gap-6 mb-4">
            <div className="text-center">
              <div className="text-4xl font-bold text-ui-accent font-mono">{crew.crew_size}</div>
              <div className="text-[9px] text-ui-text-faint uppercase">Crew</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-ui-text font-mono">{crew.effective_g.toFixed(2)}</div>
              <div className="text-[9px] text-ui-text-faint uppercase">g (habitat)</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-sev-warn font-mono">{crew.alarms_fired}</div>
              <div className="text-[9px] text-ui-text-faint uppercase">Alarms</div>
            </div>
          </div>
          {/* Crew visual (dot grid) */}
          <div className="flex flex-wrap gap-0.5 justify-center">
            {Array.from({ length: Math.min(crew.crew_size, 200) }, (_, i) => (
              <div key={i} className="w-1.5 h-1.5 rounded-full bg-ui-accent/80" />
            ))}
            {crew.crew_size > 200 && (
              <span className="text-[8px] text-ui-text-faint ml-1">+{crew.crew_size - 200}</span>
            )}
          </div>
        </div>

        {/* Health metrics */}
        <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-wider text-ui-text-faint font-bold mb-3">Health Metrics (positive)</div>
          {healthMetrics.map(h => {
            const color = h.value < h.danger ? 'bg-sev-crit' : h.value < h.warn ? 'bg-sev-warn' : 'bg-sev-ok';
            return (
              <div key={h.label} className="mb-2">
                <div className="flex justify-between text-xs mb-0.5">
                  <span className="text-ui-text">{h.label}</span>
                  <span className="font-mono text-ui-text-dim">{h.value.toFixed(1)}%</span>
                </div>
                <div className="h-2 bg-ui-bg-2 rounded-full overflow-hidden">
                  <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${Math.max(0, Math.min(100, h.value))}%` }} />
                </div>
                <div className="text-[8px] text-ui-text-faint mt-0.5">{h.desc}</div>
              </div>
            );
          })}
        </div>

        {/* Adverse metrics */}
        <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-wider text-ui-text-faint font-bold mb-3">Adverse Conditions (lower is better)</div>
          {adverseMetrics.map(h => {
            const color = h.value > h.danger ? 'bg-sev-crit' : h.value > h.warn ? 'bg-sev-warn' : 'bg-sev-info';
            return (
              <div key={h.label} className="mb-2">
                <div className="flex justify-between text-xs mb-0.5">
                  <span className="text-ui-text">{h.label}</span>
                  <span className="font-mono text-ui-text-dim">{h.value.toFixed(1)}%</span>
                </div>
                <div className="h-2 bg-ui-bg-2 rounded-full overflow-hidden">
                  <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${Math.max(0, Math.min(100, h.value))}%` }} />
                </div>
                <div className="text-[8px] text-ui-text-faint mt-0.5">{h.desc}</div>
              </div>
            );
          })}
        </div>

        {/* Health trend sparklines */}
        {history.length > 5 && (
          <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-4">
            <div className="text-[10px] uppercase tracking-wider text-ui-text-faint font-bold mb-2">Health Trends</div>
            {[
              { label: 'Bone', data: history.map(h => h.bone), color: '#22c55e' },
              { label: 'VO₂max', data: history.map(h => h.vo2), color: '#06b6d4' },
              { label: 'Psych', data: history.map(h => h.psych), color: '#eab308' },
            ].map(trend => (
              <div key={trend.label} className="mb-2">
                <div className="text-[9px] text-ui-text-dim mb-0.5">{trend.label}</div>
                <TrendLine data={trend.data} color={trend.color} />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Sources */}
      <div className="mt-3 text-[9px] text-ui-text-faint">
        Sources: {crew.sources.slice(0, 4).join(' · ')}
      </div>
    </div>
  );
}

function TrendLine({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) return null;
  const W = 200, H = 24;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = H - ((v - min) / range) * (H - 4) - 2;
    return `${x},${y}`;
  }).join(' ');
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-6" preserveAspectRatio="none">
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}
