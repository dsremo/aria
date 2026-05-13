/**
 * Bill-of-Materials tab — every redundant subsystem in the ship with
 * installed/required counts, mass, MTBF, and SPOF flag. Lets the user
 * see at a glance "what redundancy do we have / where are the SPOFs?"
 */

import { useEffect, useMemo, useState } from 'react';
import { ariaApi, type BomData, type BomItem } from '../api/aria';

interface Props {
  onSelectPart: (id: string) => void;
}

export function BomTab({ onSelectPart }: Props) {
  const [data, setData]     = useState<BomData | null>(null);
  const [filter, setFilter] = useState('');
  const [showOnlySpof, setShowOnlySpof] = useState(false);
  const [sortBy, setSortBy] = useState<'subsystem' | 'mass' | 'redundancy'>('subsystem');

  useEffect(() => { ariaApi.bomList().then(setData).catch(console.error); }, []);

  const items = useMemo(() => {
    if (!data) return [];
    let xs = data.items.slice();
    if (filter) {
      const q = filter.toLowerCase();
      xs = xs.filter(it => it.item_id.includes(q) || it.name.toLowerCase().includes(q) || it.subsystem.includes(q));
    }
    if (showOnlySpof) xs = xs.filter(it => it.is_spof);
    if (sortBy === 'mass')        xs.sort((a, b) => b.total_mass_kg - a.total_mass_kg);
    if (sortBy === 'redundancy')  xs.sort((a, b) => a.redundancy_level - b.redundancy_level);
    if (sortBy === 'subsystem')   xs.sort((a, b) => a.subsystem.localeCompare(b.subsystem) || a.name.localeCompare(b.name));
    return xs;
  }, [data, filter, showOnlySpof, sortBy]);

  if (!data) return <div className="p-4 text-sm text-ui-text-dim">Loading BOM…</div>;

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-2 border-b border-ui-border flex items-center gap-2 text-xs">
        <div className="text-[10px] uppercase tracking-wider text-ui-accent font-bold">
          BOM · {data.summary.total_items} items · {(data.summary.total_mass_kg / 1e6).toFixed(1)} kt total · {data.summary.spof_count} SPOFs
        </div>
        <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="filter…"
               className="ml-auto px-2 py-0.5 bg-ui-bg-2 border border-ui-border rounded text-xs" />
        <label className="flex items-center gap-1 text-[10px] cursor-pointer">
          <input type="checkbox" checked={showOnlySpof} onChange={e => setShowOnlySpof(e.target.checked)}
                 className="accent-red-500" />
          SPOF only
        </label>
        <select value={sortBy} onChange={e => setSortBy(e.target.value as any)}
                className="px-1 py-0.5 bg-ui-bg-2 border border-ui-border rounded text-xs">
          <option value="subsystem">by subsystem</option>
          <option value="mass">by mass</option>
          <option value="redundancy">by redundancy</option>
        </select>
      </div>

      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-[11px]">
          <thead className="text-ui-text-faint text-[9px] uppercase tracking-wider sticky top-0 bg-ui-bg-1 border-b border-ui-border">
            <tr>
              <th className="text-left px-3 py-1.5">Subsystem</th>
              <th className="text-left px-2 py-1.5">Item</th>
              <th className="text-right px-2 py-1.5">N inst</th>
              <th className="text-right px-2 py-1.5">N req</th>
              <th className="text-right px-2 py-1.5">Redund</th>
              <th className="text-right px-2 py-1.5">Mass (t)</th>
              <th className="text-right px-2 py-1.5">MTBF (yr)</th>
              <th className="text-left px-2 py-1.5">Failure mode</th>
            </tr>
          </thead>
          <tbody>
            {items.map(it => <Row key={it.item_id} item={it} onSelectPart={onSelectPart} />)}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Row({ item, onSelectPart }: { item: BomItem; onSelectPart: (id: string) => void }) {
  const redundColor = item.redundancy_level === 0 ? 'text-sev-crit'
                    : item.redundancy_level === 1 ? 'text-sev-warn'
                    : 'text-sev-ok';
  return (
    <tr className={`border-b border-ui-border-soft ${item.is_spof ? 'bg-sev-crit/30' : 'hover:bg-ui-bg-2/40'}`}>
      <td className="px-3 py-1 text-ui-text-dim uppercase text-[9px]">{item.subsystem}</td>
      <td className="px-2 py-1">
        <div className="text-ui-text">{item.name}</div>
        {item.related_part_ids.length > 0 && (
          <div className="text-[9px] flex flex-wrap gap-0.5 mt-0.5">
            {item.related_part_ids.slice(0, 3).map(p => (
              <button key={p}
                      onClick={() => onSelectPart(p)}
                      className="px-1 py-0 rounded bg-ui-bg-2 hover:bg-ui-bg-3 text-ui-text-dim text-[9px]">
                {p}
              </button>
            ))}
            {item.related_part_ids.length > 3 && <span className="text-ui-text-faint">+{item.related_part_ids.length - 3}</span>}
          </div>
        )}
      </td>
      <td className="px-2 py-1 text-right font-mono">{item.n_installed}</td>
      <td className="px-2 py-1 text-right font-mono text-ui-text-dim">{item.n_required}</td>
      <td className={`px-2 py-1 text-right font-mono font-semibold ${redundColor}`}>
        {item.is_spof ? 'SPOF' : `+${item.redundancy_level}`}
      </td>
      <td className="px-2 py-1 text-right font-mono text-ui-text-dim">{(item.total_mass_kg / 1000).toFixed(1)}</td>
      <td className="px-2 py-1 text-right font-mono text-ui-text-faint">
        {item.mtbf_hours ? (item.mtbf_hours / 8760).toFixed(0) : '—'}
      </td>
      <td className="px-2 py-1 text-[10px] text-ui-text-dim italic max-w-md truncate" title={item.failure_mode}>
        {item.failure_mode}
      </td>
    </tr>
  );
}
