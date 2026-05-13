/**
 * Critical / warning alarms aggregation.
 *
 * Polls /api/events/recent with min_severity=warning, groups by topic
 * stem, and surfaces the most urgent issues first.  Operator can × a
 * row to suppress it locally; the row auto-unsuppresses if a NEW event
 * fires in that stem (i.e. situation worsened) so you can't accidentally
 * hide a bug by dismissing it once.
 *
 * Design note: bus events are an append-only history, not
 * fault-manager objects, so "dismissal" is inherently a *client-side*
 * concern — the backend has no reason to forget that an event was
 * published.  We persist suppress keys + their wall-clock dismiss
 * timestamps in localStorage so the preference survives refresh, but
 * still let the next genuine alarm through.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Bell, BellOff } from 'lucide-react';
import { ariaApi, type BusEvent } from '../api/aria';
import { SeverityBadge } from './SeverityBadge';
import { EmptyState } from './EmptyState';

const SUPPRESS_KEY = 'aria.alarms.suppressed';

/** Dismissed stem → wall-clock seconds at which the user clicked ×.
 *  Any event with timestamp strictly greater unsuppresses the stem. */
type SuppressMap = Record<string, number>;

function loadSuppress(): SuppressMap {
  try {
    const raw = localStorage.getItem(SUPPRESS_KEY);
    if (!raw) return {};
    const j = JSON.parse(raw);
    return typeof j === 'object' && j ? j as SuppressMap : {};
  } catch { return {}; }
}

function saveSuppress(m: SuppressMap): void {
  try { localStorage.setItem(SUPPRESS_KEY, JSON.stringify(m)); } catch { /* quota */ }
}

