/**
 * Power Flow Diagram — simplified Sankey showing reactor → subsystem power distribution.
 *
 * Polls /api/power/budget for the current allocation table, then renders
 * as a left-to-right flow: Reactor (source) → each subsystem (sink).
 * Width of each flow line proportional to allocated watts.
 * Shed loads are shown in red.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type PowerBudget } from '../api/aria';

export function PowerFlowDiagram() {
  const [pb, setPb] = useState<PowerBudget | null>(null);

  useEffect(() => {
    const refresh = () => ariaApi.powerBudget().then(setPb).catch(() => {});
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);

  if (!pb) return <div className="p-4 text-sm text-ui-text-dim">Loading power budget...</div>;

  const { summary, subsystems } = pb;

  if (subsystems.length === 0 || summary.available_w === 0 || subsystems.every(subsystem => subsystem.allocated_w === 0)) {
    return (
      <div style={{textAlign:'center', color:'#888', padding:'2rem'}}>
        Reactor offline — power flow will populate once the reactor reaches operational power.
        Start the Cold-Start Sequence from Mission Control to activate.
      </div>
    );
  }
  // Sort by allocation descending
  const sorted = [...subsystems].filter(subsystem => subsystem.allocated_w > 0).sort((a, b) => b.allocated_w - a.allocated_w);
  const maxAlloc = sorted[0]?.allocated_w || 1;

  const SVG_W = 900;
  const SVG_H = Math.max(300, sorted.length * 32 + 80);
  const SRC_X = 80;
  const SINK_X = SVG_W - 200;
  const BAR_START_Y = 50;
  const ROW_H = 28;

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Power Flow</h2>
        <p className="text-xs text-ui-text-dim">
          Reactor → subsystems. {(summary.available_w / 1e6).toFixed(1)} MW available,{' '}
          {(summary.allocated_w / 1e6).toFixed(2)} MW allocated, {summary.margin_pct.toFixed(1)}% margin.
          {pb.stats.total_shed_events > 0 && (
            <span className="text-sev-warn"> {pb.stats.total_shed_events} load-shed events.</span>
          )}
        </p>
      </div>

      <svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} className="w-full">
        {/* Source: Reactor */}
        <rect x={20} y={BAR_START_Y} width={50} height={sorted.length * ROW_H}
              rx={6} fill="#ef4444" fillOpacity={0.7} stroke="#ef4444" />
        <text x={45} y={BAR_START_Y - 10} textAnchor="middle" fontSize="11" fontWeight="700" fill="#ef4444">
          Reactor
        </text>
        <text x={45} y={BAR_START_Y - 0} textAnchor="middle" fontSize="9" fill="#94a3b8">
          {(summary.available_w / 1e6).toFixed(1)} MW
        </text>

        {/* Flow lines + sink bars */}
        {sorted.map((sub, i) => {
          const y = BAR_START_Y + i * ROW_H + ROW_H / 2;
          const flowWidth = Math.max(1, (sub.allocated_w / maxAlloc) * 14);
          const barW = (sub.allocated_w / summary.available_w) * 300;
          const color = sub.shed ? '#ef4444' : sub.priority >= 80 ? '#06b6d4' : '#3b82f6';

          return (
            <g key={sub.name}>
              {/* Flow line from reactor to subsystem */}
              <path
                d={`M 70 ${BAR_START_Y + sorted.length * ROW_H / 2} C ${SRC_X + 80} ${BAR_START_Y + sorted.length * ROW_H / 2}, ${SINK_X - 200} ${y}, ${SINK_X - 10} ${y}`}
                fill="none" stroke={color} strokeWidth={flowWidth}
                strokeOpacity={0.5} strokeLinecap="round"
              />

              {/* Subsystem bar */}
              <rect x={SINK_X} y={y - 8} width={Math.max(barW, 2)} height={16}
                    rx={3} fill={color} fillOpacity={0.8} />

              {/* Label */}
              <text x={SINK_X + Math.max(barW, 2) + 8} y={y + 4} fontSize="10" fill="#e2e8f0">
                {sub.name}
              </text>

              {/* Value */}
              <text x={SINK_X - 14} y={y + 4} textAnchor="end" fontSize="9" fill="#94a3b8" fontFamily="monospace">
                {sub.allocated_w >= 1e6 ? `${(sub.allocated_w / 1e6).toFixed(1)}M` : `${(sub.allocated_w / 1e3).toFixed(0)}k`} W
              </text>

              {/* Shed indicator */}
              {sub.shed && (
                <text x={SINK_X + Math.max(barW, 2) + 8 + sub.name.length * 6 + 8} y={y + 4}
                      fontSize="9" fill="#ef4444" fontWeight="700">
                  SHED
                </text>
              )}
            </g>
          );
        })}

        {/* Margin indicator */}
        <rect x={20} y={SVG_H - 35} width={SVG_W - 40} height={20} rx={4}
              fill="#1e293b" stroke="#334155" />
        <rect x={20} y={SVG_H - 35}
              width={Math.max(0, (SVG_W - 40) * (1 - summary.margin_pct / 100))}
              height={20} rx={4}
              fill={summary.margin_pct > 30 ? '#22c55e' : summary.margin_pct > 10 ? '#eab308' : '#ef4444'}
              fillOpacity={0.6} />
        <text x={SVG_W / 2} y={SVG_H - 21} textAnchor="middle" fontSize="10" fill="white" fontWeight="600">
          {(summary.allocated_w / 1e6).toFixed(2)} / {(summary.available_w / 1e6).toFixed(1)} MW used · {summary.margin_pct.toFixed(1)}% margin
        </text>
      </svg>
    </div>
  );
}
