/**
 * Cold-start sequence panel. Shows the 19-step bringup procedure,
 * lets the user tick it forward, abort, or reset.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type StartupState, type StartupStep } from '../api/aria';
import { SeverityBadge } from './SeverityBadge';

function formatEta(s: number): string {
  if (s < 60)    return `${s.toFixed(0)} s`;
  if (s < 3600)  return `${(s / 60).toFixed(1)} min`;
  if (s < 86400) return `${(s / 3600).toFixed(1)} hr`;
  return `${(s / 86400).toFixed(1)} d`;
}

function computeEta(state: StartupState): string {
  if (state.complete)             return 'cold-start complete';
  if (state.aborted)              return 'aborted';
  const pendingSteps = state.steps.filter(st => st.status === 'pending');
  const runningStep  = state.steps.find(st => st.status === 'running');
  let remaining = pendingSteps.reduce((sum, st) => sum + st.duration_s, 0);
  if (runningStep) remaining += Math.max(0, runningStep.duration_s - runningStep.elapsed_s);
  if (remaining <= 0) return '~0 s remaining';
  return `~${formatEta(remaining)} remaining (sim time)`;
}

const STATUS_COLORS: Record<StartupStep['status'], string> = {
  pending: 'text-ui-text-dim',
  running: 'text-sev-warn animate-pulse',
  success: 'text-sev-ok',
  failed:  'text-sev-crit',
  skipped: 'text-ui-text-faint line-through',
};

export function StartupPanel() {
  const [state, setState] = useState<StartupState | null>(null);

  useEffect(() => {
    const refresh = () => ariaApi.startupStatus().then(setState).catch(() => {});
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);

  if (!state) return <div className="p-3 text-xs text-ui-text-dim">Loading startup state…</div>;

  const tick    = async (dt: number) => setState(await ariaApi.startupTick(dt));
  const reset   = async () => setState(await ariaApi.startupReset());
  const abort   = async () => setState(await ariaApi.startupAbort('operator'));

  return (
    <div className="p-3 space-y-2 text-sm">
      <div className="flex items-baseline justify-between">
        <div className="text-[10px] uppercase tracking-wide text-ui-text-faint">Cold-Start Sequence</div>
        {state.complete  ? <SeverityBadge severity="ok">Complete</SeverityBadge>
          : state.aborted ? <SeverityBadge severity="crit">Aborted</SeverityBadge>
          : <SeverityBadge severity="warn">In progress</SeverityBadge>}
      </div>

      <div>
        <div className="h-2 bg-ui-bg-2 rounded overflow-hidden">
          <div className="h-full bg-sev-ok transition-all"
               style={{ width: `${state.progress_pct}%` }} />
        </div>
        <div className="flex justify-between text-[10px] text-ui-text-dim mt-0.5">
          <span>{state.progress_pct.toFixed(1)}%</span>
          <span>{computeEta(state)}</span>
        </div>
      </div>

      <div className="flex gap-1 items-center flex-wrap">
        <span className="text-[9px] uppercase tracking-wider text-ui-text-faint">startup:</span>
        <button onClick={() => tick(30)}    className="px-2 py-0.5 text-[10px] rounded border border-ui-border bg-ui-bg-2/40 text-ui-text hover:bg-ui-bg-2 transition-colors">+30 s</button>
        <button onClick={() => tick(300)}   className="px-2 py-0.5 text-[10px] rounded border border-ui-border bg-ui-bg-2/40 text-ui-text hover:bg-ui-bg-2 transition-colors">+5 min</button>
        <button onClick={() => tick(3600)}  className="px-2 py-0.5 text-[10px] rounded border border-ui-border bg-ui-bg-2/40 text-ui-text hover:bg-ui-bg-2 transition-colors">+1 hr</button>
        <button onClick={() => tick(86400)} className="px-2 py-0.5 text-[10px] rounded border border-ui-border bg-ui-bg-2/40 text-ui-text hover:bg-ui-bg-2 transition-colors">+1 day</button>
        <button onClick={abort}             className="px-2 py-0.5 text-[10px] rounded border border-sev-crit bg-sev-crit/15 text-sev-crit hover:bg-sev-crit/25 transition-colors">Abort</button>
        <button onClick={reset}             className="px-2 py-0.5 text-[10px] rounded border border-ui-border bg-ui-bg-2/40 text-ui-text hover:bg-ui-bg-2 transition-colors">Reset</button>
      </div>

      <div className="max-h-96 overflow-y-auto pr-1 space-y-0.5">
        {state.steps.map((s, i) => (
          <div key={s.id}
               className={`text-[11px] ${s.id === state.current_step_id ? 'bg-ui-bg-2/80 -mx-1 px-1 rounded' : ''}`}>
            <div className="flex items-center gap-1">
              <span className="w-5 text-right text-ui-text-faint">{(i + 1).toString().padStart(2, '0')}</span>
              <span className={`flex-1 ${STATUS_COLORS[s.status]}`}>{s.label}</span>
              <span className="text-[9px] text-ui-text-faint uppercase">{s.subsystem}</span>
            </div>
            {s.status === 'running' && (
              <div className="ml-6 h-0.5 bg-ui-bg-2 mt-0.5 rounded overflow-hidden">
                <div className="h-full bg-sev-warn" style={{ width: `${100 * s.elapsed_s / s.duration_s}%` }} />
              </div>
            )}
            {s.note && (
              <div className="ml-6 text-[9px] italic text-sev-crit">⚠ {s.note}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
