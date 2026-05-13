/**
 * Mass-budget breakdown driven by /api/bom — totals by subsystem,
 * sorted heaviest-first, with an SVG bar chart and per-subsystem percent.
 */

import { useEffect, useMemo, useState } from 'react';
import { ariaApi, type BomData, type BomItem } from '../api/aria';

const SUBSYSTEM_COLORS: Record<string, string> = {
  structure:   '#8892a8',
  propulsion:  '#ee8822',
  power:       '#f2c158',
  thermal:     '#4488ee',
  shielding:   '#4bd27a',
  habitat:     '#f2dba0',
  eclss:       '#a0e0c0',
  comms:       '#dde4ee',
  navigation:  '#d0d6e0',
  avionics:    '#b266e6',
  other:       '#667799',
};

interface SubsystemAggregation {
  subsystem: string;
  mass_kg: number;
  items: BomItem[];
  pct: number;
}

export function MassBudgetPanel() {
  const [data, setData] = useState<BomData | null>(null);

  useEffect(() => { ariaApi.bomList().then(setData).catch(console.error); }, []);

  const aggregated: SubsystemAggregation[] = useMemo(() => {
    if (!data) return [];
    const bySub: Record<string, { mass: number; items: BomItem[] }> = {};
    for (const it of data.items) {
      if (!bySub[it.subsystem]) bySub[it.subsystem] = { mass: 0, items: [] };
      bySub[it.subsystem].mass += it.total_mass_kg;
      bySub[it.subsystem].items.push(it);
    }
    const total = Object.values(bySub).reduce((s, v) => s + v.mass, 0) || 1;
    return Object.entries(bySub)
      .map(([subsystem, v]) => ({ subsystem, mass_kg: v.mass, items: v.items, pct: 100 * v.mass / total }))
      .sort((a, b) => b.mass_kg - a.mass_kg);
  }, [data]);

  if (!data) return <div className="p-4 text-sm text-ui-text-dim">Loading mass budget…</div>;

  const totalMass = data.summary.total_mass_kg;

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-2 border-b border-ui-border">
        <div className="text-[10px] uppercase tracking-wider text-ui-accent font-bold">
          Mass Budget · {(totalMass / 1e6).toFixed(1)} kt total
        </div>
        <div className="text-[10px] text-ui-text-faint mt-0.5">
          Per <code>bill_of_materials.py</code> · ShipParameters target 100 kt · {((totalMass / 1e8) * 100).toFixed(0)}% accounted
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {/* Stacked horizontal bar */}
        <div>
          <div className="text-[10px] uppercase tracking-wider text-ui-text-faint mb-1">Total mass distribution</div>
          <div className="h-6 flex bg-ui-bg-1 rounded overflow-hidden border border-ui-border">
            {aggregated.map(a => (
              <div key={a.subsystem}
                   title={`${a.subsystem}: ${(a.mass_kg / 1e6).toFixed(2)} kt (${a.pct.toFixed(1)}%)`}
                   style={{ width: `${a.pct}%`, background: SUBSYSTEM_COLORS[a.subsystem] ?? SUBSYSTEM_COLORS.other }} />
            ))}
          </div>
          <div className="flex flex-wrap gap-2 mt-1.5 text-[10px]">
            {aggregated.map(a => (
              <div key={a.subsystem} className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full" style={{ background: SUBSYSTEM_COLORS[a.subsystem] ?? SUBSYSTEM_COLORS.other }} />
                <span className="text-ui-text-dim">{a.subsystem}</span>
                <span className="text-ui-text font-mono">{a.pct.toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>

        {/* Per-subsystem detail */}
        {aggregated.map(a => (
          <div key={a.subsystem} className="bg-ui-bg-1/40 rounded border border-ui-border">
            <div className="px-2 py-1 flex items-baseline justify-between border-b border-ui-border">
              <div className="text-[11px] font-bold uppercase tracking-wider"
                   style={{ color: SUBSYSTEM_COLORS[a.subsystem] ?? '#cbd5e1' }}>
                {a.subsystem}
              </div>
              <div className="text-[10px] font-mono text-ui-text">
                {(a.mass_kg / 1e6).toFixed(2)} kt · {a.pct.toFixed(1)}%
              </div>
            </div>
            <table className="w-full text-[10px]">
              <tbody>
                {a.items.sort((x, y) => y.total_mass_kg - x.total_mass_kg).map(it => (
                  <tr key={it.item_id} className="border-b border-ui-border-soft">
                    <td className="px-2 py-0.5 text-ui-text">{it.name}</td>
                    <td className="px-2 py-0.5 text-right text-ui-text-faint font-mono">
                      {it.n_installed} × {(it.mass_kg_each / 1000).toFixed(1)} t
                    </td>
                    <td className="px-2 py-0.5 text-right text-ui-text font-mono">
                      {(it.total_mass_kg / 1000).toFixed(1)} t
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </div>
  );
}
