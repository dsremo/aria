/**
 * Moon Mission Timeline — end-to-end Apollo-11 / Artemis-3 visualizer.
 *
 * Fetches /api/moon_mission and renders each phase as a row showing:
 *   - phase name, duration, Δv, propellant burned, mass after
 *   - success flag + any fault notes
 *   - a horizontal bar chart of cumulative mass and Δv
 *
 * This is the first UI view that shows all 11 mission phases wired
 * through real physics modules (TLI, LOI, powered descent, ASCENT,
 * rendezvous, TEI, EDL) with mass conservation end-to-end.
 */

import { useEffect, useRef, useState } from 'react';
import { LiveStateBadge } from './LiveStateBadge';
import { LiveSeparationBadge } from './LiveSeparationBadge';

interface Phase {
  phase: string;
  duration_s: number;
  delta_v_mps: number;
  propellant_burned_kg: number;
  mass_after_kg: number;
  success: boolean;
  notes: string;
}

interface MissionResp {
  summary: string;
  overall_success: boolean;
  total_dv_mps: number;
  total_propellant_kg: number;
  total_duration_hours: number;
  final_mass_kg: number;
  failure_phase: string | null;
  phases: Phase[];
  error?: string;
}

const PHASE_COLOR: Record<string, string> = {
  TLI: 'bg-sev-info',
  COAST_TO_MOON: 'bg-ui-bg-3',
  LOI: 'bg-sev-ok',
  UNDOCK_AND_DOI: 'bg-teal-500',
  POWERED_DESCENT: 'bg-orange-500',
  SURFACE_STAY: 'bg-sev-warn',
  POWERED_ASCENT: 'bg-sev-crit',
  RENDEZVOUS_DOCK: 'bg-purple-500',
  TEI: 'bg-pink-500',
  COAST_TO_EARTH: 'bg-slate-400',
  ENTRY_DESCENT_LANDING: 'bg-ui-accent',
};

