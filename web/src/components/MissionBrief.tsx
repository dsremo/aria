import { useEffect, useState } from 'react';
import { ariaApi, type TrajectoryStateApi, type PhaseState } from '../api/aria';

const PHASE_HINT: Record<string, string> = {
  prelaunch:    'cislunar assembly · reactor in standby',
  boost:        'main engine burn · accelerating',
  cruise:       'coast phase · drifting at terminal v',
  deceleration: 'braking burn · main engine reversed',
  arrival:      'orbit insertion · navigation phase',
  orbit:        'stable orbit at destination',
  emergency:    'off-nominal · operator intervention',
};

const PHASE_TONE: Record<string, string> = {
  prelaunch:    'text-ui-text',
  boost:        'text-sev-warn',
  cruise:       'text-ui-accent',
  deceleration: 'text-sev-warn',
  arrival:      'text-sev-ok',
  orbit:        'text-sev-ok',
  emergency:    'text-sev-crit',
};

function formatDuration(years: number): string {
  if (years < 1)   return `${(years * 12).toFixed(1)} mo`;
  if (years < 100) return `${years.toFixed(1)} yr`;
  return `${years.toFixed(0)} yr`;
}

function formatLy(ly: number): string {
  if (ly < 1e-6) return '<1 µly';
  if (ly < 1e-3) return `${(ly * 1e6).toFixed(1)} µly`;
  if (ly < 1)    return `${ly.toFixed(3)} ly`;
  return `${ly.toFixed(2)} ly`;
}

export function MissionBrief() {
  const [traj, setTraj] = useState<TrajectoryStateApi | null>(null);
  const [phase, setPhase] = useState<PhaseState | null>(null);

  useEffect(() => {
    const refresh = () => {
      ariaApi.trajectory().then(setTraj).catch(() => {});
      ariaApi.missionPhase().then(setPhase).catch(() => {});
    };
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);

  const target    = traj?.target ?? '—';
  const totalLy   = traj?.distance_total_ly ?? 0;
  const fraction  = traj?.fraction_complete ?? 0;
  const elapsedYr = phase?.elapsed_yr ?? 0;
  const phaseId   = (phase?.current_phase ?? 'prelaunch').toLowerCase();
  const phaseTone = PHASE_TONE[phaseId] ?? 'text-ui-text';
  const phaseHint = PHASE_HINT[phaseId] ?? '';
  const fracPct   = Math.max(0, Math.min(100, fraction * 100));

  return (
    <section className="rounded-lg border border-ui-border bg-ui-bg-1/60 overflow-hidden">
      <div className="px-4 py-2 border-b border-ui-border-soft flex items-baseline justify-between gap-3 flex-wrap">
        <div className="text-[10px] uppercase tracking-widest text-ui-accent font-semibold">
          Live simulation
        </div>
        <div className="text-[10px] text-ui-text-faint">
          One scenario running on the digital-twin engine — switch speed in Mission Control
          to see it unfold.
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[1.4fr_1fr_1fr_1fr] divide-y md:divide-y-0 md:divide-x divide-ui-border-soft">
        <Stat label="Destination" big={target} sub={formatLy(totalLy)} accent />
        <Stat label="Crew"        big="1 000"  sub="colonists · cryo + rotation" />
        <Stat label="Mission T+"  big={formatDuration(elapsedYr)} sub="since launch" mono />
        <Stat label="Phase"       big={phaseId.toUpperCase()}    sub={phaseHint} bigClassName={phaseTone} />
      </div>

      <div className="px-4 py-2 border-t border-ui-border-soft">
        <div className="flex items-baseline justify-between text-[10px] text-ui-text-faint mb-1">
          <span className="uppercase tracking-wider">Voyage progress</span>
          <span className="font-mono">{fracPct.toFixed(2)} %</span>
        </div>
        <div className="h-1.5 bg-ui-bg-2 rounded overflow-hidden">
          <div className="h-full bg-ui-accent transition-all" style={{ width: `${fracPct}%` }} />
        </div>
      </div>
    </section>
  );
}

interface StatProps {
  label: string;
  big: string;
  sub: string;
  mono?: boolean;
  accent?: boolean;
  bigClassName?: string;
}

function Stat({ label, big, sub, mono, accent, bigClassName }: StatProps) {
  const bigCls =
    bigClassName ?? (accent ? 'text-ui-accent' : 'text-ui-text');
  return (
    <div className="px-4 py-3">
      <div className="text-[10px] uppercase tracking-widest text-ui-text-faint">{label}</div>
      <div className={`text-2xl font-semibold leading-tight mt-0.5 truncate ${mono ? 'font-mono' : ''} ${bigCls}`}>
        {big}
      </div>
      <div className="text-[10px] text-ui-text-faint mt-0.5 truncate">{sub}</div>
    </div>
  );
}

export default MissionBrief;
