/**
 * Mission Studio — unified front-end for the production-grade mission
 * simulators added in R37.  Single tab covers four flows:
 *
 *   1. Porkchop / Lambert  — pick origin & destination planet, set
 *      vehicle dry-mass + fuel + Isp + max revs, get the optimal launch
 *      window with C3, v∞ at arrival, ToF, fuel required, feasibility.
 *      Multi-rev support consumes the Phase-A `max_revs` knob so outer-
 *      planet missions can pick a Type-III/IV trajectory.
 *
 *   2. Aerocapture  — pick planetary body (Mars / Venus / Titan / Earth),
 *      arrival v∞, entry FPA, bank angle.  Returns captured-orbit
 *      geometry (a, e, peri, apo), peak g, peak heat flux, total heat
 *      load, Δv saved versus chemical insertion.  Uses the Phase-B
 *      atmospheric integrator.
 *
 *   3. Light-lag round-trip  — pure client-side calc; show how stale
 *      the next telemetry will be at the user's chosen distance.
 *
 *   4. Generation-ship Monte Carlo  — wires up the Phase-D ensemble
 *      runner via the SSE stream from /api/mission/ensemble/stream.
 *      Live progress bar + survival-rate readout + per-field P5/P95
 *      bands.
 *
 * The four tools intentionally share one tab so the operator can run
 * a porkchop, hand its v∞ to aerocapture, then run an ensemble — the
 * three simulators together give an end-to-end view of an
 * interplanetary mission, which used to require jumping between
 * Porkchop + LunarMissionPanel + MoonMissionPanel + nothing-for-
 * interstellar.
 */

import { useEffect, useRef, useState } from 'react';

// ── API helpers ──────────────────────────────────────────────────────

interface PorkchopResponse {
  origin: string; destination: string;
  dep_day: number; arr_day: number; tof_days: number;
  c3_departure_km2_s2: number; v_inf_arrival_km_s: number;
  total_dv_ms: number; fuel_required_kg: number;
  feasible: boolean; best_M: number;
  valid_count: number; total_count: number;
  trajectory_au?: [number, number, number][];
}

interface AerocaptureResponse {
  body: string; captured: boolean;
  captured_orbit_a_km: number; captured_orbit_e: number;
  captured_periapsis_alt_km: number; captured_apoapsis_alt_km: number;
  peak_g: number; peak_heat_flux_w_cm2: number; total_heat_load_j_cm2: number;
  pass_duration_s: number;
  delta_v_saved_m_s: number; delta_v_required_propulsive_m_s: number;
  notes: string;
  trajectory_sampled: { t_s: number; alt_km: number; v_km_s: number;
                        fpa_deg: number; g: number; q_w_cm2: number }[];
}

interface EnsembleRunEvt {
  type: 'run'; i: number; n: number; survived: boolean;
  years: number; final_hull: number; final_fuel: number;
  final_crew: number; failure_reason: string | null;
}
interface EnsembleDoneEvt {
  type: 'done'; n_runs: number; wall_time_s: number;
  survival_rate: number; failure_reasons: Record<string, number>;
  field_stats: Record<string, {
    n: number; mean: number; median: number; std: number;
    min: number; max: number; p05: number; p95: number;
  }>;
}

const PLANETS = ['mercury', 'venus', 'earth', 'mars', 'jupiter', 'saturn'] as const;
const AERO_BODIES = ['mars', 'venus', 'titan', 'earth'] as const;

// ── Top-level component ─────────────────────────────────────────────

type StudioTab = 'porkchop' | 'aerocapture' | 'lightlag' | 'ensemble';

