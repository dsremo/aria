/**
 * Random Events Control — toggle stochastic events + force MMOD/flare.
 *
 * Operator control for the Poisson event generator: enable/disable,
 * view counts, force specific events for testing.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type RandomEventsState } from '../api/aria';

export function RandomEventsPanel() {
  const [state, setState] = useState<RandomEventsState | null>(null);

  useEffect(() => {
    const refresh = () => ariaApi.randomEvents().then(setState).catch(() => {});
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);

  if (!state) return <div className="p-4 text-sm text-ui-text-dim">Loading...</div>;

  const toggle = async () => setState(await ariaApi.randomEventsToggle(!state.enabled));
  const forceMmod = async () => setState(await ariaApi.forceMmod());
  const forceFlare = async () => setState(await ariaApi.forceFlare());

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Stochastic Event Generator</h2>
        <p className="text-xs text-ui-text-dim">
          Poisson-distributed random events: MMOD strikes, solar flares, equipment faults.
          Seed: {state.seed}
        </p>
      </div>

      {/* Enable toggle */}
      <div className={`p-4 rounded-lg border mb-4 ${state.enabled ? 'bg-sev-ok/20 border-sev-ok/50' : 'bg-ui-bg-1/60 border-ui-border'}`}>
        <div className="flex items-center justify-between">
          <div>
            <span className={`text-sm font-bold ${state.enabled ? 'text-sev-ok' : 'text-ui-text-dim'}`}>
              Random Events: {state.enabled ? 'ENABLED' : 'DISABLED'}
            </span>
            <div className="text-[9px] text-ui-text-faint mt-0.5">
              {state.enabled ? 'Events fire stochastically during simulation ticks' : 'No random events — deterministic mode'}
            </div>
          </div>
          <button onClick={toggle}
                  className={`px-4 py-2 rounded-lg border font-bold text-sm ${
                    state.enabled
                      ? 'bg-sev-crit/40 border-sev-crit text-sev-crit hover:bg-sev-crit/60'
                      : 'bg-sev-ok/40 border-sev-ok text-sev-ok hover:bg-sev-ok/60'
                  }`}>
            {state.enabled ? 'Disable' : 'Enable'}
          </button>
        </div>
      </div>

      {/* Event rates */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <StatCard label="MMOD rate" value={`${state.rates.mmod_per_yr.toFixed(1)}/yr`} />
        <StatCard label="Flare rate (boost)" value={`${state.rates.flare_boost.toFixed(2)}/yr`} />
        <StatCard label="Flare rate (cruise)" value={`${state.rates.flare_cruise.toFixed(2)}/yr`} />
        <StatCard label="Fault rate" value={`${state.rates.fault_per_yr.toFixed(1)}/yr`} />
      </div>

      {/* Cumulative counts */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <CountCard label="MMOD Strikes" count={state.counts.mmod} icon="☄" color="text-sev-warn" />
        <CountCard label="Solar Flares" count={state.counts.flare} icon="☀" color="text-sev-warn" />
        <CountCard label="Faults" count={state.counts.fault} icon="⚡" color="text-sev-crit" />
      </div>

      {/* Force event buttons */}
      <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-4">
        <div className="text-[10px] uppercase tracking-wider text-ui-text-faint font-bold mb-2">
          Manual Event Injection (Operator Drill)
        </div>
        <div className="flex gap-2">
          <button onClick={forceMmod}
                  className="px-4 py-2 rounded-lg border border-orange-600 bg-sev-warn/40 text-orange-200 hover:bg-sev-warn/60 text-sm">
            ☄ Force MMOD Strike
          </button>
          <button onClick={forceFlare}
                  className="px-4 py-2 rounded-lg border border-sev-warn bg-sev-warn/40 text-sev-warn hover:bg-sev-warn/60 text-sm">
            ☀ Force Solar Flare
          </button>
        </div>
        <div className="text-[9px] text-ui-text-faint mt-2">
          Elapsed: {state.counts.elapsed_yr.toFixed(3)} sim-yr since last reset
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-3">
      <div className="text-[9px] uppercase tracking-wider text-ui-text-faint">{label}</div>
      <div className="text-sm font-mono text-ui-text">{value}</div>
    </div>
  );
}

function CountCard({ label, count, icon, color }: { label: string; count: number; icon: string; color: string }) {
  return (
    <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-3 text-center">
      <div className="text-2xl mb-1">{icon}</div>
      <div className={`text-2xl font-bold font-mono ${color}`}>{count}</div>
      <div className="text-[9px] text-ui-text-faint uppercase">{label}</div>
    </div>
  );
}
