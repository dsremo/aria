/**
 * Material picker for the currently selected placed part.
 *
 * Pulls /api/materials once and lets the operator override the part's
 * default material. The change flows through the assembly store so
 * MassBudget recomputes automatically.
 *
 * Roadmap Track 2 Phase 3.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type MaterialEntry } from '../../api/aria';
import { useAssembly } from './AssemblyStore';

interface Props {
  uid: string;
  defaultMaterial: string;
}

export function MaterialPicker({ uid, defaultMaterial }: Props) {
  const [materials, setMaterials] = useState<Record<string, MaterialEntry> | null>(null);
  const placed = useAssembly((s) => s.placed.find((p) => p.uid === uid));
  const setMaterial = useAssembly((s) => s.setMaterial);
  const current = placed?.material ?? null;

  useEffect(() => {
    let cancelled = false;
    ariaApi
      .materials()
      .then((d) => !cancelled && setMaterials(d.materials))
      .catch(() => !cancelled && setMaterials({}));
    return () => {
      cancelled = true;
    };
  }, []);

  if (!materials) {
    return <div className="text-[10px] text-ui-text-faint">loading materials…</div>;
  }

  const names = Object.keys(materials).sort();

  return (
    <div className="space-y-1">
      <label className="text-[10px] uppercase tracking-widest text-ui-text-faint">
        Material override
      </label>
      <select
        value={current ?? ''}
        onChange={(e) => setMaterial(uid, e.target.value || null)}
        className="w-full bg-ui-bg-0 border border-ui-border rounded text-xs text-ui-text px-1 py-1"
      >
        <option value="">— default ({defaultMaterial}) —</option>
        {names.map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </select>
      {current && materials[current] && (
        <div className="text-[10px] text-ui-text-dim grid grid-cols-2 gap-1">
          <div>density</div>
          <div className="text-right font-mono">
            {materials[current].density_kg_m3?.toFixed(0)} kg/m³
          </div>
          {materials[current].yield_strength_mpa !== null && (
            <>
              <div>yield</div>
              <div className="text-right font-mono">
                {materials[current].yield_strength_mpa} MPa
              </div>
            </>
          )}
          <div className="col-span-2 text-[9px] italic text-ui-text-faint">
            {materials[current].source}
          </div>
        </div>
      )}
    </div>
  );
}

export default MaterialPicker;
