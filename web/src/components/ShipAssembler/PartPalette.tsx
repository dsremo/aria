/**
 * Drag source for ship parts. Each item is a tiny card the user can
 * drag onto the assembly canvas. Uses native HTML5 drag-and-drop —
 * no extra deps. Sets a `text/aria-part-id` payload so the canvas
 * can tell what was dropped.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type ShipPartDef } from '../../api/aria';

interface Props {
  onSelect?: (part: ShipPartDef) => void;
}

export function PartPalette({ onSelect }: Props) {
  const [parts, setParts] = useState<ShipPartDef[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    ariaApi
      .shipParts()
      .then((d) => setParts(d.parts))
      .catch((e: Error) => setErr(e.message));
  }, []);

  if (err) return <div className="text-xs text-sev-crit p-2">parts unavailable: {err}</div>;
  if (!parts) return <div className="text-xs text-ui-text-dim p-2">loading parts…</div>;

  return (
    <div className="h-full overflow-y-auto p-2">
      <div className="text-[10px] uppercase tracking-widest text-ui-accent mb-2">
        Parts ({parts.length}) · drag onto canvas
      </div>
      <ul className="space-y-1">
        {parts.map((p) => (
          <li
            key={p.id}
            data-testid={`palette-${p.id}`}
            draggable
            onDragStart={(e) => {
              e.dataTransfer.effectAllowed = 'copy';
              e.dataTransfer.setData('text/aria-part-id', p.id);
            }}
            onClick={() => onSelect?.(p)}
            className="cursor-grab active:cursor-grabbing rounded border border-ui-border-strong/40 bg-ui-bg-1/40 p-2 text-xs text-ui-text hover:border-ui-accent/40 hover:bg-ui-accent/20 transition-colors"
          >
            <div className="flex items-center gap-2">
              <div
                className="w-3 h-3 rounded shrink-0"
                style={{ background: p.color || '#475569' }}
              />
              <div className="flex-1 min-w-0">
                <div className="font-semibold">{p.name}</div>
                <div className="text-[10px] text-ui-text-faint">{p.material}</div>
              </div>
            </div>
            {p.description && (
              <div className="mt-1 text-[10px] text-ui-text-dim line-clamp-2">{p.description}</div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default PartPalette;
