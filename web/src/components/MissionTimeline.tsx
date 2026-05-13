/**
 * Mission Timeline — SVG Gantt chart of mission phases with event overlay.
 *
 * Shows the full mission as a horizontal bar divided into colored phase
 * segments (PRELAUNCH → BOOST → CRUISE → DECELERATION → ARRIVAL → ORBIT).
 * Events (hull impacts, phase transitions, flares, alarms) are plotted as
 * dots along the timeline. Click a segment to see phase details.
 *
 * Polls /api/mission/phase every 2s for phase history.
 * Polls /api/events/recent every 5s for event overlay.
 */

import { useEffect, useMemo, useState } from 'react';
import { ariaApi, type PhaseState, type BusEvent } from '../api/aria';
import { ProgrammeMilestones } from './ProgrammeMilestones';

const PHASE_COLORS: Record<string, string> = {
  prelaunch:    '#334155',
  boost:        '#f97316',
  cruise:       '#06b6d4',
  deceleration: '#eab308',
  arrival:      '#22c55e',
  orbit:        '#8b5cf6',
  emergency:    '#ef4444',
};

const PHASE_ORDER = ['prelaunch', 'boost', 'cruise', 'deceleration', 'arrival', 'orbit', 'emergency'];

const SEVERITY_COLORS: Record<string, string> = {
  debug:    '#475569',
  info:     '#3b82f6',
  warning:  '#eab308',
  critical: '#ef4444',
};

