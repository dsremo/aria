/**
 * Thin 28 px always-visible status bar.
 *
 * Shows mission phase · elapsed sim clock · speed · active alarm count.
 * Deliberately info-only — no controls here. Controls live in Mission
 * Control. Keeps the strip shallow so the 3D viewport and chart panels
 * retain their vertical real estate.
 *
 * Polls:
 *   - /api/mission/phase           every  3 s (current_phase, elapsed_yr)
 *   - /api/auto-tick/status        every  3 s (running, speed_factor)
 *   - /api/events/recent?minSev=warning every 5 s (alarm count)
 *
 * Click the alarm badge to jump to the Alarms tab.
 */

import { useEffect, useState } from 'react';
import { ariaApi } from '../api/aria';
import type { Tab } from '../App';

interface Tick {
  phase: string;
  elapsed_yr: number;
  running: boolean;
  speed_factor: number;
  alarms: number;
}

function formatClock(years: number): string {
  if (years < 1 / 365 / 24) {
    const mins = years * 365 * 24 * 60;
    return `${mins.toFixed(1)} min`;
  }
  if (years < 1 / 365) {
    const hrs = years * 365 * 24;
    return `${hrs.toFixed(1)} h`;
  }
  if (years < 1) {
    const days = years * 365;
    return `${days.toFixed(1)} d`;
  }
  return `${years.toFixed(2)} yr`;
}

function formatSpeed(factor: number): string {
  // factor = seconds of sim per second of wall clock
  if (factor >= 2_592_000) return `${(factor / 2_592_000).toFixed(0)} mo/s`;
  if (factor >= 604_800)   return `${(factor / 604_800).toFixed(0)} wk/s`;
  if (factor >= 86_400)    return `${(factor / 86_400).toFixed(0)} d/s`;
  if (factor >= 3_600)     return `${(factor / 3_600).toFixed(0)} h/s`;
  if (factor >= 60)        return `${(factor / 60).toFixed(0)} min/s`;
  return `${factor.toFixed(1)} s/s`;
}

export function StatusStrip({ onGoto }: { onGoto: (t: Tab | string) => void }) {
  const [t, setT] = useState<Tick>({ phase: '—', elapsed_yr: 0, running: false, speed_factor: 0, alarms: 0 });

  useEffect(() => {
    let alive = true;
    const pullCore = async () => {
      try {
        const [ph, at] = await Promise.all([
          ariaApi.missionPhase().catch(() => null),
          ariaApi.autoTickStatus().catch(() => null),
        ]);
        if (!alive) return;
        setT((prev) => ({
          ...prev,
          phase: ph?.current_phase ?? prev.phase,
          elapsed_yr: ph?.elapsed_yr ?? prev.elapsed_yr,
          running: Boolean(at?.running),
          speed_factor: Number(at?.speed_factor ?? 0),
        }));
      } catch { /* swallow — strip is cosmetic, never block UI */ }
    };
    const pullAlarms = async () => {
      try {
        // BUG-036 (2026-04-24, walkthrough): was 50 — AlarmsPanel
        // asks for 200, so the status strip under-counted whenever
        // there were more than 50 warning+ events.  Match Alarms.
        const r = await ariaApi.eventsRecent(200, undefined, 'warning');
        if (!alive) return;
        const count = (r?.events ?? []).filter((e: any) => {
          const sev = String(e.severity ?? '').toLowerCase();
          return sev === 'warning' || sev === 'critical' || sev === 'emergency';
        }).length;
        setT((prev) => ({ ...prev, alarms: count }));
      } catch { /* ignore */ }
    };
    pullCore(); pullAlarms();
    // BUG-019 partial (2026-04-24, walkthrough): the 3 s core poll made
    // the status-strip T+ lag the Mission-Control footer by up to 3 s
    // during cold-start — long enough to produce a visibly different
    // clock reading (14.6 d vs 22 d at 1 mo/s). Both panels read the
    // *same* MissionClock on the backend, so the disagreement was pure
    // poll skew. Drop to 1 s so the UI strip's MissionClock sample is
    // fresh before any operator screen-compares with MissionPanel (2 s
    // poll) or the auto-tick cumulative read (live).
    const a = setInterval(pullCore, 1000);
    const b = setInterval(pullAlarms, 5000);
    return () => { alive = false; clearInterval(a); clearInterval(b); };
  }, []);

  const phaseColor =
    t.phase.toLowerCase().includes('emergency') ? 'text-sev-crit' :
    t.phase.toLowerCase().includes('arrival')   ? 'text-sev-ok' :
    t.phase.toLowerCase().includes('cruise')    ? 'text-ui-accent' :
    t.phase.toLowerCase().includes('boost')     ? 'text-sev-warn' :
    'text-ui-text';

  return (
    <div className="flex items-center gap-3 text-[11px] font-mono select-none">
      <span className="hidden md:flex items-center gap-1.5">
        <span className={`inline-block w-1.5 h-1.5 rounded-full ${t.running ? 'bg-sev-ok animate-pulse' : 'bg-ui-text-faint'}`} />
        <span className="text-ui-text-faint">PHASE</span>
        <span className={`${phaseColor} font-semibold uppercase tracking-wider`}>{t.phase}</span>
      </span>
      <span className="hidden md:inline">
        <span className="text-ui-text-faint">T+ </span>
        <span className="text-ui-text tabular-nums">{formatClock(t.elapsed_yr)}</span>
      </span>
      <span className="hidden lg:inline">
        <span className="text-ui-text-faint">SPEED </span>
        <span className="text-ui-text tabular-nums">
          {t.running ? formatSpeed(t.speed_factor) : 'paused'}
        </span>
      </span>
      <button
        onClick={() => onGoto('alarms')}
        title={t.alarms > 0 ? `${t.alarms} active warning/critical events — click to view` : 'No active alarms'}
        className={`flex items-center gap-1 px-2 py-0.5 rounded transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ui-accent ${
          t.alarms > 0
            ? 'bg-sev-crit/30 border border-sev-crit text-sev-crit hover:bg-sev-crit/40'
            : 'border border-ui-border text-ui-text-faint hover:text-ui-text-dim hover:border-ui-border-strong'
        }`}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-current inline-block" />
        <span className="tabular-nums">{t.alarms}</span>
        <span className="hidden sm:inline">{t.alarms === 1 ? 'alarm' : 'alarms'}</span>
      </button>
    </div>
  );
}
