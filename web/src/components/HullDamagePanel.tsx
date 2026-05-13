/**
 * Hull damage map — top-down silhouette of the ship with each of the 10
 * regions colour-coded by health %. Click a region to highlight + repair.
 *
 * Polls /api/hull/damage every 2 s.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type HullDamage, type HullRegion } from '../api/aria';

const SVG_W = 1000;
const SVG_H = 220;
const PAD = 60;

export function HullDamagePanel() {
  const [data, setData] = useState<HullDamage | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    const refresh = () => ariaApi.hullDamage().then(setData).catch(() => {});
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);

  if (!data) return <div className="p-4 text-sm text-ui-text-dim">Loading hull damage…</div>;

  const repair = async (rid: string, all = false) => {
    const r = await ariaApi.hullRepair(rid, all);
    setData(r.state);
  };
  const impact = async (rid: string, energy: number) => {
    await ariaApi.hullImpact(rid, energy);
    setData(await ariaApi.hullDamage());
  };

  // Compute X bounds across all regions for SVG mapping
  const xMin = Math.min(...data.regions.map(r => r.x_start_m));
  const xMax = Math.max(...data.regions.map(r => r.x_end_m));
  // Guard against zero-width payload (single region or degenerate state) —
  // otherwise (x - xMin) / 0 produces NaN and breaks SVG layout.
  const xSpan = Math.max(xMax - xMin, 1e-6);

  const xToSvg = (x: number) =>
    PAD + (x - xMin) / xSpan * (SVG_W - 2 * PAD);

  const sel = data.regions.find(r => r.region_id === selected) ?? null;

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-2 border-b border-ui-border flex items-center gap-3">
        <div className="text-[10px] uppercase tracking-wider text-ui-accent font-bold">
          Hull Damage Map · 10 regions
        </div>
        <div className="text-[10px] text-ui-text-faint">
          {data.stats.total_impacts} impacts · {data.stats.repairs_pending} pending repairs · worst region: <span className="text-sev-warn">{data.stats.worst_region}</span> ({(data.stats.worst_fatigue * 100).toFixed(2)} % fatigue)
        </div>
      </div>

      {/* Ship silhouette */}
      <div className="px-3 py-2">
        <svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} className="w-full">
          {/* Each region as a rounded rectangle */}
          {data.regions.map(r => {
            const x0 = xToSvg(r.x_start_m);
            const x1 = xToSvg(r.x_end_m);
            const w = x1 - x0;
            const fill = healthFill(r.health_pct);
            const isSel = selected === r.region_id;
            return (
              <g key={r.region_id}
                 className="cursor-pointer"
                 onClick={() => setSelected(r.region_id)}>
                <rect
                  x={x0} y={70} width={w} height={80} rx="4"
                  fill={fill}
                  stroke={isSel ? '#06b6d4' : (r.repair_queue_depth > 0 ? '#f59e0b' : '#1e3a5f')}
                  strokeWidth={isSel ? 3 : (r.repair_queue_depth > 0 ? 2 : 1)} />
                <text x={(x0 + x1) / 2} y={115} textAnchor="middle"
                      fontSize="10" fontWeight="700" fill="#e2e8f0" pointerEvents="none">
                  {r.label.replace('Hull Zone ', 'Z').replace('Bow Shield Cone', 'BowShield').replace('Stern Nozzle', 'Nozzle')}
                </text>
                <text x={(x0 + x1) / 2} y={130} textAnchor="middle"
                      fontSize="9" fill="#cbd5e1" pointerEvents="none">
                  {r.health_pct.toFixed(1)}%
                </text>
                {r.repair_queue_depth > 0 && (
                  <text x={(x0 + x1) / 2} y={62} textAnchor="middle"
                        fontSize="11" fill="#fbbf24" pointerEvents="none">
                    ⚠{r.repair_queue_depth}
                  </text>
                )}
              </g>
            );
          })}
          {/* Centerline */}
          <line x1={PAD} y1={110} x2={SVG_W - PAD} y2={110}
                stroke="#475569" strokeWidth="1" strokeDasharray="2 3" opacity="0.4" />
          {/* Axis labels */}
          <text x={PAD} y={195} fontSize="10" fill="#64748b">stern (−x)</text>
          <text x={SVG_W - PAD} y={195} textAnchor="end" fontSize="10" fill="#64748b">bow (+x)</text>
        </svg>
      </div>

      {/* Selected region detail */}
      {sel && (
        <div className="mx-3 p-3 bg-ui-bg-1/60 border border-ui-accent rounded mb-2">
          <div className="flex items-baseline justify-between mb-2">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-ui-text-faint">Selected region</div>
              <div className="text-base font-bold text-ui-accent">{sel.label}</div>
            </div>
            <button onClick={() => setSelected(null)}
                    className="text-[10px] text-ui-text-dim hover:text-ui-text">close ✕</button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-1 text-[10px] mb-2">
            <Stat label="Impacts" value={String(sel.impact_count)} />
            <Stat label="Cum. energy" value={`${(sel.cumulative_energy_j / 1000).toFixed(1)} kJ`} />
            <Stat label="Fatigue" value={`${(sel.fatigue_index * 100).toFixed(3)} %`} />
            <Stat label="Health" value={`${sel.health_pct.toFixed(2)} %`} color={sel.health_pct < 80 ? 'text-sev-crit' : 'text-sev-ok'} />
            <Stat label="Repair queue" value={String(sel.repair_queue_depth)} color={sel.repair_queue_depth > 0 ? 'text-sev-warn' : undefined} />
            <Stat label="Last impact" value={sel.last_impact_at_yr != null ? `yr ${sel.last_impact_at_yr.toFixed(2)}` : '—'} />
            <Stat label="X start" value={`${sel.x_start_m.toFixed(0)} m`} />
            <Stat label="X end" value={`${sel.x_end_m.toFixed(0)} m`} />
          </div>

          {/* Cumulative-damage sparkline for this region.  X = sim time,
              Y = running cumulative energy (kJ).  Pulled from the global
              impacts log filtered by `region_id`.  Zero history → hint
              text; otherwise a monotone step curve that immediately
              reveals whether impacts are clustered (steep steps) or
              spread (gentle slope). */}
          <RegionDamageSparkline
            impacts={data.recent_impacts.filter((i) => i.region_id === sel.region_id)} />

          <div className="flex flex-wrap gap-1 mt-2">
            <button onClick={() => repair(sel.region_id, false)}
                    disabled={sel.repair_queue_depth === 0}
                    className="px-2 py-0.5 text-[10px] rounded border border-sev-ok bg-sev-ok/30 hover:bg-sev-ok/50 disabled:opacity-30">
              Repair 1
            </button>
            <button onClick={() => repair(sel.region_id, true)}
                    disabled={sel.repair_queue_depth === 0}
                    className="px-2 py-0.5 text-[10px] rounded border border-sev-ok bg-sev-ok/30 hover:bg-sev-ok/50 disabled:opacity-30">
              Repair All ({sel.repair_queue_depth})
            </button>
            <span className="ml-2 text-[10px] text-ui-text-faint self-center">Inject impact:</span>
            <button onClick={() => impact(sel.region_id, 1000)}
                    className="px-2 py-0.5 text-[10px] rounded border border-sev-warn bg-sev-warn/30 hover:bg-sev-warn/50">
              1 kJ
            </button>
            <button onClick={() => impact(sel.region_id, 10_000)}
                    className="px-2 py-0.5 text-[10px] rounded border border-sev-warn bg-sev-warn/30 hover:bg-sev-warn/50">
              10 kJ
            </button>
            <button onClick={() => impact(sel.region_id, 100_000)}
                    className="px-2 py-0.5 text-[10px] rounded border border-sev-crit bg-sev-crit/30 hover:bg-sev-crit/50">
              100 kJ
            </button>
          </div>
        </div>
      )}

      {/* Recent impacts log */}
      <div className="px-3 pt-1 pb-3 flex-1 overflow-y-auto">
        <div className="text-[10px] uppercase tracking-wider text-ui-text-faint mb-1">
          Recent impacts ({data.recent_impacts.length})
        </div>
        {data.recent_impacts.length === 0 && (
          <div className="text-[10px] text-ui-text-faint italic">
            No impacts yet. Trigger one above, or enable random events in Mission Control to simulate cruise-time MMOD strikes.
          </div>
        )}
        <div className="space-y-0.5">
          {data.recent_impacts.slice().reverse().slice(0, 30).map(i => (
            <div key={i.impact_id} className="text-[10px] flex justify-between">
              <span className="text-ui-text">
                <span className="text-ui-text-faint">[{i.impact_id}]</span> {i.region_id} · {i.energy_j.toFixed(0)} J
              </span>
              <span className="text-ui-text-faint">yr {i.sim_time_yr.toFixed(3)} {i.note ? `· ${i.note}` : ''}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function healthFill(health_pct: number): string {
  if (health_pct >= 95) return '#0e7490';   // cyan-700
  if (health_pct >= 80) return '#15803d';   // green-700
  if (health_pct >= 60) return '#a16207';   // amber-700
  if (health_pct >= 40) return '#c2410c';   // orange-700
  return '#991b1b';                         // red-800
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="text-[8px] uppercase tracking-wide text-ui-text-faint">{label}</div>
      <div className={`font-mono text-xs ${color ?? 'text-ui-text'}`}>{value}</div>
    </div>
  );
}

function RegionDamageSparkline({
  impacts,
}: { impacts: { region_id: string; sim_time_yr: number; energy_j: number }[] }) {
  if (impacts.length === 0) {
    return (
      <div className="mt-1 p-2 border border-ui-border rounded bg-ui-bg-0/60 text-[9px] text-ui-text-faint">
        No impacts recorded for this region yet.
      </div>
    );
  }
  const sorted = impacts.slice().sort((a, b) => a.sim_time_yr - b.sim_time_yr);
  const t0 = sorted[0].sim_time_yr;
  const t1 = sorted[sorted.length - 1].sim_time_yr;
  const span = Math.max(t1 - t0, 1e-6);
  // Build monotone cumulative curve in kJ.
  let running = 0;
  const pts = sorted.map((i) => {
    running += i.energy_j / 1000;
    return { t: i.sim_time_yr, cum: running };
  });
  const maxKj = pts[pts.length - 1].cum;
  const W = 560, H = 70, padL = 32, padR = 6, padT = 6, padB = 14;
  const xOf = (t: number) => padL + ((t - t0) / span) * (W - padL - padR);
  const yOf = (v: number) => H - padB - (v / Math.max(maxKj, 1e-6)) * (H - padT - padB);
  // Step path (monotone, values only increase).
  let d = `M ${padL.toFixed(1)} ${yOf(0).toFixed(1)} `;
  let prevX = padL, prevY = yOf(0);
  for (const p of pts) {
    const x = xOf(p.t);
    const y = yOf(p.cum);
    d += `L ${x.toFixed(1)} ${prevY.toFixed(1)} L ${x.toFixed(1)} ${y.toFixed(1)} `;
    prevX = x; prevY = y;
  }
  d += `L ${(W - padR).toFixed(1)} ${prevY.toFixed(1)}`;
  return (
    <div className="mt-1 border border-ui-border rounded bg-ui-bg-0/60 overflow-hidden">
      <div className="px-2 py-0.5 text-[9px] text-ui-text-faint uppercase tracking-wider flex justify-between">
        <span>Cumulative damage (kJ) · {impacts.length} impact{impacts.length > 1 ? 's' : ''}</span>
        <span className="font-mono text-ui-text-dim">{maxKj.toFixed(1)} kJ total</span>
      </div>
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <path d={d} stroke="#f87171" strokeWidth={1.5} fill="none" />
        <text x={4}     y={yOf(0) + 3}     fontSize={8} fill="#64748b">0</text>
        <text x={4}     y={yOf(maxKj) + 3} fontSize={8} fill="#64748b">{maxKj.toFixed(0)}</text>
        <text x={padL}  y={H - 2} fontSize={8} fill="#64748b">yr {t0.toFixed(2)}</text>
        <text x={W - padR} y={H - 2} fontSize={8} fill="#64748b" textAnchor="end">yr {t1.toFixed(2)}</text>
      </svg>
    </div>
  );
}