export function MissionTimeline() {
  const [phase, setPhase] = useState<PhaseState | null>(null);
  const [events, setEvents] = useState<BusEvent[]>([]);
  const [target, setTarget] = useState<string>('—');
  const [eventCap, setEventCap] = useState(500);

  useEffect(() => {
    const refreshPhase = () => ariaApi.missionPhase().then(setPhase).catch(() => {});
    refreshPhase();
    const t1 = setInterval(refreshPhase, 2000);
    return () => clearInterval(t1);
  }, []);

  useEffect(() => {
    ariaApi.trajectory().then(t => setTarget(t.target)).catch(() => {});
  }, []);

  useEffect(() => {
    const refreshEvents = () =>
      ariaApi.eventsRecent(eventCap).then(r => setEvents(r.events)).catch(() => {});
    refreshEvents();
    const t2 = setInterval(refreshEvents, 5000);
    return () => clearInterval(t2);
  }, [eventCap]);

  // Build phase segments from history
  const segments = useMemo(() => {
    if (!phase) return [];
    const history = phase.history;
    if (!history || history.length === 0) {
      // Only current phase, no transitions yet
      return [{ phase: phase.current_phase, from_yr: 0, to_yr: Math.max(phase.elapsed_yr, 0.01) }];
    }

    const segs: { phase: string; from_yr: number; to_yr: number }[] = [];
    // First segment: from 0 to first transition
    segs.push({
      phase: history[0].from,
      from_yr: 0,
      to_yr: history[0].at_yr,
    });
    // Middle segments: between transitions
    for (let i = 0; i < history.length; i++) {
      const end = i + 1 < history.length ? history[i + 1].at_yr : phase.elapsed_yr;
      segs.push({
        phase: history[i].to,
        from_yr: history[i].at_yr,
        to_yr: end,
      });
    }
    return segs.filter(s => s.to_yr > s.from_yr);
  }, [phase]);

  if (!phase) return <div className="p-4 text-sm text-ui-text-dim">Loading timeline...</div>;

  const totalYr = Math.max(phase.elapsed_yr, 0.01);
  const SVG_W = 1000;
  const SVG_H = 150;
  const BAR_Y = 20;
  const BAR_H = 36;
  const HIST_Y = BAR_Y + BAR_H + 6;
  const HIST_H = 22;
  const DOT_Y  = HIST_Y + HIST_H + 8;
  const PAD = 20;
  const BIN_COUNT = totalYr > 10 ? 18 : totalYr > 1 ? 14 : 10;

  const yrToX = (yr: number) => PAD + (yr / totalYr) * (SVG_W - 2 * PAD);

  const binWidth = totalYr / BIN_COUNT;
  const bins: { count: number; maxSev: 'info' | 'warning' | 'critical' | null }[] = Array.from(
    { length: BIN_COUNT },
    () => ({ count: 0, maxSev: null }),
  );
  const SEV_RANK: Record<string, number> = { info: 1, warning: 2, critical: 3 };
  for (const ev of events) {
    if (ev.sim_time_yr < 0 || ev.sim_time_yr > totalYr) continue;
    const idx = Math.min(BIN_COUNT - 1, Math.floor(ev.sim_time_yr / binWidth));
    bins[idx].count += 1;
    const sev = (ev.severity ?? 'info') as 'info' | 'warning' | 'critical';
    if (!bins[idx].maxSev || SEV_RANK[sev] > SEV_RANK[bins[idx].maxSev!]) bins[idx].maxSev = sev;
  }
  const maxBin = Math.max(1, ...bins.map(b => b.count));

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-2 border-b border-ui-border flex items-center justify-between gap-2 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-ui-accent font-bold">
            Mission Timeline · destination {target}
          </div>
          <div className="text-[10px] text-ui-text-dim">
            {phase.elapsed_yr.toFixed(3)} yr elapsed · {phase.current_phase.toUpperCase()} ·{' '}
            {phase.history?.length || 0} transitions · {events.length} events
            {events.length >= eventCap && <span className="text-sev-warn"> (capped)</span>}
          </div>
        </div>
        <label className="text-[10px] text-ui-text-faint inline-flex items-center gap-1">
          show last
          <select value={eventCap}
                  onChange={(e) => setEventCap(Number(e.target.value))}
                  className="bg-ui-bg-2 border border-ui-border text-ui-text rounded px-1 py-0.5 text-[10px] cursor-pointer">
            <option value={200}>200</option>
            <option value={500}>500</option>
            <option value={1000}>1000</option>
            <option value={2000}>2000</option>
          </select>
          events
        </label>
      </div>

      <div className="flex-1 px-3 py-2">
        <svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} className="w-full" preserveAspectRatio="xMidYMid meet">
          {/* Phase bar segments */}
          {segments.map((seg, i) => {
            const x1 = yrToX(seg.from_yr);
            const x2 = yrToX(seg.to_yr);
            const w = Math.max(x2 - x1, 1);
            return (
              <g key={i}>
                <rect
                  x={x1} y={BAR_Y} width={w} height={BAR_H} rx={3}
                  fill={PHASE_COLORS[seg.phase] || '#334155'}
                  stroke="#0f172a" strokeWidth={0.5}
                />
                {w > 50 && (
                  <text
                    x={x1 + w / 2} y={BAR_Y + BAR_H / 2 + 4}
                    textAnchor="middle" fontSize="11" fontWeight="600"
                    fill="white" pointerEvents="none"
                  >
                    {seg.phase.toUpperCase()}
                  </text>
                )}
              </g>
            );
          })}

          {/* Current position indicator */}
          <line
            x1={yrToX(phase.elapsed_yr)} y1={BAR_Y - 5}
            x2={yrToX(phase.elapsed_yr)} y2={BAR_Y + BAR_H + 5}
            stroke="#06b6d4" strokeWidth={2}
          />
          <polygon
            points={`${yrToX(phase.elapsed_yr) - 4},${BAR_Y - 5} ${yrToX(phase.elapsed_yr) + 4},${BAR_Y - 5} ${yrToX(phase.elapsed_yr)},${BAR_Y - 1}`}
            fill="#06b6d4"
          />

          {/* Event-density histogram (events binned per Mission Year). Empty bins
              render as a faint 1-unit tall baseline so the bin grid is always visible. */}
          <text x={PAD - 4} y={HIST_Y + HIST_H + 4} textAnchor="end" fontSize="6"
                fill="#475569">events/yr</text>
          <line
            x1={PAD} y1={HIST_Y + HIST_H}
            x2={SVG_W - PAD} y2={HIST_Y + HIST_H}
            stroke="#334155" strokeWidth={0.5}
          />
          {bins.map((b, i) => {
            const fromYr = i * binWidth;
            const toYr = (i + 1) * binWidth;
            const x = yrToX(fromYr);
            const w = Math.max(yrToX(toYr) - x - 0.5, 2);
            if (b.count === 0) {
              return (
                <rect key={`bin-${i}`} x={x} y={HIST_Y + HIST_H - 1}
                      width={w} height={1} fill="#334155" opacity={0.5}>
                  <title>{`yr ${fromYr.toFixed(2)}–${toYr.toFixed(2)} · 0 events`}</title>
                </rect>
              );
            }
            const h = Math.max(2, (b.count / maxBin) * HIST_H);
            const color = b.maxSev ? (SEVERITY_COLORS[b.maxSev] || '#06b6d4') : '#06b6d4';
            return (
              <rect key={`bin-${i}`}
                    x={x} y={HIST_Y + HIST_H - h}
                    width={w} height={h}
                    fill={color} opacity={0.85}>
                <title>{`yr ${fromYr.toFixed(2)}–${toYr.toFixed(2)} · ${b.count} events · max ${b.maxSev ?? 'info'}`}</title>
              </rect>
            );
          })}

          {/* Event dots below the histogram */}
          {events.map((ev, i) => {
            if (ev.sim_time_yr <= 0 || ev.sim_time_yr > totalYr * 1.1) return null;
            const x = yrToX(ev.sim_time_yr);
            const color = SEVERITY_COLORS[ev.severity] || '#475569';
            return (
              <circle
                key={i} cx={x} cy={DOT_Y} r={ev.severity === 'critical' ? 3 : 2}
                fill={color} opacity={0.8}
              >
                <title>{`yr ${ev.sim_time_yr.toFixed(3)} · ${ev.severity} · ${ev.topic}`}</title>
              </circle>
            );
          })}

          {/* Time axis */}
          {Array.from({ length: 11 }, (_, i) => {
            const yr = (totalYr * i) / 10;
            const x = yrToX(yr);
            return (
              <g key={`tick-${i}`}>
                <line x1={x} y1={DOT_Y + 6} x2={x} y2={DOT_Y + 10} stroke="#475569" strokeWidth={1} />
                <text x={x} y={DOT_Y + 22} textAnchor="middle" fontSize="8" fill="#64748b">
                  {yr < 1 ? yr.toFixed(3) : yr < 100 ? yr.toFixed(1) : yr.toFixed(0)}
                </text>
              </g>
            );
          })}

          {/* Axis label */}
          <text x={SVG_W / 2} y={SVG_H - 2} textAnchor="middle" fontSize="9" fill="#475569">
            Mission Year
          </text>
        </svg>
      </div>

      {/* Phase legend */}
      <div className="px-3 py-1 border-t border-ui-border flex flex-wrap gap-3 text-[9px]">
        {PHASE_ORDER.map(p => (
          <div key={p} className="flex items-center gap-1">
            <div className="w-3 h-2 rounded-sm" style={{ background: PHASE_COLORS[p] }} />
            <span className="text-ui-text-dim">{p}</span>
          </div>
        ))}
        <div className="ml-auto flex gap-2">
          {(['info', 'warning', 'critical'] as const).map(sev => (
            <div key={sev} className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full" style={{ background: SEVERITY_COLORS[sev] }} />
              <span className="text-ui-text-dim">{sev}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="px-3 py-2 border-t border-ui-border">
        <div className="text-[10px] uppercase tracking-widest text-ui-accent font-bold mb-1">
          Real-world programme overlay
        </div>
        <ProgrammeMilestones program="artemis2" compact />
      </div>
    </div>
  );
}