export function MissionStudio() {
  const [tab, setTab] = useState<StudioTab>('porkchop');

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Mission Studio</h2>
        <p className="text-xs text-ui-text-dim">
          Production-grade mission simulators in one tab — multi-rev porkchop,
          aerocapture, light-lag round-trip, and Monte-Carlo generation-ship
          ensembles.  Each tab feeds the others (porkchop → v∞ → aerocapture).
        </p>
      </div>

      <div className="mb-3 flex gap-1 border-b border-ui-border">
        {([
          ['porkchop',    'Porkchop / Lambert'],
          ['aerocapture', 'Aerocapture'],
          ['lightlag',    'Light-lag'],
          ['ensemble',    'Monte Carlo'],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`px-3 py-1.5 text-xs border-b-2 -mb-px ${
              tab === id
                ? 'border-ui-accent text-ui-accent'
                : 'border-transparent text-ui-text-dim hover:text-ui-text'
            }`}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'porkchop'    && <PorkchopForm />}
      {tab === 'aerocapture' && <AerocaptureForm />}
      {tab === 'lightlag'    && <LightLagForm />}
      {tab === 'ensemble'    && <EnsembleForm />}
    </div>
  );
}

// ── Porkchop / Lambert ──────────────────────────────────────────────

function PorkchopForm() {
  const [origin, setOrigin] = useState<string>('earth');
  const [destination, setDestination] = useState<string>('mars');
  const [depWindow, setDepWindow] = useState('0,400');
  const [arrWindow, setArrWindow] = useState('150,600');
  const [dryKg, setDryKg] = useState('3000');
  const [fuelKg, setFuelKg] = useState('6000');
  const [ispS, setIspS] = useState('320');
  const [maxRevs, setMaxRevs] = useState(0);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<PorkchopResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    setLoading(true); setErr(null);
    try {
      const url = new URL('/api/mission/porkchop', window.location.origin);
      url.searchParams.set('origin', origin);
      url.searchParams.set('destination', destination);
      url.searchParams.set('dep_window_days', depWindow);
      url.searchParams.set('arr_window_days', arrWindow);
      url.searchParams.set('dry_kg', dryKg);
      url.searchParams.set('fuel_kg', fuelKg);
      url.searchParams.set('isp_s', ispS);
      url.searchParams.set('max_revs', String(maxRevs));
      const r = await fetch(url.toString());
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
      setData(j);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally    { setLoading(false); }
  };

  return (
    <div className="grid md:grid-cols-2 gap-4">
      <div className="bg-ui-bg-1/50 border border-ui-border rounded p-3 text-xs">
        <h3 className="text-ui-accent font-semibold mb-2">Inputs</h3>
        <Field label="Origin">
          <select value={origin} onChange={(e) => setOrigin(e.target.value)}
                  className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 w-full">
            {PLANETS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </Field>
        <Field label="Destination">
          <select value={destination} onChange={(e) => setDestination(e.target.value)}
                  className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 w-full">
            {PLANETS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </Field>
        <Field label="Departure window (days)">
          <input value={depWindow} onChange={(e) => setDepWindow(e.target.value)} className="input" />
        </Field>
        <Field label="Arrival window (days)">
          <input value={arrWindow} onChange={(e) => setArrWindow(e.target.value)} className="input" />
        </Field>
        <Field label="Dry mass (kg)">
          <input value={dryKg} onChange={(e) => setDryKg(e.target.value)} className="input" />
        </Field>
        <Field label="Fuel budget (kg)">
          <input value={fuelKg} onChange={(e) => setFuelKg(e.target.value)} className="input" />
        </Field>
        <Field label="Isp (s)">
          <input value={ispS} onChange={(e) => setIspS(e.target.value)} className="input" />
        </Field>
        <Field label="Max revolutions (Phase-A)">
          <select value={maxRevs} onChange={(e) => setMaxRevs(Number(e.target.value))}
                  className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 w-full">
            <option value={0}>0 (direct only)</option>
            <option value={1}>1 (Type-III)</option>
            <option value={2}>2 (Type-IV)</option>
          </select>
        </Field>
        <button onClick={run} disabled={loading}
                className="mt-3 px-3 py-1.5 bg-ui-accent/40 hover:bg-ui-accent-strong disabled:opacity-50 rounded text-white">
          {loading ? 'Running…' : 'Solve'}
        </button>
        {err && <div className="mt-2 text-sev-crit bg-sev-crit/30 border border-sev-crit rounded p-2">{err}</div>}
      </div>

      <div className="bg-ui-bg-1/50 border border-ui-border rounded p-3 text-xs">
        <h3 className="text-ui-accent font-semibold mb-2">Result</h3>
        {data ? (
          <div className="space-y-1 font-mono">
            <KV k="Origin → Destination" v={`${data.origin} → ${data.destination}`} />
            <KV k="Departure day" v={data.dep_day.toFixed(1)} />
            <KV k="Time of flight" v={`${data.tof_days.toFixed(1)} d`} />
            <KV k="C3 departure" v={`${data.c3_departure_km2_s2.toFixed(2)} km²/s²`} />
            <KV k="v∞ arrival" v={`${data.v_inf_arrival_km_s.toFixed(2)} km/s`} />
            <KV k="Total Δv" v={`${(data.total_dv_ms/1000).toFixed(2)} km/s`} />
            <KV k="Fuel required" v={`${data.fuel_required_kg.toFixed(0)} kg`} />
            <KV k="Best M (revolutions)" v={`${data.best_M}`} />
            <KV k="Valid Lambert cells" v={`${data.valid_count}/${data.total_count}`} />
            <KV k="Feasible at given fuel"
                v={data.feasible ? '✓ yes' : '✗ no — increase fuel or Isp'}
                color={data.feasible ? 'text-sev-ok' : 'text-sev-warn'} />
            {data.trajectory_au && data.trajectory_au.length > 0 && (
              <button
                onClick={() => {
                  // Push the trajectory to SolarSystem3D via a window
                  // CustomEvent — sibling tabs subscribe to draw it.
                  window.dispatchEvent(new CustomEvent('aria.mission.trajectory', {
                    detail: {
                      origin: data.origin, destination: data.destination,
                      points: data.trajectory_au,
                      label: `${data.origin} → ${data.destination} (M=${data.best_M}, ToF=${data.tof_days.toFixed(0)} d)`,
                    },
                  }));
                }}
                className="mt-3 px-3 py-1.5 bg-amber-700 hover:bg-amber-600 rounded text-white text-xs">
                Render trajectory in Solar System 3D ↗
              </button>
            )}
          </div>
        ) : <div className="text-ui-text-faint italic">Pick inputs and click Solve.</div>}
      </div>
    </div>
  );
}

// ── Aerocapture ─────────────────────────────────────────────────────

function AerocaptureForm() {
  const [body, setBody] = useState<string>('mars');
  const [vInf, setVInf] = useState('5500');
  const [fpa, setFpa] = useState('-11.5');
  const [bank, setBank] = useState('60');
  const [entry, setEntry] = useState('125000');
  const [data, setData] = useState<AerocaptureResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    setLoading(true); setErr(null);
    try {
      const url = new URL('/api/mission/aerocapture', window.location.origin);
      url.searchParams.set('body', body);
      url.searchParams.set('v_inf_m_s', vInf);
      url.searchParams.set('flight_path_deg', fpa);
      url.searchParams.set('bank_angle_deg', bank);
      url.searchParams.set('entry_alt_m', entry);
      const r = await fetch(url.toString());
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
      setData(j);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally    { setLoading(false); }
  };

  return (
    <div className="grid md:grid-cols-2 gap-4">
      <div className="bg-ui-bg-1/50 border border-ui-border rounded p-3 text-xs">
        <h3 className="text-ui-accent font-semibold mb-2">Inputs</h3>
        <Field label="Body">
          <select value={body} onChange={(e) => setBody(e.target.value)}
                  className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 w-full">
            {AERO_BODIES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </Field>
        <Field label="Arrival v∞ (m/s)">
          <input value={vInf} onChange={(e) => setVInf(e.target.value)} className="input" />
        </Field>
        <Field label="Entry flight-path angle (deg)">
          <input value={fpa} onChange={(e) => setFpa(e.target.value)} className="input" />
        </Field>
        <Field label="Bank angle (deg)">
          <input value={bank} onChange={(e) => setBank(e.target.value)} className="input" />
        </Field>
        <Field label="Entry altitude (m)">
          <input value={entry} onChange={(e) => setEntry(e.target.value)} className="input" />
        </Field>
        <button onClick={run} disabled={loading}
                className="mt-3 px-3 py-1.5 bg-ui-accent/40 hover:bg-ui-accent-strong disabled:opacity-50 rounded text-white">
          {loading ? 'Simulating…' : 'Run pass'}
        </button>
        {err && <div className="mt-2 text-sev-crit bg-sev-crit/30 border border-sev-crit rounded p-2">{err}</div>}
      </div>

      <div className="bg-ui-bg-1/50 border border-ui-border rounded p-3 text-xs">
        <h3 className="text-ui-accent font-semibold mb-2">Result</h3>
        {data ? (
          <div className="space-y-1 font-mono">
            <KV k="Captured?" v={data.captured ? '✓ yes' : '✗ no'}
                color={data.captured ? 'text-sev-ok' : 'text-sev-warn'} />
            <KV k="Notes" v={data.notes} />
            <KV k="Captured semi-major axis" v={`${data.captured_orbit_a_km.toFixed(0)} km`} />
            <KV k="Eccentricity" v={data.captured_orbit_e.toFixed(3)} />
            <KV k="Periapsis alt." v={`${data.captured_periapsis_alt_km.toFixed(0)} km`} />
            <KV k="Apoapsis alt." v={`${data.captured_apoapsis_alt_km.toFixed(0)} km`} />
            <KV k="Peak g" v={data.peak_g.toFixed(2)} />
            <KV k="Peak heat flux" v={`${data.peak_heat_flux_w_cm2.toFixed(1)} W/cm²`} />
            <KV k="Total heat load" v={`${(data.total_heat_load_j_cm2/1000).toFixed(1)} kJ/cm²`} />
            <KV k="Pass duration" v={`${data.pass_duration_s.toFixed(0)} s`} />
            <KV k="Δv saved (vs propulsive)"
                v={`${data.delta_v_saved_m_s.toFixed(0)} of ${data.delta_v_required_propulsive_m_s.toFixed(0)} m/s`}
                color="text-sev-ok" />
            {data.trajectory_sampled.length > 0 && (
              <div className="mt-3 pt-2 border-t border-ui-border">
                <div className="text-[10px] uppercase tracking-wider text-ui-text-dim mb-1">Altitude profile</div>
                <TrajectoryMiniChart points={data.trajectory_sampled.map(s => [s.t_s, s.alt_km])} />
              </div>
            )}
          </div>
        ) : <div className="text-ui-text-faint italic">Pick inputs and click Run pass.</div>}
      </div>
    </div>
  );
}

// ── Light-lag round-trip ────────────────────────────────────────────

function LightLagForm() {
  const [distance, setDistance] = useState('4.24');   // ly
  const [unit, setUnit]         = useState<'ly' | 'au' | 'km'>('ly');

  // c in m/s — speed of light (NIST CODATA exact).
  const C_M_S = 299792458;
  const LY_M = 9.4607304725808e15;
  const AU_M = 1.495978707e11;
  const dM = unit === 'ly' ? Number(distance) * LY_M
            : unit === 'au' ? Number(distance) * AU_M
            : Number(distance) * 1000;
  const oneWayS = dM / C_M_S;
  const rttS    = 2 * oneWayS;

  const fmt = (s: number) => {
    if (s < 60)        return `${s.toFixed(2)} s`;
    if (s < 3600)      return `${(s/60).toFixed(2)} min`;
    if (s < 86400)     return `${(s/3600).toFixed(2)} hr`;
    if (s < 365.25*86400) return `${(s/86400).toFixed(2)} d`;
    return `${(s/(365.25*86400)).toFixed(2)} yr`;
  };

  return (
    <div className="grid md:grid-cols-2 gap-4">
      <div className="bg-ui-bg-1/50 border border-ui-border rounded p-3 text-xs">
        <h3 className="text-ui-accent font-semibold mb-2">Distance</h3>
        <Field label="Value">
          <input value={distance} onChange={(e) => setDistance(e.target.value)} className="input" />
        </Field>
        <Field label="Unit">
          <select value={unit} onChange={(e) => setUnit(e.target.value as 'ly'|'au'|'km')}
                  className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 w-full">
            <option value="ly">light-years</option>
            <option value="au">astronomical units</option>
            <option value="km">kilometres</option>
          </select>
        </Field>
        <div className="text-[10px] text-ui-text-faint mt-2 space-y-0.5">
          <p>Earth-Moon avg: 384 400 km</p>
          <p>Earth-Mars opposition: 0.52 AU</p>
          <p>Voyager 1 (2026): 24.6 light-hours ≈ 0.0028 ly</p>
          <p>Proxima Centauri: 4.24 ly</p>
        </div>
      </div>

      <div className="bg-ui-bg-1/50 border border-ui-border rounded p-3 text-xs">
        <h3 className="text-ui-accent font-semibold mb-2">Round-trip</h3>
        <div className="space-y-1 font-mono">
          <KV k="Distance" v={`${dM.toExponential(3)} m`} />
          <KV k="One-way" v={fmt(oneWayS)} />
          <KV k="Round-trip" v={fmt(rttS)} color="text-sev-warn" />
        </div>
        <p className="mt-3 text-[11px] text-ui-text-dim">
          Operationally: a command queued today won't see *any* response
          until {fmt(rttS)} from now.  At that point the spacecraft has
          already moved another {fmt(rttS)} into the future of its own
          state machine.  Spacecraft this far out must be effectively
          autonomous for any decision shorter than the round-trip.
        </p>
      </div>
    </div>
  );
}

// ── Monte-Carlo ensemble (SSE) ──────────────────────────────────────

function EnsembleForm() {
  const [n, setN] = useState(20);
  const [vC, setVC] = useState('0.20');
  const [targetLy, setTargetLy] = useState('1.0');
  const [crew, setCrew] = useState('4');
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<{i: number; n: number}>({i: 0, n: 0});
  const [runs, setRuns] = useState<EnsembleRunEvt[]>([]);
  const [done, setDone] = useState<EnsembleDoneEvt | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  const run = () => {
    if (running) return;
    setRunning(true); setRuns([]); setDone(null); setProgress({i: 0, n});
    const url = new URL('/api/mission/ensemble/stream', window.location.origin);
    url.searchParams.set('n', String(n));
    url.searchParams.set('velocity_c', vC);
    url.searchParams.set('target_ly', targetLy);
    url.searchParams.set('crew_size', crew);
    url.searchParams.set('minimal', '1');
    const es = new EventSource(url.toString());
    sourceRef.current = es;
    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.type === 'run') {
        setRuns((prev) => [...prev, data]);
        setProgress({i: data.i, n: data.n});
      } else if (data.type === 'done') {
        setDone(data);
        setRunning(false);
        es.close();
      }
    };
    es.onerror = () => {
      setRunning(false);
      es.close();
    };
  };

  useEffect(() => () => sourceRef.current?.close(), []);

  return (
    <div className="grid md:grid-cols-2 gap-4">
      <div className="bg-ui-bg-1/50 border border-ui-border rounded p-3 text-xs">
        <h3 className="text-ui-accent font-semibold mb-2">Ensemble inputs</h3>
        <Field label="Number of runs (capped at 200)">
          <input type="number" value={n} min={1} max={200}
                 onChange={(e) => setN(Math.min(200, Math.max(1, Number(e.target.value))))} className="input" />
        </Field>
        <Field label="Velocity (c)">
          <input value={vC} onChange={(e) => setVC(e.target.value)} className="input" />
        </Field>
        <Field label="Target distance (ly)">
          <input value={targetLy} onChange={(e) => setTargetLy(e.target.value)} className="input" />
        </Field>
        <Field label="Crew size">
          <input value={crew} onChange={(e) => setCrew(e.target.value)} className="input" />
        </Field>
        <button onClick={run} disabled={running}
                className="mt-3 px-3 py-1.5 bg-ui-accent/40 hover:bg-ui-accent-strong disabled:opacity-50 rounded text-white">
          {running ? `Running ${progress.i}/${progress.n}…` : 'Start ensemble'}
        </button>
        {running && (
          <div className="mt-3 h-2 bg-ui-bg-2 rounded overflow-hidden">
            <div className="h-full bg-ui-accent transition-all"
                 style={{ width: `${(progress.i / Math.max(progress.n, 1)) * 100}%` }} />
          </div>
        )}
      </div>

      <div className="bg-ui-bg-1/50 border border-ui-border rounded p-3 text-xs">
        <h3 className="text-ui-accent font-semibold mb-2">Live runs</h3>
        <div className="max-h-48 overflow-y-auto font-mono text-[11px] space-y-0.5">
          {runs.length === 0 && <div className="text-ui-text-faint italic">Waiting for first run.</div>}
          {runs.map((r) => (
            <div key={r.i} className="flex justify-between border-b border-ui-border-soft/60 py-0.5">
              <span className="text-ui-text-dim">#{r.i}</span>
              <span className={r.survived ? 'text-sev-ok' : 'text-sev-warn'}>
                {r.survived ? '✓' : '✗'} hull {r.final_hull.toFixed(3)}, fuel {r.final_fuel.toFixed(3)}, crew {r.final_crew}
              </span>
            </div>
          ))}
        </div>

        {done && (
          <div className="mt-3 pt-3 border-t border-ui-border space-y-1 font-mono">
            <KV k="Runs completed" v={`${done.n_runs}`} />
            <KV k="Wall-clock" v={`${done.wall_time_s.toFixed(1)} s`} />
            <KV k="Survival rate" v={`${(done.survival_rate * 100).toFixed(1)} %`}
                color={done.survival_rate > 0.5 ? 'text-sev-ok' : 'text-sev-warn'} />
            {Object.entries(done.failure_reasons).slice(0, 3).map(([reason, count]) => (
              <div key={reason} className="text-[10px] text-ui-text-dim">
                {count}× {reason}
              </div>
            ))}
            {done.field_stats.final_hull_integrity && (
              <KV k="Hull P5/P95"
                  v={`${done.field_stats.final_hull_integrity.p05.toFixed(3)} / ${done.field_stats.final_hull_integrity.p95.toFixed(3)}`} />
            )}
            {done.field_stats.final_fuel_fraction && (
              <KV k="Fuel P5/P95"
                  v={`${done.field_stats.final_fuel_fraction.p05.toFixed(3)} / ${done.field_stats.final_fuel_fraction.p95.toFixed(3)}`} />
            )}
            {done.field_stats.lorentz_gamma && (
              <KV k="γ P5/P95"
                  v={`${done.field_stats.lorentz_gamma.p05.toFixed(4)} / ${done.field_stats.lorentz_gamma.p95.toFixed(4)}`} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Atomic UI helpers ──────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block mb-2">
      <span className="block text-[10px] uppercase tracking-wider text-ui-text-dim mb-0.5">{label}</span>
      {children}
    </label>
  );
}

function KV({ k, v, color }: { k: string; v: React.ReactNode; color?: string }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-ui-text-dim">{k}</span>
      <span className={color ?? 'text-ui-text'}>{v}</span>
    </div>
  );
}

function TrajectoryMiniChart({ points }: { points: [number, number][] }) {
  if (points.length === 0) return null;
  const w = 280, h = 90;
  const xs = points.map(p => p[0]);
  const ys = points.map(p => p[1]);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const path = points
    .map(([x, y], i) => {
      const px = ((x - xMin) / (xMax - xMin || 1)) * w;
      const py = h - ((y - yMin) / (yMax - yMin || 1)) * h;
      return `${i === 0 ? 'M' : 'L'} ${px.toFixed(1)} ${py.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg width={w} height={h} className="bg-ui-bg-0 rounded">
      <path d={path} stroke="#67e8f9" strokeWidth="1.2" fill="none" />
      <text x={3} y={h - 3} fill="#64748b" fontSize="9" fontFamily="monospace">
        t={xMin.toFixed(0)}-{xMax.toFixed(0)}s · alt {yMin.toFixed(0)}-{yMax.toFixed(0)}km
      </text>
    </svg>
  );
}