export function AlarmsPanel() {
  const [events, setEvents] = useState<BusEvent[]>([]);
  const [minSev, setMinSev] = useState<'warning'|'critical'>('warning');
  const [suppressed, setSuppressed] = useState<SuppressMap>(() => loadSuppress());
  // Re-persist whenever the map changes so hard-refresh keeps the suppressions.
  const suppressedRef = useRef(suppressed);
  useEffect(() => { suppressedRef.current = suppressed; saveSuppress(suppressed); }, [suppressed]);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await ariaApi.eventsRecent(200, undefined, minSev);
        if (!cancelled) setEvents(r.events);
      } catch (e) { /* silent */ }
    };
    tick();
    const t = setInterval(tick, 2000);
    return () => { cancelled = true; clearInterval(t); };
  }, [minSev]);

  const grouped = useMemo(() => {
    // Group by topic-stem (everything before the last segment) so e.g.
    // eclss.contaminant.ethylene.alarm + eclss.contaminant.formaldehyde.alarm
    // show as two rows under "eclss.contaminant.*"
    const byStem: Record<string, { events: BusEvent[]; latest: BusEvent }> = {};
    for (const e of events) {
      const stem = e.topic.split('.').slice(0, -1).join('.') || e.topic;
      if (!byStem[stem]) byStem[stem] = { events: [], latest: e };
      byStem[stem].events.push(e);
      if (e.timestamp > byStem[stem].latest.timestamp) byStem[stem].latest = e;
    }
    return Object.entries(byStem).sort((a, b) => b[1].latest.timestamp - a[1].latest.timestamp);
  }, [events]);

  // Visible = not currently suppressed.  A stem stops being suppressed
  // the moment a newer event shows up — this way a pressing situation
  // can never be hidden by yesterday's dismissal.
  const { visible, hiddenStems } = useMemo(() => {
    const vis: typeof grouped = [];
    const hidden: string[] = [];
    for (const [stem, g] of grouped) {
      const sup = suppressed[stem];
      if (sup !== undefined && g.latest.timestamp <= sup) {
        hidden.push(stem);
      } else {
        vis.push([stem, g]);
      }
    }
    return { visible: vis, hiddenStems: hidden };
  }, [grouped, suppressed]);

  const dismiss = (stem: string) => {
    setSuppressed((prev) => ({ ...prev, [stem]: Date.now() / 1000 }));
  };

  const dismissAll = () => {
    const now = Date.now() / 1000;
    setSuppressed((prev) => {
      const next = { ...prev };
      for (const [stem] of visible) next[stem] = now;
      return next;
    });
  };

  const clearSuppressions = () => {
    setSuppressed({});
  };

  const criticalCount = events.filter(e => e.severity === 'critical').length;
  const warningCount  = events.filter(e => e.severity === 'warning').length;
  const visibleCrit   = visible.flatMap(([, g]) => g.events).filter(e => e.severity === 'critical').length;

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-2 border-b border-ui-border flex items-center gap-2 flex-wrap">
        <div className="text-[10px] uppercase tracking-wider text-ui-accent font-bold whitespace-nowrap">
          Active Alarms
        </div>
        <div className="ml-auto flex items-center gap-3 text-[10px] flex-wrap whitespace-nowrap">
          <SeverityBadge severity="crit" variant="dot"><span className="whitespace-nowrap">{criticalCount} critical</span></SeverityBadge>
          <SeverityBadge severity="warn" variant="dot"><span className="whitespace-nowrap">{warningCount} warning</span></SeverityBadge>
          {visible.length >= 2 && (
            <button onClick={dismissAll}
                    className="px-2 py-0.5 rounded border border-ui-border-strong bg-ui-bg-1
                               text-ui-text hover:border-ui-accent hover:bg-ui-bg-2">
              Dismiss all ({visible.length})
            </button>
          )}
          {hiddenStems.length > 0 && (
            <button onClick={clearSuppressions}
                    className="px-2 py-0.5 rounded border border-sev-warn bg-sev-warn/30
                               text-sev-warn hover:bg-sev-warn/40"
                    title={`Currently hiding: ${hiddenStems.join(', ')}`}>
              ⊙ Show all (+{hiddenStems.length} hidden)
            </button>
          )}
          <select value={minSev} onChange={e => setMinSev(e.target.value as any)}
                  className="px-1 py-0.5 bg-ui-bg-2 border border-ui-border rounded text-xs">
            <option value="warning">warning+</option>
            <option value="critical">critical only</option>
          </select>
        </div>
      </div>

      {visible.length === 0 && (
        hiddenStems.length > 0
          ? <EmptyState Icon={BellOff}
              title="All current alarms dismissed"
              hint={<>{hiddenStems.length} stem{hiddenStems.length > 1 ? 's' : ''} will reappear if a fresher event fires.</>} />
          : <EmptyState Icon={Bell}
              title="No active alarms"
              hint="Tick the engine or simulate a fault to see events here." />
      )}

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {visible.map(([stem, { events: evs, latest }]) => {
          const sev = latest.severity;
          const border = sev === 'critical' ? 'border-sev-crit bg-sev-crit/30'
                       : sev === 'warning'  ? 'border-sev-warn bg-sev-warn/20'
                       : 'border-sev-info';
          return (
            <div key={stem} className={`p-2 rounded border ${border} group relative`}>
              <button
                onClick={() => dismiss(stem)}
                className="absolute top-1 right-1 px-1.5 py-0 text-[10px]
                           text-ui-text-dim hover:text-white hover:bg-ui-bg-2 rounded"
                title="Dismiss this alarm stem — will reappear if a newer event fires">
                ✕
              </button>
              <div className="flex items-baseline gap-2 pr-5">
                <div className="text-[11px] font-bold text-ui-accent">{stem}.*</div>
                <div className="text-[9px] text-ui-text-faint">{evs.length} occurrence{evs.length > 1 ? 's' : ''}</div>
                <div className="ml-auto text-[9px] text-ui-text-faint">{relativeTime(latest.timestamp)}</div>
              </div>
              <div className="text-[10px] text-ui-text mt-0.5">
                Latest: <span className="text-ui-text">{latest.topic}</span> from <span className="text-ui-text-dim">{latest.source}</span>
              </div>
              {Object.keys(latest.payload).length > 0 && (
                <div className="text-[10px] text-ui-text-dim font-mono mt-1 max-w-full truncate">
                  {JSON.stringify(latest.payload)}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {visible.length > 0 && visibleCrit === 0 && criticalCount > 0 && (
        <div className="px-3 py-1 border-t border-ui-border text-[10px] text-sev-warn">
          ⚠ {criticalCount - visibleCrit} critical alarm{criticalCount - visibleCrit > 1 ? 's' : ''} currently dismissed — click "Show all" above to review.
        </div>
      )}
    </div>
  );
}

function relativeTime(unixSec: number): string {
  const dt = (Date.now() / 1000) - unixSec;
  if (dt < 60)    return `${dt.toFixed(0)} s ago`;
  if (dt < 3600)  return `${(dt / 60).toFixed(0)} min ago`;
  if (dt < 86400) return `${(dt / 3600).toFixed(1)} hr ago`;
  return `${(dt / 86400).toFixed(1)} d ago`;
}
