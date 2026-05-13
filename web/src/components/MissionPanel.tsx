/**
 * Mission-phase panel: current phase, nominal next, transition controls.
 * Polls /api/mission/phase every 2 s so the UI stays in sync if another
 * client drives a tick or transition.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type PhaseState } from '../api/aria';

const PHASES = ['prelaunch', 'boost', 'cruise', 'deceleration', 'arrival', 'orbit', 'emergency'];

const PHASE_TOOLTIPS: Record<string, string> = {
  prelaunch:    'Cislunar assembly orbit. Reactor in standby; commissioning checks. No motion.',
  boost:        'Main engine burn. 5 yr nominal, accelerating from 0 to terminal cruise velocity.',
  cruise:       'Coast phase. Main engine off, ship drifts at constant velocity for most of the voyage.',
  deceleration: 'Braking burn. Same Δv as boost, applied in reverse, typically last 5 yr of voyage.',
  arrival:      'Approaching destination. Navigation/orbit insertion burns.',
  orbit:        'Stable orbit at destination. Colonisation operations.',
  emergency:    'Off-nominal. Manual operator intervention required to recover.',
};

export function MissionPanel() {
  const [state, setState] = useState<PhaseState | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const s = await ariaApi.missionPhase();
        if (!cancelled) { setState(s); setErr(null); }
      } catch (e: any) {
        if (!cancelled) setErr(String(e));
      }
    };
    poll();
    const t = setInterval(poll, 2000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  const transition = async (target: string) => {
    // Always force — user clicked a phase button, that IS the intent.
    // Previously we showed a confirm() dialog on illegal-transition,
    // which broke flow when the operator tried to reset the mission
    // after auto-arrival (ARRIVAL → PRELAUNCH is normally illegal).
    try {
      setState(await ariaApi.missionTransition(target, true));
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    }
  };

  const tick = async (yr: number) => setState(await ariaApi.missionTick(yr));

  if (err)    return <div className="p-3 text-xs text-sev-crit">Mission API: {err}</div>;
  if (!state) return <div className="p-3 text-xs text-ui-text-dim">Loading mission state…</div>;

  return (
    <div className="p-3 space-y-2 text-sm">
      <div className="flex items-baseline justify-between">
        <div>
          <div className="text-[9px] uppercase tracking-wide text-ui-text-faint">Current phase</div>
          <div className="text-lg font-bold text-ui-accent uppercase">{state.current_phase}</div>
        </div>
        <div className="text-right">
          <div className="text-[9px] uppercase tracking-wide text-ui-text-faint">Mission year</div>
          <div className="font-mono text-ui-text">{state.elapsed_yr.toFixed(2)} yr</div>
        </div>
      </div>

      <div className="text-xs text-ui-text-dim italic">{state.spec.description}</div>

      <div className="grid grid-cols-2 gap-1 text-[10px]">
        <Bar label="Power" v={state.spec.power_load_frac} />
        <Bar label="Thermal" v={state.spec.thermal_load_frac} />
        <Bar label="RCS" v={state.spec.rcs_load_frac} />
        <Bar label="Main Thrust" v={state.spec.main_thrust_frac} />
      </div>

      <div className="pt-1 border-t border-ui-border">
        <div className="text-[9px] uppercase tracking-wider text-ui-text-faint mb-1">
          Phase transition · click to advance/revert · hover for description
        </div>
        <div className="flex flex-wrap gap-1">
          {PHASES.map(p => (
            <button key={p}
                    onClick={() => transition(p)}
                    disabled={p === state.current_phase}
                    title={PHASE_TOOLTIPS[p] ?? p}
                    className={`px-1.5 py-0.5 text-[10px] rounded border transition-colors
                      ${p === state.current_phase
                        ? 'border-ui-accent bg-ui-accent/15 text-ui-accent cursor-default'
                        : p === state.nominal_next
                        ? 'border-sev-ok bg-sev-ok/20 text-ui-text hover:bg-sev-ok/30'
                        : 'border-ui-border bg-ui-bg-2/40 text-ui-text-dim hover:bg-ui-bg-2 hover:text-ui-text'}`}>
              {p}
            </button>
          ))}
        </div>
        <div className="text-[9px] text-ui-text-faint mt-1 leading-relaxed">
          <span className="text-ui-accent">cyan</span> = current ·
          <span className="text-sev-ok"> green</span> = nominal next ·
          others = jump to that phase (forces a transition even if non-nominal).
        </div>
      </div>

      <div className="flex flex-wrap gap-1 pt-1 border-t border-ui-border">
        <span className="text-[9px] uppercase tracking-wider text-ui-text-faint self-center">mission clock:</span>
        <button onClick={() => tick(1 / 365.25 / 24)} className="px-2 py-0.5 text-[10px] rounded border border-ui-border bg-ui-bg-2/40 text-ui-text hover:bg-ui-bg-2 transition-colors">+1 hr</button>
        <button onClick={() => tick(1 / 365.25)}      className="px-2 py-0.5 text-[10px] rounded border border-ui-border bg-ui-bg-2/40 text-ui-text hover:bg-ui-bg-2 transition-colors">+1 day</button>
        <button onClick={() => tick(0.1)}             className="px-2 py-0.5 text-[10px] rounded border border-ui-border bg-ui-bg-2/40 text-ui-text hover:bg-ui-bg-2 transition-colors">+0.1 yr</button>
        <button onClick={() => tick(1.0)}             className="px-2 py-0.5 text-[10px] rounded border border-ui-border bg-ui-bg-2/40 text-ui-text hover:bg-ui-bg-2 transition-colors">+1 yr</button>
        <button onClick={() => tick(10)}              className="px-2 py-0.5 text-[10px] rounded border border-ui-border bg-ui-bg-2/40 text-ui-text hover:bg-ui-bg-2 transition-colors">+10 yr</button>
      </div>
    </div>
  );
}

function Bar({ label, v }: { label: string; v: number }) {
  return (
    <div>
      <div className="flex justify-between">
        <span className="text-ui-text-faint">{label}</span>
        <span className="text-ui-text">{(v * 100).toFixed(0)}%</span>
      </div>
      <div className="h-1 bg-ui-bg-2 rounded overflow-hidden">
        <div className="h-full bg-ui-accent" style={{ width: `${v * 100}%` }} />
      </div>
    </div>
  );
}
