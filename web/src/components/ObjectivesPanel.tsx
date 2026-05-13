/**
 * Mission objectives — checklist of milestones grouped by category,
 * with overall progress bar and live %.
 */

import { useEffect, useMemo, useState } from 'react';
import { ariaApi, type MissionObjectivesState } from '../api/aria';

const CATEGORY_ORDER = ['startup', 'phase', 'distance', 'subsystem', 'arrival'];
const CATEGORY_COLORS: Record<string, string> = {
  startup:   'text-ui-accent',
  phase:     'text-sev-warn',
  distance:  'text-sev-ok',
  subsystem: 'text-sev-info',
  arrival:   'text-ui-accent',
};

export function ObjectivesPanel() {
  const [data, setData] = useState<MissionObjectivesState | null>(null);

  useEffect(() => {
    const refresh = () => ariaApi.objectives().then(setData).catch(() => {});
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);

  const grouped = useMemo(() => {
    if (!data) return {} as Record<string, MissionObjectivesState['objectives']>;
    const out: Record<string, MissionObjectivesState['objectives']> = {};
    for (const o of data.objectives) (out[o.category] = out[o.category] ?? []).push(o);
    return out;
  }, [data]);

  if (!data) return <div className="p-4 text-sm text-ui-text-dim">Loading objectives…</div>;

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-2 border-b border-ui-border">
        <div className="flex items-baseline justify-between mb-1">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-ui-accent font-bold">
              Mission Objectives · sim year {data.current_yr.toFixed(2)}
            </div>
            <div className="text-[10px] text-ui-text-faint mt-0.5">
              {data.completed} / {data.total} complete
            </div>
          </div>
          <div className="text-2xl font-bold text-ui-accent font-mono">
            {data.progress_pct.toFixed(1)}%
          </div>
        </div>
        <div className="h-2 bg-ui-bg-2 rounded overflow-hidden relative">
          <div className="h-full bg-ui-accent transition-all" style={{ width: `${data.progress_pct}%` }} />
          {/* Per-category segment markers — thin vertical ticks showing
              the fraction each category contributes to total progress.
              Lets operators at a glance see which category is lagging
              without reading the per-category rows below. */}
          {CATEGORY_ORDER.map((cat, idx) => {
            const prior = CATEGORY_ORDER.slice(0, idx)
              .reduce((s, c) => s + (grouped[c]?.length ?? 0), 0);
            const here = grouped[cat]?.length ?? 0;
            const total = data.total || 1;
            const startPct = (prior / total) * 100;
            if (here === 0) return null;
            return (
              <div key={cat}
                   className="absolute top-0 bottom-0 border-l border-slate-900/50"
                   style={{ left: `${startPct}%` }}
                   title={`${cat} starts here`} />
            );
          })}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {CATEGORY_ORDER.map(cat => {
          const list = grouped[cat] ?? [];
          if (!list.length) return null;
          const done = list.filter(o => o.complete).length;
          const catPct = (done / list.length) * 100;
          return (
            <div key={cat}>
              <div className="flex items-baseline justify-between mb-1">
                <div className={`text-[10px] uppercase tracking-wider font-bold ${CATEGORY_COLORS[cat]}`}>
                  {cat} · {done}/{list.length}
                </div>
                <div className="text-[9px] text-ui-text-dim font-mono">{catPct.toFixed(0)} %</div>
              </div>
              <div className="h-1 mb-1 bg-ui-bg-2 rounded overflow-hidden">
                <div className={`h-full transition-all ${
                  catPct === 100 ? 'bg-sev-ok' :
                  catPct >= 50   ? 'bg-ui-accent' : 'bg-ui-bg-3'
                }`} style={{ width: `${catPct}%` }} />
              </div>
              <div className="space-y-0.5">
                {list.map(o => (
                  <div key={o.id}
                       className={`flex items-baseline gap-2 px-2 py-1 rounded text-[11px]
                                   ${o.complete ? 'bg-sev-ok/30 border border-emerald-800/60' : 'bg-ui-bg-1/30 border border-ui-border/30'}`}>
                    <span className={`text-base ${o.complete ? 'text-sev-ok' : 'text-ui-text-faint'}`}>
                      {o.complete ? '✓' : '○'}
                    </span>
                    <div className="flex-1">
                      <div className={o.complete ? 'text-sev-ok' : 'text-ui-text'}>
                        {o.label}
                      </div>
                      <div className="text-[9px] text-ui-text-faint">{o.description}</div>
                      {o.notes && <div className="text-[9px] text-sev-warn italic">{o.notes}</div>}
                    </div>
                    {o.completed_at_yr != null && (
                      <span className="text-[9px] text-ui-text-faint font-mono">yr {o.completed_at_yr.toFixed(2)}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
