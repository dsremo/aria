/**
 * Mission Planner — ordered list of destinations, each with an optional
 * refuel-on-arrival flag. "Run" button executes the plan autonomously:
 *
 *   set_target(leg.target)
 *   force transition → BOOST
 *   tick until phase becomes ARRIVAL (with a max-yr safety cap)
 *   optional refuel (advances mission clock by body-specific yr)
 *   repeat
 *
 * Live-updates the UI every tick so the user watches the mission
 * progress in real time. Any backend 400/500 aborts the plan with a
 * visible error message. Closes the loop on the existing ISRU +
 * auto-arrival + fuel-gate + closed-loop-DECEL work.
 */

import { useEffect, useRef, useState } from 'react';
import { ariaApi, type TrajectoryTarget, type GravityAssistPlan } from '../api/aria';

interface Leg {
  target: string;
  refuelOnArrival: boolean;
}

interface LegResult {
  target: string;
  startedYr: number;
  arrivedYr: number | null;   // null if still running / failed
  propAtArrival: number | null;
  refuelYears: number;        // 0 if not refuelled
  error: string | null;
}

// Example presets a user might start from — all physically valid within
// the simulator's 186 km/s Tsiolkovsky bound + the ISRU catalog.
const PRESETS: { id: string; label: string; legs: Leg[] }[] = [
  { id: 'earth-moon',   label: 'Shakedown: Earth → Moon', legs: [
    { target: 'Moon', refuelOnArrival: true },
  ]},
  { id: 'proxima-direct', label: 'Direct: Earth → Proxima Centauri', legs: [
    { target: 'Proxima Centauri', refuelOnArrival: false },
  ]},
  { id: 'tau-ceti-direct', label: 'Direct: Earth → Tau Ceti (11.9 ly)', legs: [
    { target: 'Tau Ceti', refuelOnArrival: false },
  ]},
  { id: 'grand-tour',   label: 'Grand Tour: Moon → Mars → Jupiter → Pluto', legs: [
    { target: 'Moon',    refuelOnArrival: true },
    { target: 'Mars',    refuelOnArrival: true },
    { target: 'Jupiter', refuelOnArrival: true },
    { target: 'Pluto',   refuelOnArrival: true },
  ]},
  { id: 'proxima',      label: 'Generation ship: Moon → Pluto → Oort → Proxima', legs: [
    { target: 'Moon',             refuelOnArrival: true },
    { target: 'Pluto',            refuelOnArrival: true },
    { target: 'Inner Oort Cloud', refuelOnArrival: true },
    { target: 'Proxima Centauri', refuelOnArrival: false },
  ]},
];

