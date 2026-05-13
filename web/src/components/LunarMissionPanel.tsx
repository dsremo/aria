import { useEffect, useRef, useState } from 'react';

// Earth→Moon feasibility panel.
//
// Wraps the `/api/lunar/feasibility` endpoint so operators can tweak the
// lunar-sortie vehicle and see real FEA + Δv + radiation numbers immediately.
// This is the "modify part → remesh → resolve" loop for the Moon scenario.

type LunarReport = {
  feasible: boolean;
  structural: {
    pressure_vm_mpa: number;
    pressure_analytical_mpa: number;
    launch_axial_mpa: number;
    safety_factor: number;
    cabin_mass_kg: number;
  };
  delta_v: { achievable_m_s: number; required_m_s: number; margin_pct: number };
  radiation: { dose_sv: number; limit_sv: number };
  goes: string[];
  nogos: string[];
  warnings: string[];
  params: {
    cabin_radius_m: number; cabin_length_m: number; cabin_wall_mm: number;
    crew_size: number; mission_days: number; isp_s: number;
    dry_mass_kg: number; propellant_mass_kg: number;
    shield_kg_m2: number; mass_ratio: number;
  };
};

// Initial "Orion / Apollo" reference design.
const DEFAULT = {
  cabin_radius_m: 1.8,
  cabin_length_m: 3.3,
  cabin_wall_thickness_m: 0.012,
  crew_size: 4,
  mission_duration_days: 3.0,
  propulsion_isp_s: 900.0,
  dry_mass_kg: 15000,
  propellant_mass_kg: 30000,
  shield_areal_density_kg_m2: 100,
};

