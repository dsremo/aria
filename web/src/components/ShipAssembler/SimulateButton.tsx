/**
 * Simulate button — POSTs the current assembly to
 * /api/ship/assembly/simulate which picks scenarios deterministically
 * from the categories present and returns the events emitted by the
 * cascade. Renders a compact result card below.
 *
 * Roadmap Track 2 Phase 4 — capstone of the assembler track.
 */

import { useState } from 'react';
import { ariaApi, type AssemblyPartRecord } from '../../api/aria';
import { useAssembly } from './AssemblyStore';

interface SimulateResult {
  run_id: string;
  parts_count: number;
  scenarios_triggered: { id: string; label: string; severity: string; impact: string }[];
  events_emitted: { topic: string; severity: string; payload: Record<string, unknown> }[];
  total_critical: number;
  total_warning: number;
  note?: string;
}

export function SimulateButton() {
  const placed = useAssembly((s) => s.placed);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SimulateResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const onSimulate = async () => {
    if (placed.length === 0 || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch('/api/ship/assembly/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parts: placed as AssemblyPartRecord[] }),
      });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const body = await res.json();
          detail = body.error ?? detail;
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }
      const r: SimulateResult = await res.json();
      setResult(r);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  // Avoid the unused-import warning while keeping the public API ready
  // for callers that want a typed wrapper later.
  void ariaApi;

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={onSimulate}
        disabled={placed.length === 0 || busy}
        className="w-full text-xs px-2 py-1.5 rounded border border-cyan-400/40 bg-ui-accent/30 text-ui-accent hover:bg-ui-accent/40 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {busy ? 'Simulating…' : 'Simulate scenarios'}
      </button>
      {err && <div className="text-[10px] text-sev-crit">{err}</div>}
      {result && (
        <div className="rounded border border-ui-border-strong/40 bg-ui-bg-1/40 p-2 space-y-2">
          <div className="text-[10px] uppercase tracking-widest text-ui-accent">
            {result.run_id}
          </div>
          <div className="grid grid-cols-2 gap-1 text-[11px]">
            <div className="text-ui-text-dim">scenarios run</div>
            <div className="text-right font-mono">{result.scenarios_triggered.length}</div>
            <div className="text-ui-text-dim">critical events</div>
            <div className={`text-right font-mono ${result.total_critical > 0 ? 'text-sev-crit' : 'text-ui-text-dim'}`}>
              {result.total_critical}
            </div>
            <div className="text-ui-text-dim">warning events</div>
            <div className={`text-right font-mono ${result.total_warning > 0 ? 'text-sev-warn' : 'text-ui-text-dim'}`}>
              {result.total_warning}
            </div>
          </div>
          {result.note && (
            <div className="text-[10px] text-sev-warn">{result.note}</div>
          )}
          {result.scenarios_triggered.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-widest text-ui-text-faint mb-1">
                Scenarios
              </div>
              <ul className="space-y-0.5 text-[10px]">
                {result.scenarios_triggered.map((s) => (
                  <li key={s.id} className="flex justify-between gap-2">
                    <span
                      className={`shrink-0 px-1 rounded ${
                        s.severity === 'critical'
                          ? 'bg-sev-crit/50 text-sev-crit'
                          : 'bg-sev-warn/40 text-sev-warn'
                      }`}
                    >
                      {s.severity[0].toUpperCase()}
                    </span>
                    <span className="text-ui-text truncate">{s.label}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default SimulateButton;