export function MoonMissionPanel() {
  const [which, setWhich] = useState<'apollo_11' | 'artemis_3' | 'custom'>('apollo_11');
  const [faults, setFaults] = useState('');
  const [data, setData] = useState<MissionResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // R65-R4 (2026-04-24) A-7: rapid selector toggles (apollo_11 →
  // artemis_3 → apollo_11) could have the second result overwritten by
  // the first's late-arriving response.  AbortController cancels any
  // in-flight request before starting a new one.
  const abortRef = useRef<AbortController | null>(null);

  const run = async () => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setLoading(true);
    setErr(null);
    // BUG-032 (2026-04-24, walkthrough): clear the previous run's
    // banner + phase table before firing.  Without this, a fault
    // string that errors (e.g. `BOGUS:engine_out:0.5`) left the prior
    // FAILED-at-LOI report on screen below the new error pill, so a
    // naive operator couldn't tell whether the banner was from the
    // current submission or a stale one.
    setData(null);
    try {
      const params = new URLSearchParams({ mission: which });
      if (which === 'custom' && faults) params.set('faults', faults);
      const r = await fetch(`/api/moon_mission?${params}`, { signal: ac.signal });
      if (!r.ok) {
        let detail = `HTTP ${r.status}`;
        try { const body = await r.json(); if (body?.error) detail = body.error; }
        catch { /* body wasn't JSON */ }
        throw new Error(detail);
      }
      const j = await r.json();
      if (j.error) throw new Error(j.error);
      if (!ac.signal.aborted) setData(j);
    } catch (e: any) {
      if (e?.name !== 'AbortError') setErr(e.message ?? String(e));
    } finally {
      if (!ac.signal.aborted) setLoading(false);
    }
  };

  useEffect(() => {
    run();
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [which]);

  const maxDv = data ? Math.max(...data.phases.map((p) => p.delta_v_mps || 1), 100) : 100;
  const maxProp = data ? Math.max(...data.phases.map((p) => p.propellant_burned_kg || 1), 100) : 100;

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Moon Mission End-to-End</h2>
        <p className="text-xs text-ui-text-dim">
          Full physics chain: TLI → coast → LOI → DOI → descent → surface → ASCENT → rendezvous → TEI → coast → EDL
        </p>
      </div>

      <div className="mb-3 grid grid-cols-1 md:grid-cols-2 gap-2">
        <LiveStateBadge norad="25544" group="stations" refreshSec={60} />
        <LiveSeparationBadge
          noradA="25544"
          noradB="48274"
          group="stations"
          refreshSec={60}
          label="Live separation (ISS ↔ Tiangong)"
        />
      </div>

      <div className="flex flex-wrap gap-2 items-end mb-3 text-xs">
        <label className="flex flex-col">
          <span className="text-ui-text-dim">Mission</span>
          <select value={which} onChange={(e) => setWhich(e.target.value as any)}
                   className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text">
            <option value="apollo_11">Apollo 11 (historical)</option>
            <option value="artemis_3">Artemis 3 / HLS (projected)</option>
            <option value="custom">Custom with faults</option>
          </select>
        </label>
        {which === 'custom' && (
          <label className="flex flex-col flex-1">
            <span className="text-ui-text-dim">Faults (PHASE:kind:severity,…)</span>
            <input value={faults} onChange={(e) => setFaults(e.target.value)}
                   placeholder="TLI:engine_out:0.3,LOI:nav_error:0.5"
                   className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text" />
          </label>
        )}
        <button onClick={run} disabled={loading}
                className="inline-flex items-center gap-2 px-4 py-1.5 bg-ui-accent/40 hover:bg-ui-accent-strong text-white rounded disabled:opacity-50 disabled:cursor-wait transition-colors">
          {loading && (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" className="animate-spin" aria-hidden>
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
              <path d="M22 12a10 10 0 0 1-10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            </svg>
          )}
          {loading ? 'Running…' : 'Run mission'}
        </button>
      </div>

      {err && (
        <div className="bg-sev-crit/40 border border-sev-crit rounded p-2 text-sev-crit text-xs mb-2">
          Error: {err}
        </div>
      )}

      {data && (
        <>
          <div className={`mb-3 p-3 rounded border ${
            data.overall_success
              ? 'bg-sev-ok/30 border-sev-ok text-sev-ok'
              : 'bg-sev-crit/30 border-sev-crit text-sev-crit'
          }`}>
            <div className="font-semibold">{data.summary}</div>
            <div className="text-xs mt-1 text-ui-text">
              Total Δv: <span className="font-mono">{data.total_dv_mps.toFixed(0)} m/s</span> ·
              Propellant: <span className="font-mono">{data.total_propellant_kg.toFixed(0)} kg</span> ·
              Duration: <span className="font-mono">{data.total_duration_hours.toFixed(1)} h</span> ·
              Final CM: <span className="font-mono">{data.final_mass_kg.toFixed(0)} kg</span>
            </div>
          </div>

          <div className="bg-ui-bg-1/60 border border-ui-border rounded overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-ui-bg-2 text-ui-text-dim">
                <tr>
                  <th className="text-left p-2">Phase</th>
                  <th className="text-right p-2">Duration</th>
                  <th className="text-right p-2">Δv (m/s)</th>
                  <th className="text-left p-2 w-32">Δv bar</th>
                  <th className="text-right p-2">Prop (kg)</th>
                  <th className="text-left p-2 w-32">Prop bar</th>
                  <th className="text-right p-2">Mass after</th>
                  <th className="text-left p-2">Notes</th>
                </tr>
              </thead>
              <tbody>
                {data.phases.map((p, i) => {
                  const dur = p.duration_s > 3600
                    ? `${(p.duration_s / 3600).toFixed(1)}h`
                    : `${p.duration_s.toFixed(0)}s`;
                  const dvPct = Math.min(100, (p.delta_v_mps / maxDv) * 100);
                  const propPct = Math.min(100, (p.propellant_burned_kg / maxProp) * 100);
                  const color = PHASE_COLOR[p.phase] || 'bg-ui-bg-3';
                  return (
                    <tr key={i} className="border-t border-ui-border">
                      <td className={`p-2 ${p.success ? 'text-ui-text' : 'text-sev-crit'}`}>
                        <span className={`inline-block w-2 h-2 mr-1 ${color}`} /> {p.phase}
                      </td>
                      <td className="p-2 font-mono text-right text-ui-text">{dur}</td>
                      <td className="p-2 font-mono text-right text-ui-text">{p.delta_v_mps.toFixed(0)}</td>
                      <td className="p-2"><div className={`h-3 ${color}`} style={{ width: `${dvPct}%` }} /></td>
                      <td className="p-2 font-mono text-right text-ui-text">{p.propellant_burned_kg.toFixed(0)}</td>
                      <td className="p-2"><div className={`h-3 ${color}/70`} style={{ width: `${propPct}%` }} /></td>
                      <td className="p-2 font-mono text-right text-ui-text">{p.mass_after_kg.toFixed(0)}</td>
                      <td className="p-2 text-ui-text-dim text-[10px]">{p.notes}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="mt-3 text-[11px] text-ui-text-dim space-y-1">
            <p>• Apollo 11 historical: TLI 3,131 m/s · descent 2,040 m/s · TEI 897.9 m/s · EDL peak g 6.9 (ARIA matches within 2-10%).</p>
            <p>• Custom mode accepts fault tokens: <code className="bg-ui-bg-2 px-1 rounded">PHASE:kind:severity,...</code> — kinds: engine_out, propellant_leak, nav_error, comms_loss, cabin_leak, medical.</p>
          </div>
        </>
      )}
    </div>
  );
}