export function MissionPlannerPanel() {
  const [targets, setTargets]   = useState<TrajectoryTarget[]>([]);
  const [plan, setPlan]         = useState<Leg[]>(PRESETS[0].legs);
  const [running, setRunning]   = useState(false);
  const [results, setResults]   = useState<LegResult[]>([]);
  const [currentLeg, setCurrentLeg] = useState<number | null>(null);
  const [statusLine, setStatusLine] = useState<string>('');
  const [abort, setAbort]       = useState(false);
  // Ref mirror of `abort` so the async run() loop always observes the
  // latest value (setAbort updates state asynchronously; the while-loop
  // closure would otherwise read the false captured at run() start and
  // ignore the user clicking Abort mid-plan).
  const abortRef = useRef(false);

  // ── Gravity-assist patched-conic planner ────────────────────────
  // Purely analytical side panel — does NOT touch live simulator
  // state. Chains Hohmann legs + fly-by Δv credits so the user can
  // see "Earth → Venus → Earth → Jupiter → Saturn" fuel savings
  // before committing to a real mission plan.
  const GA_BODIES = ['mercury', 'venus', 'earth', 'mars',
                     'jupiter', 'saturn', 'uranus', 'neptune', 'pluto'];
  const GA_PRESETS: { id: string; label: string; start: string; destination: string; flybys: string[] }[] = [
    { id: 'direct-jupiter',  label: 'Direct: Earth → Jupiter',            start: 'earth', destination: 'jupiter', flybys: [] },
    { id: 'voyager-like',    label: 'Voyager-like: Earth → Jupiter → Saturn', start: 'earth', destination: 'saturn',  flybys: ['jupiter'] },
    { id: 'galileo-like',    label: 'Galileo-like: Earth → Venus → Earth → Jupiter', start: 'earth', destination: 'jupiter', flybys: ['venus', 'earth'] },
    { id: 'grand-tour',      label: 'Grand Tour: Earth → Jup → Sat → Ura → Nep',   start: 'earth', destination: 'neptune', flybys: ['jupiter', 'saturn', 'uranus'] },
    { id: 'cassini-like',    label: 'Cassini-like: Earth → Venus → Venus → Earth → Jupiter → Saturn', start: 'earth', destination: 'saturn', flybys: ['venus', 'venus', 'earth', 'jupiter'] },
  ];
  const [gaStart, setGaStart]           = useState<string>('earth');
  const [gaDestination, setGaDestination] = useState<string>('saturn');
  const [gaFlybys, setGaFlybys]         = useState<string[]>(['jupiter']);
  const [gaAltKm, setGaAltKm]           = useState<number>(300);
  const [gaPlan, setGaPlan]             = useState<GravityAssistPlan | null>(null);
  const [gaError, setGaError]           = useState<string | null>(null);
  const [gaRunning, setGaRunning]       = useState(false);

  const gaLoadPreset = (id: string) => {
    const p = GA_PRESETS.find(x => x.id === id);
    if (!p) return;
    setGaStart(p.start);
    setGaDestination(p.destination);
    setGaFlybys([...p.flybys]);
  };
  const gaAddFlyby = (body: string) => {
    if (!body) return;
    setGaFlybys(f => [...f, body]);
  };
  const gaRemoveFlyby = (i: number) => setGaFlybys(f => f.filter((_, idx) => idx !== i));
  const gaComputePlan = async () => {
    setGaRunning(true);
    setGaError(null);
    try {
      const p = await ariaApi.gravityAssistPlan(gaStart, gaDestination, gaFlybys, gaAltKm);
      setGaPlan(p);
    } catch (e: any) {
      setGaError(String(e?.message ?? e).slice(0, 200));
      setGaPlan(null);
    } finally {
      setGaRunning(false);
    }
  };

  useEffect(() => {
    ariaApi.trajectoryTargets().then(r => setTargets(r.targets)).catch(() => {});
  }, []);

  const addLeg = (target: string) => {
    if (!target) return;
    setPlan(p => [...p, { target, refuelOnArrival: true }]);
  };
  const removeLeg = (i: number) => setPlan(p => p.filter((_, idx) => idx !== i));
  const moveLeg = (i: number, delta: number) => setPlan(p => {
    const next = [...p];
    const j = i + delta;
    if (j < 0 || j >= next.length) return p;
    [next[i], next[j]] = [next[j], next[i]];
    return next;
  });
  const toggleRefuel = (i: number) => setPlan(p => p.map((l, idx) => idx === i ? { ...l, refuelOnArrival: !l.refuelOnArrival } : l));
  const loadPreset = (id: string) => {
    const p = PRESETS.find(x => x.id === id);
    if (p) setPlan([...p.legs]);
  };

  const run = async () => {
    setRunning(true);
    setResults([]);
    setAbort(false);
    abortRef.current = false;
    let savedPhase: Awaited<ReturnType<typeof ariaApi.missionPhase>> | null = null;
    let savedTrajectory: Awaited<ReturnType<typeof ariaApi.trajectory>> | null = null;
    try {
      try { savedPhase = await ariaApi.missionPhase(); } catch { savedPhase = null; }
      try { savedTrajectory = await ariaApi.trajectory(); } catch { savedTrajectory = null; }
      try {
      // Reset to a clean state so legs don't inherit leftover trajectory.
      await ariaApi.missionTransition('prelaunch', true);

      for (let i = 0; i < plan.length; i++) {
        if (abortRef.current) break;
        setCurrentLeg(i);
        const leg = plan[i];
        setStatusLine(`Leg ${i + 1}/${plan.length} — targeting ${leg.target}`);

        const t0State = await ariaApi.trajectory();
        const startedYr = t0State.elapsed_yr;
        const legResult: LegResult = {
          target: leg.target, startedYr,
          arrivedYr: null, propAtArrival: null, refuelYears: 0, error: null,
        };
        setResults(r => [...r, legResult]);

        try {
          // Reset trajectory for the new leg. set_target wipes position.
          await ariaApi.trajectorySetTarget(leg.target);
          // Force BOOST so we always thrust at the start, even after a
          // previous ARRIVAL clamp.
          await ariaApi.missionTransition('prelaunch', true);
          await ariaApi.missionTransition('boost', true);

          // Step-advance until phase == arrival OR we exhaust a max
          // mission-year cap per leg (safety).
          const MAX_LEG_YR = 50_000;
          let legYr = 0;
          const stepLadder = [0.001, 0.01, 0.1, 1, 10, 100, 1000, 5000];
          let stepIdx = 0;
          // Throttle status-line updates: at step=0.001 the inner loop
          // runs ~100x/s — stop React re-rendering every iteration.
          let lastStatusAt = 0;
          const STATUS_THROTTLE_MS = 100;
          while (!abortRef.current) {
            const phase = await ariaApi.missionPhase();
            // Terminate on any end-state phase, not just arrival/orbit.
            // EMERGENCY was being ignored, so a flared leg would spin
            // up to MAX_LEG_YR (50 000 sim years) before breaking out.
            if (phase.current_phase === 'arrival'
                || phase.current_phase === 'orbit') break;
            if (phase.current_phase === 'emergency') {
              throw new Error(`Leg entered EMERGENCY phase — aborting leg (check alarms).`);
            }
            if (legYr > MAX_LEG_YR) {
              throw new Error(`Leg exceeded ${MAX_LEG_YR} yr cap; stuck in ${phase.current_phase}`);
            }
            const step = stepLadder[Math.min(stepIdx, stepLadder.length - 1)];
            await ariaApi.missionTick(step);
            legYr += step;
            // Grow the step once trajectory hits Tsiolkovsky cap (cruise).
            if (phase.current_phase === 'cruise') stepIdx = Math.min(stepIdx + 1, stepLadder.length - 1);
            const now = Date.now();
            if (now - lastStatusAt >= STATUS_THROTTLE_MS) {
              const t = await ariaApi.trajectory();
              setStatusLine(`Leg ${i + 1}/${plan.length} · ${leg.target} · ${phase.current_phase} · pos ${t.fraction_complete * 100 | 0}% · prop ${(t.propellant_fraction_remaining * 100) | 0}% · yr ${t.elapsed_yr.toFixed(1)}`);
              lastStatusAt = now;
            }
          }

          if (abortRef.current) { legResult.error = 'aborted'; break; }

          const arrivedT = await ariaApi.trajectory();
          legResult.arrivedYr = arrivedT.elapsed_yr;
          legResult.propAtArrival = arrivedT.propellant_fraction_remaining;

          if (leg.refuelOnArrival) {
            setStatusLine(`Leg ${i + 1} — refuelling at ${leg.target}`);
            try {
              const r = await ariaApi.trajectoryRefuel();
              legResult.refuelYears = r.refuel_years;
            } catch (e: any) {
              legResult.error = 'refuel failed: ' + String(e?.message ?? e).slice(0, 120);
            }
          }
          setResults(rs => rs.map((r, idx) => idx === i ? legResult : r));
        } catch (e: any) {
          legResult.error = String(e?.message ?? e).slice(0, 160);
          setResults(rs => rs.map((r, idx) => idx === i ? legResult : r));
          break;
        }
      }
      } finally {
        try {
          if (savedPhase) {
            await ariaApi.missionTransition(savedPhase.current_phase, true);
          }
          if (savedTrajectory && savedTrajectory.target) {
            await ariaApi.trajectorySetTarget(savedTrajectory.target);
          }
        } catch { void 0; }
      }
    } finally {
      setRunning(false);
      setCurrentLeg(null);
      const base = abortRef.current ? 'Aborted.' : 'Plan complete.';
      setStatusLine(savedPhase ? `${base} Live sim restored to ${savedPhase.current_phase}.` : base);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-3 space-y-3 text-sm">
      <div>
        <div className="text-[10px] uppercase tracking-widest text-ui-accent font-bold">Mission Planner</div>
        <div className="text-[11px] text-ui-text-dim">
          Chain multi-leg missions with automatic BOOST → ARRIVAL detection
          and optional ISRU refuelling between legs. All physics is live
          (Tsiolkovsky-bounded Δv, fuel-gate, auto-arrival, body-specific
          refuel time costs).
        </div>
      </div>

      {/* Presets */}
      <div className="flex flex-wrap gap-1">
        {PRESETS.map(p => (
          <button key={p.id} onClick={() => loadPreset(p.id)}
                  disabled={running}
                  className="px-2 py-1 text-[10px] rounded border border-ui-border bg-ui-bg-2 hover:bg-ui-bg-3 text-ui-text disabled:opacity-50">
            {p.label}
          </button>
        ))}
      </div>

      {/* Leg table */}
      <div className="bg-ui-bg-1/40 border border-ui-border rounded overflow-hidden">
        <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-2 px-2 py-1 text-[9px] uppercase tracking-wide text-ui-text-faint border-b border-ui-border bg-ui-bg-1/60">
          <div>Target</div><div>Refuel</div><div>Up</div><div>Down</div><div>×</div>
        </div>
        {plan.length === 0 && (
          <div className="p-3 text-[11px] text-ui-text-faint italic">Empty plan — add legs below.</div>
        )}
        {plan.map((l, i) => (
          <div key={i} className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-2 px-2 py-1 items-center text-[11px] border-b border-ui-border-soft last:border-b-0">
            <div className={`font-mono ${currentLeg === i && running ? 'text-ui-accent' : 'text-ui-text'}`}>
              {currentLeg === i && running && '▶ '}
              {l.target}
            </div>
            <button onClick={() => toggleRefuel(i)} disabled={running}
                    className={`text-[9px] px-1 rounded ${l.refuelOnArrival ? 'bg-sev-ok/50 text-sev-ok' : 'bg-ui-bg-2 text-ui-text-faint'}`}>
              {l.refuelOnArrival ? '🛢 refuel' : 'no refuel'}
            </button>
            <button onClick={() => moveLeg(i, -1)} disabled={running || i === 0}
                    className="text-[10px] px-1 text-ui-text-dim hover:text-ui-text disabled:opacity-30">▲</button>
            <button onClick={() => moveLeg(i, +1)} disabled={running || i === plan.length - 1}
                    className="text-[10px] px-1 text-ui-text-dim hover:text-ui-text disabled:opacity-30">▼</button>
            <button onClick={() => removeLeg(i)} disabled={running}
                    className="text-[10px] px-1 text-sev-crit hover:text-sev-crit disabled:opacity-30">×</button>
          </div>
        ))}
      </div>

      {/* Add leg */}
      <div className="flex gap-1 items-center">
        <select disabled={running} id="addLegTarget"
                className="px-1 py-0.5 text-xs bg-ui-bg-2 border border-ui-border rounded flex-1">
          <option value="">+ Add leg…</option>
          <optgroup label="Solar System">
            {targets.filter(t => t.class === 'solar').map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
          </optgroup>
          <optgroup label="Interstellar">
            {targets.filter(t => t.class === 'interstellar').map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
          </optgroup>
        </select>
        <button disabled={running}
                onClick={() => {
                  const el = document.getElementById('addLegTarget') as HTMLSelectElement | null;
                  if (el?.value) { addLeg(el.value); el.value = ''; }
                }}
                className="px-2 py-1 text-[10px] rounded border border-ui-border bg-ui-bg-2 hover:bg-ui-bg-3 text-ui-text disabled:opacity-50">
          Add
        </button>
      </div>

      {/* Run */}
      <div className="flex gap-2">
        <button onClick={run} disabled={running || plan.length === 0}
                className="px-3 py-1.5 text-xs rounded border font-bold bg-sev-ok/60 border-sev-ok text-sev-ok hover:bg-sev-ok/30 disabled:opacity-50">
          {running ? '⏳ Running…' : '▶ Run plan'}
        </button>
        {running && (
          <button onClick={() => { abortRef.current = true; setAbort(true); }}
                  className="px-3 py-1.5 text-xs rounded border bg-sev-crit/50 border-sev-crit text-sev-crit hover:bg-sev-crit/70">
            Abort
          </button>
        )}
      </div>

      {statusLine && (
        <div className="p-2 bg-ui-bg-1/50 border border-ui-accent/60 rounded text-[10px] font-mono text-ui-accent">
          {statusLine}
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="bg-ui-bg-1/40 border border-ui-border rounded overflow-hidden">
          <div className="text-[10px] uppercase tracking-wide text-ui-text-dim px-2 py-1 bg-ui-bg-1/60 border-b border-ui-border">
            Leg results
          </div>
          <table className="w-full text-[10px]">
            <thead className="text-ui-text-dim">
              <tr>
                <th className="text-left px-2 py-1">#</th>
                <th className="text-left px-2">Target</th>
                <th className="text-right px-2">Start yr</th>
                <th className="text-right px-2">Arrive yr</th>
                <th className="text-right px-2">Δt</th>
                <th className="text-right px-2">Prop%</th>
                <th className="text-right px-2">Refuel</th>
                <th className="text-left px-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={i} className="border-t border-ui-border-soft">
                  <td className="px-2 py-1 text-ui-text-faint">{i + 1}</td>
                  <td className="px-2 font-mono">{r.target}</td>
                  <td className="px-2 text-right font-mono">{r.startedYr.toFixed(2)}</td>
                  <td className="px-2 text-right font-mono">{r.arrivedYr != null ? r.arrivedYr.toFixed(2) : '—'}</td>
                  <td className="px-2 text-right font-mono text-ui-accent">
                    {r.arrivedYr != null ? (r.arrivedYr - r.startedYr).toFixed(2) : '—'}
                  </td>
                  <td className="px-2 text-right font-mono">
                    {r.propAtArrival != null ? (r.propAtArrival * 100).toFixed(1) : '—'}
                  </td>
                  <td className="px-2 text-right font-mono text-sev-ok">
                    {r.refuelYears > 0 ? `+${r.refuelYears.toFixed(1)}y` : '—'}
                  </td>
                  <td className={`px-2 text-[9px] ${r.error ? 'text-sev-crit' : 'text-sev-ok'}`}>
                    {r.error ? '⚠ ' + r.error.slice(0, 60) : (r.arrivedYr != null ? '✓' : '…')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════
            Gravity-Assist Mission Planner (patched-conic)

            Purely analytical — Hohmann transfers between each pair of
            bodies, fly-by Δv credits computed from 2·v_planet·sin(δ/2).
            Bypasses the live simulator — shows Voyager-class tradeoffs
            before committing to a real mission plan.
          ═══════════════════════════════════════════════════════════ */}
      <div className="mt-4 pt-4 border-t border-ui-border">
        <div className="text-[10px] uppercase tracking-widest text-ui-accent font-bold">
          Gravity-Assist Planner (patched-conic)
        </div>
        <div className="text-[11px] text-ui-text-dim mb-2">
          Chain Hohmann transfers with fly-by Δv credits. Each fly-by
          at an intermediate planet contributes up to
          2·v<sub>planet</sub>·sin(δ/2) of free heliocentric Δv.
        </div>

        {/* GA Presets */}
        <div className="flex flex-wrap gap-1 mb-2">
          {GA_PRESETS.map(p => (
            <button key={p.id} onClick={() => gaLoadPreset(p.id)}
                    className="px-2 py-1 text-[10px] rounded border border-purple-800/60 bg-ui-accent/30 hover:bg-ui-accent/40 text-ui-accent">
              {p.label}
            </button>
          ))}
        </div>

        {/* Start + destination + alt */}
        <div className="grid grid-cols-[auto_1fr_auto_1fr_auto_1fr] gap-2 items-center mb-2 text-[11px]">
          <label className="text-ui-text-dim">From</label>
          <select value={gaStart} onChange={e => setGaStart(e.target.value)}
                  className="px-1 py-0.5 bg-ui-bg-2 border border-ui-border rounded">
            {GA_BODIES.map(b => <option key={b} value={b}>{b}</option>)}
          </select>
          <label className="text-ui-text-dim">To</label>
          <select value={gaDestination} onChange={e => setGaDestination(e.target.value)}
                  className="px-1 py-0.5 bg-ui-bg-2 border border-ui-border rounded">
            {GA_BODIES.map(b => <option key={b} value={b}>{b}</option>)}
          </select>
          <label className="text-ui-text-dim">Peri alt (km)</label>
          <input type="number" value={gaAltKm} min={100} max={1_000_000} step={100}
                 onChange={e => setGaAltKm(Number(e.target.value) || 300)}
                 className="px-1 py-0.5 bg-ui-bg-2 border border-ui-border rounded font-mono" />
        </div>

        {/* Fly-by chain */}
        <div className="bg-ui-bg-1/40 border border-ui-border rounded overflow-hidden mb-2">
          <div className="px-2 py-1 text-[9px] uppercase tracking-wide text-ui-text-faint border-b border-ui-border bg-ui-bg-1/60">
            Fly-by chain (order matters)
          </div>
          <div className="p-2 flex flex-wrap gap-1 items-center text-[11px]">
            <span className="font-mono text-ui-accent">{gaStart}</span>
            {gaFlybys.map((fb, i) => (
              <span key={i} className="flex items-center gap-1">
                <span className="text-ui-text-faint">→</span>
                <span className="font-mono px-1.5 py-0.5 rounded bg-ui-accent/40 border border-ui-accent text-ui-accent">
                  {fb}
                </span>
                <button onClick={() => gaRemoveFlyby(i)}
                        className="text-[9px] text-sev-crit hover:text-sev-crit">×</button>
              </span>
            ))}
            <span className="text-ui-text-faint">→</span>
            <span className="font-mono text-ui-accent">{gaDestination}</span>
          </div>
          <div className="px-2 py-1 border-t border-ui-border bg-ui-bg-1/60 flex gap-1 items-center">
            <select id="gaAddFlyby"
                    className="px-1 py-0.5 text-[10px] bg-ui-bg-2 border border-ui-border rounded flex-1">
              <option value="">+ Add fly-by…</option>
              {GA_BODIES.map(b => <option key={b} value={b}>{b}</option>)}
            </select>
            <button onClick={() => {
                      const el = document.getElementById('gaAddFlyby') as HTMLSelectElement | null;
                      if (el?.value) { gaAddFlyby(el.value); el.value = ''; }
                    }}
                    className="px-2 py-0.5 text-[10px] rounded border border-ui-border bg-ui-bg-2 hover:bg-ui-bg-3 text-ui-text">
              Add
            </button>
          </div>
        </div>

        <button onClick={gaComputePlan} disabled={gaRunning}
                className="px-3 py-1.5 text-xs rounded border font-bold bg-ui-accent/60 border-ui-accent text-ui-accent hover:bg-ui-accent/40 disabled:opacity-50">
          {gaRunning ? '⏳ Computing…' : '∑ Compute plan'}
        </button>

        {gaError && (
          <div className="mt-2 p-2 bg-sev-crit/30 border border-sev-crit rounded text-[10px] text-sev-crit">
            ⚠ {gaError}
          </div>
        )}

        {gaPlan && (
          <div className="mt-2 space-y-2">
            {/* Totals */}
            <div className="grid grid-cols-4 gap-2 text-center">
              <div className="bg-ui-bg-1/50 border border-ui-border rounded p-1.5">
                <div className="text-[9px] uppercase tracking-wide text-ui-text-faint">Total Δv</div>
                <div className="text-sm font-mono text-ui-accent">{gaPlan.total_dv_required_kms.toFixed(2)} km/s</div>
              </div>
              <div className="bg-ui-bg-1/50 border border-ui-border rounded p-1.5">
                <div className="text-[9px] uppercase tracking-wide text-ui-text-faint">Gross Δv</div>
                <div className="text-sm font-mono text-ui-text">{gaPlan.total_dv_gross_kms.toFixed(2)} km/s</div>
              </div>
              <div className="bg-ui-bg-1/50 border border-sev-ok rounded p-1.5">
                <div className="text-[9px] uppercase tracking-wide text-sev-ok">Fly-by savings</div>
                <div className="text-sm font-mono text-sev-ok">−{gaPlan.total_dv_savings_kms.toFixed(2)} km/s</div>
              </div>
              <div className="bg-ui-bg-1/50 border border-ui-border rounded p-1.5">
                <div className="text-[9px] uppercase tracking-wide text-ui-text-faint">Duration</div>
                <div className="text-sm font-mono text-ui-accent">{gaPlan.total_duration_years.toFixed(2)} yr</div>
              </div>
            </div>

            {/* Leg-by-leg */}
            <div className="bg-ui-bg-1/40 border border-ui-border rounded overflow-hidden">
              <div className="text-[10px] uppercase tracking-wide text-ui-text-dim px-2 py-1 bg-ui-bg-1/60 border-b border-ui-border">
                Per-leg breakdown — {gaPlan.summary}
              </div>
              <table className="w-full text-[10px]">
                <thead className="text-ui-text-dim">
                  <tr>
                    <th className="text-left px-2 py-1">#</th>
                    <th className="text-left px-2">Leg</th>
                    <th className="text-right px-2">r₁ (AU)</th>
                    <th className="text-right px-2">r₂ (AU)</th>
                    <th className="text-right px-2">Δv₁</th>
                    <th className="text-right px-2">Δv₂</th>
                    <th className="text-right px-2">Total Δv</th>
                    <th className="text-right px-2">ToF (yr)</th>
                  </tr>
                </thead>
                <tbody>
                  {gaPlan.legs.map((lg, i) => (
                    <tr key={i} className="border-t border-ui-border-soft">
                      <td className="px-2 py-1 text-ui-text-faint">{i + 1}</td>
                      <td className="px-2 font-mono">{lg.origin} → {lg.destination}</td>
                      <td className="px-2 text-right font-mono">{lg.r1_au.toFixed(2)}</td>
                      <td className="px-2 text-right font-mono">{lg.r2_au.toFixed(2)}</td>
                      <td className="px-2 text-right font-mono">{lg.dv_depart_kms.toFixed(2)}</td>
                      <td className="px-2 text-right font-mono">{lg.dv_arrive_kms.toFixed(2)}</td>
                      <td className="px-2 text-right font-mono text-ui-accent">{lg.dv_total_kms.toFixed(2)}</td>
                      <td className="px-2 text-right font-mono">{lg.time_of_flight_years.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Fly-by savings */}
            {gaPlan.flybys.length > 0 && (
              <div className="bg-ui-bg-1/40 border border-sev-ok/60 rounded overflow-hidden">
                <div className="text-[10px] uppercase tracking-wide text-sev-ok px-2 py-1 bg-sev-ok/40 border-b border-sev-ok">
                  Fly-by Δv credits
                </div>
                <table className="w-full text-[10px]">
                  <thead className="text-ui-text-dim">
                    <tr>
                      <th className="text-left px-2 py-1">Planet</th>
                      <th className="text-right px-2">v∞ (km/s)</th>
                      <th className="text-right px-2">Deflection δ</th>
                      <th className="text-right px-2">Peri alt</th>
                      <th className="text-right px-2">Δv gained</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gaPlan.flybys.map((fb, i) => (
                      <tr key={i} className="border-t border-ui-border-soft">
                        <td className="px-2 py-1 font-mono">{fb.planet}</td>
                        <td className="px-2 text-right font-mono">{fb.v_approach_kms.toFixed(2)}</td>
                        <td className="px-2 text-right font-mono">{fb.deflection_deg.toFixed(1)}°</td>
                        <td className="px-2 text-right font-mono">{fb.closest_approach_km.toFixed(0)} km</td>
                        <td className="px-2 text-right font-mono text-sev-ok">+{fb.dv_gained_kms.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
