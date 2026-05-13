/**
 * Live mass budget — recomputes whenever the placed-parts list changes.
 *
 * Posts the current assembly to /api/ship/assembly/compute_mass and
 * shows total + per-part breakdown. Material overrides flow through
 * to the backend so density-substituted masses are reflected here.
 *
 * Roadmap Track 2 Phase 3.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type AssemblyMassResponse } from '../../api/aria';
import { useAssembly } from './AssemblyStore';

export function MassBudget() {
  const placed = useAssembly((s) => s.placed);
  const [resp, setResp] = useState<AssemblyMassResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (placed.length === 0) {
      setResp(null);
      setErr(null);
      return;
    }
    let cancelled = false;
    const items = placed.map((p) => ({ part_id: p.partId, material: p.material }));
    ariaApi
      .assemblyComputeMass(items)
      .then((r) => {
        if (!cancelled) {
          setResp(r);
          setErr(null);
        }
      })
      .catch((e: Error) => !cancelled && setErr(e.message));
    return () => {
      cancelled = true;
    };
  }, [placed]);

  if (placed.length === 0) {
    return (
      <div className="text-[10px] text-ui-text-faint">no parts — drag from palette</div>
    );
  }
  if (err) return <div className="text-[10px] text-sev-crit">mass: {err}</div>;
  if (!resp) return <div className="text-[10px] text-ui-text-dim">computing mass…</div>;

  const tonnes = resp.total_mass_kg / 1000;
  const formattedTotal =
    tonnes >= 1000
      ? `${(tonnes / 1000).toFixed(1)} kt`
      : `${tonnes.toFixed(1)} t`;

  return (
    <div className="text-xs text-ui-text">
      <div className="flex items-baseline justify-between">
        <div className="text-[10px] uppercase tracking-widest text-ui-accent">
          Mass budget
        </div>
        <div className="font-mono text-ui-accent">{formattedTotal}</div>
      </div>
      <ul className="mt-1 space-y-0.5 max-h-32 overflow-y-auto">
        {resp.parts.map((p, i) => (
          <li
            key={`${p.part_id}-${i}`}
            className="flex justify-between text-[10px] text-ui-text-dim"
          >
            <span>{p.part_id}{p.material ? ` (${p.material})` : ''}</span>
            <span className="font-mono">
              {p.mass_kg >= 1000
                ? `${(p.mass_kg / 1000).toFixed(1)} t`
                : `${p.mass_kg.toFixed(0)} kg`}
            </span>
          </li>
        ))}
      </ul>
      {resp.warnings.length > 0 && (
        <div className="mt-1 text-[10px] text-sev-warn">
          {resp.warnings.length} warning{resp.warnings.length === 1 ? '' : 's'}
          <ul className="mt-0.5 list-disc list-inside">
            {resp.warnings.slice(0, 3).map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default MassBudget;