export function LunarMissionPanel() {
  const [inp, setInp] = useState({ ...DEFAULT });
  const [rep, setRep] = useState<LunarReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // BUG-033 (2026-04-24, walkthrough): track the slider state that
  // actually produced `rep` so we can tell when the user has moved
  // sliders without clicking Re-analyze.  `repInp === null` while a
  // run is pending or no run has happened.
  const [repInp, setRepInp] = useState<typeof DEFAULT | null>(null);
  const abortRef   = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  // True when any slider differs from the input that produced the
  // currently-displayed result.  JSON string compare is fine here — the
  // shape is fixed and float values serialise deterministically.
  const stale = !!rep && !!repInp && JSON.stringify(inp) !== JSON.stringify(repInp);

  // BUG-005 fix: React 18 StrictMode deliberately runs effects mount →
  // unmount → mount in development.  The first unmount fires the cleanup
  // and flips mountedRef.current to false; because useRef's initial value
  // only applies on first render, the second mount kept mountedRef at
  // false and every `if (mountedRef.current) setRep(data)` was silently
  // dropped — the Result panel stayed on "Click Re-analyze to evaluate".
  // Set mountedRef.current = true at mount, false at unmount.
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  const run = async () => {
    // Cancel any previous Re-analyze request so the user's latest
    // slider state is what produces the displayed result.
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    if (mountedRef.current) { setLoading(true); setErr(null); }
    try {
      const r = await fetch('/api/lunar/feasibility', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(inp),
        signal: ac.signal,
      });
      if (!r.ok) {
        // Preserve the server-side error body (e.g. "cabin_radius_m=-5
        // below min 0.5") instead of displaying a useless "HTTP 400".
        let detail = `HTTP ${r.status}`;
        try {
          const body = await r.json();
          if (body?.error) detail = body.error;
        } catch { /* body wasn't JSON */ }
        throw new Error(detail);
      }
      const data = await r.json();
      if (mountedRef.current && !ac.signal.aborted) {
        setRep(data);
        // Capture the input snapshot that produced this result so we
        // can render a "stale — click Re-analyze" overlay when the
        // user subsequently drags a slider without recomputing.
        setRepInp({ ...inp });
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError' && mountedRef.current) setErr(String(e.message ?? e));
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  };

  const reset = () => { setInp({ ...DEFAULT }); setRep(null); setRepInp(null); };

  const Slider = (
    label: string, key: keyof typeof inp,
    min: number, max: number, step: number, unit = ''
  ) => (
    <label className="flex items-center gap-2 text-xs py-1">
      <span className="w-44 text-ui-text">{label}</span>
      <input type="range" min={min} max={max} step={step}
             value={inp[key] as number}
             onChange={e => setInp(s => ({ ...s, [key]: parseFloat(e.target.value) }))}
             className="flex-1"/>
      <span className="w-24 text-right text-ui-accent tabular-nums">
        {(inp[key] as number).toLocaleString(undefined, { maximumFractionDigits: 3 })} {unit}
      </span>
    </label>
  );

  return (
    <div className="p-4 text-sm">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Earth → Moon — Digital Twin Feasibility</h2>
        <p className="text-xs text-ui-text-dim mt-1 max-w-3xl">
          Apollo-class sortie through the real twin: CadQuery geometry → Gmsh tetrahedral mesh
          → FEA (internal pressure + 4 g launch load) → Tsiolkovsky Δv budget → Van Allen + GCR
          dose model. Tweak any slider, click <b>Re-analyze</b>, get physical numbers.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <section className="bg-ui-bg-1/70 border border-ui-border rounded p-3">
          <h3 className="text-xs uppercase text-ui-text-dim mb-2">Vehicle design</h3>
          {/* BUG-023 (2026-04-24): lowered wall/shield mins to match
              the physics engine's actual range. Walkthrough scenarios
              (2 mm wall, 10 kg/m² shield) are now reachable via the UI,
              not only by direct API call. */}
          {Slider('Cabin radius',          'cabin_radius_m',          1.0, 4.0,  0.05, 'm')}
          {Slider('Cabin length',          'cabin_length_m',          2.0, 10.0, 0.1,  'm')}
          {Slider('Wall thickness',        'cabin_wall_thickness_m',  0.002, 0.050, 0.001, 'm')}
          {Slider('Crew size',             'crew_size',               2, 8,       1,      '')}
          {Slider('Mission duration',      'mission_duration_days',   2, 30,      1,      'd')}
          {Slider('Propulsion Isp',        'propulsion_isp_s',        300, 10000, 50,    's')}
          {Slider('Dry mass',              'dry_mass_kg',             5000, 50000, 500,   'kg')}
          {Slider('Propellant mass',       'propellant_mass_kg',      5000, 120000, 1000, 'kg')}
          {Slider('Shield areal density',  'shield_areal_density_kg_m2', 5, 500,  5,      'kg/m²')}

          <div className="mt-3 flex gap-2">
            <button onClick={run} disabled={loading}
                    className="px-3 py-1.5 bg-ui-accent-strong hover:bg-ui-accent disabled:opacity-60 rounded text-xs">
              {loading ? '…analyzing' : '▶ Re-analyze'}
            </button>
            <button onClick={reset}
                    className="px-3 py-1.5 bg-ui-bg-3 hover:bg-ui-bg-3 rounded text-xs">
              Reset to Apollo-class
            </button>
          </div>
          {err && <div className="text-sev-crit text-xs mt-2">{err}</div>}
        </section>

        <section className="bg-ui-bg-1/70 border border-ui-border rounded p-3 relative">
          <h3 className="text-xs uppercase text-ui-text-dim mb-2">Result</h3>
          {/* BUG-033 (2026-04-24, walkthrough): when sliders drift away
              from the input that produced `rep`, the displayed numbers
              are lying.  Show a conspicuous amber chip + dim the
              content so the operator can't miss it. */}
          {stale && (
            <div className="absolute top-2 right-2 text-[10px] px-2 py-0.5 rounded border border-sev-warn bg-sev-warn/60 text-sev-warn animate-pulse">
              ⚠ stale — sliders changed, click Re-analyze
            </div>
          )}
          {!rep && <div className="text-ui-text-faint text-xs">Click Re-analyze to evaluate.</div>}
          {rep && (
            <div className={`space-y-2 text-xs ${stale ? 'opacity-50' : ''}`}>
              <div className={`text-lg font-semibold ${rep.feasible ? 'text-sev-ok' : 'text-sev-crit'}`}>
                {rep.feasible ? '✓ FEASIBLE' : '✗ NOT FEASIBLE'}
              </div>

              <div className="border border-ui-border rounded p-2">
                <div className="text-ui-text-dim mb-1">Structural (FEA)</div>
                <div>Pressure VM stress: <b className="text-ui-accent">{rep.structural.pressure_vm_mpa.toFixed(2)} MPa</b> (analytical pR/t {rep.structural.pressure_analytical_mpa.toFixed(2)})</div>
                <div title="Analytical axial stress from dry-mass payload at 4g launch. Informational — the safety factor above already includes this load in the FEA.">Launch axial (ref): {rep.structural.launch_axial_mpa.toFixed(2)} MPa</div>
                <div>Safety factor: <b className={rep.structural.safety_factor >= 2 ? 'text-sev-ok' : 'text-sev-crit'}>{rep.structural.safety_factor.toFixed(1)}×</b></div>
                <div>Cabin shell mass: {rep.structural.cabin_mass_kg.toFixed(0)} kg</div>
              </div>

              <div className="border border-ui-border rounded p-2">
                <div className="text-ui-text-dim mb-1">Propulsion (Tsiolkovsky)</div>
                <div>Achievable Δv: <b className="text-ui-accent">{rep.delta_v.achievable_m_s.toFixed(0)} m/s</b></div>
                <div>Required Δv: {rep.delta_v.required_m_s.toFixed(0)} m/s</div>
                <div>Margin: <b className={rep.delta_v.margin_pct >= 0 ? 'text-sev-ok' : 'text-sev-crit'}>{rep.delta_v.margin_pct > 0 ? '+' : ''}{rep.delta_v.margin_pct.toFixed(0)}%</b></div>
              </div>

              <div className="border border-ui-border rounded p-2">
                <div className="text-ui-text-dim mb-1">Radiation (Van Allen + GCR)</div>
                <div>Predicted dose: <b className={rep.radiation.dose_sv <= rep.radiation.limit_sv ? 'text-sev-ok' : 'text-sev-crit'}>{(rep.radiation.dose_sv*1000).toFixed(1)} mSv</b></div>
                <div>30-day limit: {(rep.radiation.limit_sv*1000).toFixed(0)} mSv (NASA-STD-3001)</div>
              </div>

              {rep.nogos.length > 0 && (
                <div className="border border-sev-crit bg-sev-crit/30 rounded p-2">
                  <div className="text-sev-crit mb-1">NO-GOs</div>
                  {rep.nogos.map((x, i) => <div key={i}>• {x}</div>)}
                </div>
              )}
              {rep.warnings.length > 0 && (
                <div className="border border-sev-warn bg-sev-warn/20 rounded p-2">
                  <div className="text-sev-warn mb-1">Warnings</div>
                  {rep.warnings.map((x, i) => <div key={i}>• {x}</div>)}
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
