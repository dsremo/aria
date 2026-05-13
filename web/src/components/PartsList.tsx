/**
 * Left sidebar: scrollable list of every ship part, grouped by subsystem.
 * Clicking a row selects it in the inspection panel.
 */

import { useEffect, useMemo, useState } from 'react';
import { ariaApi, type PartSnapshot } from '../api/aria';

interface Props {
  selectedPartId: string | null;
  hoveredPartId: string | null;
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
}

export function PartsList({ selectedPartId, hoveredPartId, onSelect, onHover }: Props) {
  const [parts, setParts] = useState<PartSnapshot[]>([]);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    const refresh = () => ariaApi.listParts().then(d => setParts(d.parts)).catch(() => {});
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);

  const grouped = useMemo(() => {
    const groups: Record<string, PartSnapshot[]> = {};
    for (const p of parts) {
      if (filter && !p.part_id.toLowerCase().includes(filter.toLowerCase())
                 && !p.name.toLowerCase().includes(filter.toLowerCase())) continue;
      (groups[p.subsystem] = groups[p.subsystem] ?? []).push(p);
    }
    return groups;
  }, [parts, filter]);

  return (
    <div className="h-full flex flex-col text-xs">
      <div className="px-3 py-2 border-b border-ui-border">
        <input type="text" placeholder="Filter parts…"
               value={filter}
               onChange={e => setFilter(e.target.value)}
               className="w-full px-2 py-1 text-xs rounded bg-ui-bg-2 border border-ui-border text-ui-text placeholder:text-ui-text-faint focus:border-ui-accent outline-none" />
      </div>
      <div className="flex-1 overflow-y-auto pb-4">
        {Object.entries(grouped).sort().map(([subsystem, group]) => (
          <div key={subsystem} className="mb-1">
            <div className="px-3 py-1 text-[9px] uppercase tracking-wider text-ui-text-faint font-bold">
              {subsystem} · {group.length}
            </div>
            {group.map(p => (
              <div
                key={p.part_id}
                onClick={() => onSelect(p.part_id)}
                onMouseEnter={() => onHover(p.part_id)}
                onMouseLeave={() => onHover(null)}
                className={`px-3 py-1 cursor-pointer flex items-center gap-2 border-l-2 transition-colors
                  ${selectedPartId === p.part_id
                    ? 'border-ui-accent bg-ui-accent/20'
                    : hoveredPartId === p.part_id
                    ? 'border-transparent bg-ui-bg-2/60'
                    : 'border-transparent hover:bg-ui-bg-2/30'}`}>
                <div className={`w-1.5 h-1.5 rounded-full ${p.operational ? 'bg-sev-ok' : 'bg-sev-crit'}`} />
                <span className="flex-1 truncate">{p.name}</span>
                <span className="text-[9px] text-ui-text-faint font-mono">
                  {p.health_pct < 100 ? `${p.health_pct.toFixed(0)}%` : ''}
                </span>
              </div>
            ))}
          </div>
        ))}
        {parts.length === 0 && (
          <div className="p-3 text-ui-text-faint">Loading parts… (backend on :8090)</div>
        )}
        {parts.length > 0 && Object.keys(grouped).length === 0 && (
          <div className="p-3 text-ui-text-faint italic">No parts match "{filter}".</div>
        )}
      </div>
    </div>
  );
}
