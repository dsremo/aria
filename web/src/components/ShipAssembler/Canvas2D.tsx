/**
 * Drop zone for ship parts. Renders placed parts as labelled circles
 * (one circle per ShipPartDef instance) at their stored pixel coords.
 * Reuses the part-def colour palette so the canvas reads the same as
 * the existing ship-builder.
 *
 * Native HTML5 drag/drop — no extra deps. The data payload is a
 * `text/aria-part-id` matching what PartPalette sets.
 */

import { useRef } from 'react';
import { useAssembly } from './AssemblyStore';
import type { ShipPartDef } from '../../api/aria';

interface Props {
  partDefs: Record<string, ShipPartDef>;
  /** Pre-add gate; return false to reject (e.g. constraint violation). */
  onAttemptAdd?: (partId: string) => boolean;
}

export function Canvas2D({ partDefs, onAttemptAdd }: Props) {
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const placed = useAssembly((s) => s.placed);
  const selectedUid = useAssembly((s) => s.selectedUid);
  const addPart = useAssembly((s) => s.addPart);
  const movePart = useAssembly((s) => s.movePart);
  const selectPart = useAssembly((s) => s.selectPart);
  const removePart = useAssembly((s) => s.removePart);

  const onDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  };

  const localCoords = (e: React.DragEvent<HTMLDivElement> | React.MouseEvent<HTMLDivElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const partId = e.dataTransfer.getData('text/aria-part-id');
    if (!partId) return;
    if (!partDefs[partId]) return;
    const { x, y } = localCoords(e);
    // The drop event might be from the palette (new) or from the canvas
    // (move). Distinguish by uid presence in dataTransfer.
    const movingUid = e.dataTransfer.getData('text/aria-uid');
    if (movingUid) {
      movePart(movingUid, x, y);
    } else {
      if (onAttemptAdd && !onAttemptAdd(partId)) return;
      addPart(partId, x, y);
    }
  };

  return (
    <div
      ref={canvasRef}
      data-testid="canvas"
      onDragOver={onDragOver}
      onDrop={onDrop}
      onClick={(e) => {
        // Click empty canvas → deselect
        if (e.target === canvasRef.current) selectPart(null);
      }}
      className="relative h-full w-full bg-ui-bg-0 overflow-hidden border border-ui-border/40"
      style={{
        backgroundImage:
          'linear-gradient(rgba(148,163,184,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.06) 1px, transparent 1px)',
        backgroundSize: '40px 40px',
      }}
    >
      {/* Grid centre cross */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/2 left-0 right-0 border-t border-ui-border/40" />
        <div className="absolute top-0 bottom-0 left-1/2 border-l border-ui-border/40" />
      </div>

      {placed.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-ui-text-faint pointer-events-none">
          drag a part from the palette →
        </div>
      )}

      {placed.map((p) => {
        const def = partDefs[p.partId];
        const color = def?.color || '#475569';
        const label = def?.name || p.partId;
        const isSelected = p.uid === selectedUid;
        return (
          <div
            key={p.uid}
            data-testid={`placed-${p.uid}`}
            draggable
            onDragStart={(e) => {
              e.dataTransfer.effectAllowed = 'move';
              e.dataTransfer.setData('text/aria-part-id', p.partId);
              e.dataTransfer.setData('text/aria-uid', p.uid);
            }}
            onClick={(e) => {
              e.stopPropagation();
              selectPart(p.uid);
            }}
            onDoubleClick={(e) => {
              e.stopPropagation();
              removePart(p.uid);
            }}
            className={`absolute -translate-x-1/2 -translate-y-1/2 select-none cursor-grab active:cursor-grabbing rounded-full border-2 flex items-center justify-center text-[10px] font-semibold ${
              isSelected ? 'border-cyan-300 ring-2 ring-cyan-300/40' : 'border-ui-border'
            }`}
            style={{
              left: p.x,
              top: p.y,
              width: 50,
              height: 50,
              background: color,
              color: '#0f172a',
            }}
            title={`${label} — double-click to remove`}
          >
            {label.slice(0, 8)}
          </div>
        );
      })}
    </div>
  );
}

export default Canvas2D;
