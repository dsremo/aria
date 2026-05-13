/**
 * ShipAssembler — drag-drop ship-assembly UX.
 *
 * Layout: 240 px palette ▏ flex-1 canvas ▏ 240 px inspector + mass budget.
 *
 * Roadmap:
 *   Phase 1 — drag a part onto the canvas (done)
 *   Phase 2 — connection constraints via category + compatible_with (here)
 *   Phase 3 — material picker + live mass budget (here)
 *   Phase 4 — 3D preview + Simulate button (future)
 */

import { useEffect, useState } from 'react';
import { ariaApi, type ShipPartDef } from '../../api/aria';
import { PartPalette } from './PartPalette';
import { Canvas2D } from './Canvas2D';
import { Canvas3D } from './Canvas3D';
import { MaterialPicker } from './MaterialPicker';
import { MassBudget } from './MassBudget';
import { SaveLoadBar } from './SaveLoadBar';
import { SimulateButton } from './SimulateButton';
import { useAssembly } from './AssemblyStore';

function checkConstraint(
  toAdd: ShipPartDef,
  placed: { partId: string }[],
  defs: Record<string, ShipPartDef>,
): { ok: true } | { ok: false; reason: string } {
  const compat = toAdd.compatible_with ?? [];
  if (compat.length === 0) {
    // Root parts (e.g. hull) — only one allowed.
    const sameCat = placed.filter((p) => defs[p.partId]?.category === toAdd.category);
    if (sameCat.length > 0) {
      return { ok: false, reason: `only one ${toAdd.category} allowed` };
    }
    return { ok: true };
  }
  // Non-root parts must have at least one placed part of a compatible category.
  const placedCategories = new Set(
    placed.map((p) => defs[p.partId]?.category).filter(Boolean) as string[],
  );
  const matchedCat = compat.find((c) => placedCategories.has(c));
  if (!matchedCat) {
    return {
      ok: false,
      reason: `requires a ${compat.join(' or ')} part on the canvas first`,
    };
  }
  return { ok: true };
}

export function ShipAssembler() {
  const [partDefs, setPartDefs] = useState<Record<string, ShipPartDef>>({});
  const [err, setErr] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [view, setView] = useState<'2d' | '3d'>('2d');

  useEffect(() => {
    ariaApi
      .shipParts()
      .then((d) => {
        const map: Record<string, ShipPartDef> = {};
        for (const p of d.parts) map[p.id] = p;
        setPartDefs(map);
      })
      .catch((e: Error) => setErr(e.message));
  }, []);

  const placed = useAssembly((s) => s.placed);
  const selectedUid = useAssembly((s) => s.selectedUid);
  const clear = useAssembly((s) => s.clear);
  const removePart = useAssembly((s) => s.removePart);

  const selected = placed.find((p) => p.uid === selectedUid);
  const selectedDef = selected ? partDefs[selected.partId] : null;

  const onAttemptAdd = (partId: string): boolean => {
    const def = partDefs[partId];
    if (!def) return false;
    const r = checkConstraint(def, placed, partDefs);
    if (!r.ok) {
      setHint(`${def.name}: ${r.reason}`);
      window.setTimeout(() => setHint(null), 3000);
      return false;
    }
    setHint(null);
    return true;
  };

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-2 border-b border-ui-border flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-ui-accent font-bold">
            Ship Assembler
          </div>
          <div className="text-[10px] text-ui-text-dim">
            {placed.length} part{placed.length === 1 ? '' : 's'} placed · drag from palette,
            double-click to remove · constraints enforced
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded border border-ui-border-strong/40 overflow-hidden text-xs">
            <button
              type="button"
              onClick={() => setView('2d')}
              className={`px-2 py-1 ${view === '2d' ? 'bg-ui-accent/40 text-ui-accent' : 'text-ui-text hover:text-ui-text'}`}
            >
              2D
            </button>
            <button
              type="button"
              onClick={() => setView('3d')}
              className={`px-2 py-1 ${view === '3d' ? 'bg-ui-accent/40 text-ui-accent' : 'text-ui-text hover:text-ui-text'}`}
            >
              3D
            </button>
          </div>
          <button
            type="button"
            onClick={clear}
            className="text-xs px-2 py-1 rounded border border-ui-border-strong/40 text-ui-text hover:border-sev-crit/40 hover:text-sev-crit"
            disabled={placed.length === 0}
          >
            Clear
          </button>
        </div>
      </div>

      {hint && (
        <div className="px-3 py-1 bg-sev-warn/40 border-b border-sev-warn/30 text-sev-warn text-xs">
          ⚠ {hint}
        </div>
      )}

      <div className="flex-1 flex min-h-0">
        <div className="w-60 border-r border-ui-border/40 shrink-0">
          <PartPalette />
        </div>
        <div className="flex-1 min-w-0 relative">
          {view === '2d' ? (
            <Canvas2D partDefs={partDefs} onAttemptAdd={onAttemptAdd} />
          ) : (
            <Canvas3D partDefs={partDefs} />
          )}
        </div>
        <div className="w-60 border-l border-ui-border/40 shrink-0 overflow-y-auto p-2 text-xs">
          <div className="text-[10px] uppercase tracking-widest text-ui-accent mb-2">Inspector</div>
          {!selected && (
            <div className="text-ui-text-faint">Select a placed part to inspect</div>
          )}
          {selected && selectedDef && (
            <div className="space-y-2">
              <div className="font-semibold text-ui-text">{selectedDef.name}</div>
              <div className="text-[10px] text-ui-text-faint font-mono">{selected.uid}</div>
              <div className="grid grid-cols-2 gap-1 text-[11px]">
                <div className="text-ui-text-dim">x</div>
                <div className="text-right">{selected.x.toFixed(0)}</div>
                <div className="text-ui-text-dim">y</div>
                <div className="text-right">{selected.y.toFixed(0)}</div>
                <div className="text-ui-text-dim">category</div>
                <div className="text-right">{selectedDef.category ?? '—'}</div>
              </div>
              <MaterialPicker uid={selected.uid} defaultMaterial={selectedDef.material} />
              <button
                type="button"
                onClick={() => removePart(selected.uid)}
                className="w-full text-xs px-2 py-1 rounded border border-sev-crit/40 text-sev-crit hover:bg-sev-crit/40"
              >
                Remove
              </button>
            </div>
          )}
          {err && <div className="text-sev-crit">{err}</div>}
          <div className="mt-3 pt-2 border-t border-ui-border/40">
            <MassBudget />
          </div>
          <div className="mt-3 pt-2 border-t border-ui-border/40">
            <SaveLoadBar />
          </div>
          <div className="mt-3 pt-2 border-t border-ui-border/40">
            <SimulateButton />
          </div>
        </div>
      </div>
    </div>
  );
}

export default ShipAssembler;
