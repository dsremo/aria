/**
 * Trajectory panel — ship position vs Alpha Centauri on a 1-D star chart,
 * propellant gauge, ETA, current velocity (β = v/c), ΔV expended.
 *
 * Polls /api/trajectory every 2 s. Star chart redraws each tick.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type TrajectoryStateApi, type TrajectoryTarget, type AutoTickStatus, type PhaseState } from '../api/aria';

export function TrajectoryPanel() {
  const [t, setT] = useState<TrajectoryStateApi | null>(null);
  // Catalog is fetched once from /api/trajectory/targets so the dropdown
  // stays in sync with whatever the backend is willing to serve — adds
  // solar-system bodies (Moon, Mars, Jupiter…) alongside the interstellar
  // stars without hard-coding the list in the client.
  const [targets, setTargets] = useState<TrajectoryTarget[]>([]);
  const [tick, setTick] = useState<AutoTickStatus | null>(null);
  const [phase, setPhase] = useState<PhaseState | null>(null);
  const [justChangedAt, setJustChangedAt] = useState<number | null>(null);
  // NOTE: refuel-status hook MUST be declared before the early-return below,
  // otherwise React throws 'Rendered more hooks than during the previous
  // render' when the trajectory first loads.
  const [refuelStatus, setRefuelStatus] = useState<string | null>(null);

  useEffect(() => {
    const refresh = () => {
      ariaApi.trajectory().then(setT).catch(() => {});
      ariaApi.autoTickStatus().then(setTick).catch(() => {});
      ariaApi.missionPhase().then(setPhase).catch(() => {});
    };
    refresh();
    const tt = setInterval(refresh, 2000);
    return () => clearInterval(tt);
  }, []);

  useEffect(() => {
    ariaApi.trajectoryTargets().then(r => setTargets(r.targets)).catch(() => {});
  }, []);

  if (!t) return <div className="p-4 text-sm text-ui-text-dim">Loading trajectory…</div>;

  const setTarget = async (target: string) => {
    setT(await ariaApi.trajectorySetTarget(target));
    setJustChangedAt(Date.now());
  };
  const launchSim = async () => {
    try {
      if (phase?.current_phase === 'orbit' || phase?.current_phase === 'arrival') {
        await ariaApi.missionTransition('boost', true);
      }
      if (!tick?.running) {
        await ariaApi.autoTickStart(604800);
      }
      setJustChangedAt(null);
      setT(await ariaApi.trajectory());
      setTick(await ariaApi.autoTickStatus());
      setPhase(await ariaApi.missionPhase());
    } catch (e: any) {
      setRefuelStatus(`⚠ launch failed: ${String(e?.message ?? e).slice(0, 140)}`);
    }
  };
  const refuel = async () => {
    setRefuelStatus('working…');
    try {
      const r = await ariaApi.trajectoryRefuel();
      setRefuelStatus(`✓ Refuelled at ${r.target} in ${r.refuel_years.toFixed(1)} yr — ${r.method}`);
      setT(await ariaApi.trajectory());
    } catch (e: any) {
      setRefuelStatus(`⚠ ${String(e?.message ?? e).slice(0, 140)}`);
    }
  };

  const solarTargets = targets.filter(x => x.class === 'solar');
  const starTargets  = targets.filter(x => x.class === 'interstellar');
  const formatDist = (tg: TrajectoryTarget) =>
    tg.class === 'solar'
      ? (tg.distance_au < 0.1
          ? `${(tg.distance_au * 1.496e8).toFixed(0)} km`
          : `${tg.distance_au.toFixed(2)} AU`)
      : `${tg.distance_ly.toFixed(2)} ly`;

  // Position on a 0..1 scale
  const frac = t.fraction_complete;
  const SVG_W = 1000;
  const PAD = 60;
  const earthX = PAD;
  const targetX = SVG_W - PAD;
  const shipX = earthX + (targetX - earthX) * frac;

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-2 border-b border-ui-border flex items-center gap-2">
        <div className="text-[10px] uppercase tracking-wider text-ui-accent font-bold">
          Cruise Trajectory
        </div>
        <div className="ml-auto flex items-center gap-2 text-xs">
          <span className="text-[10px] text-ui-text-faint">Target:</span>
          <select value={t.target}
                  onChange={e => setTarget(e.target.value)}
                  className="px-1 py-0.5 bg-ui-bg-2 border border-ui-border rounded text-xs">
            {targets.length === 0 && <option value={t.target}>{t.target}</option>}
            {solarTargets.length > 0 && (
              <optgroup label="Solar System">
                {solarTargets.map(tg => (
                  <option key={tg.name} value={tg.name}>
                    {tg.name} — {formatDist(tg)}
                  </option>
                ))}
              </optgroup>
            )}
            {starTargets.length > 0 && (
              <optgroup label="Interstellar">
                {starTargets.map(tg => (
                  <option key={tg.name} value={tg.name}>
                    {tg.name} — {formatDist(tg)}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </div>
      </div>

      {/* Next-step callout: when the operator picked a new target but the
          sim is paused / in a non-thrusting phase, nothing visible happens.
          Tell them what to do next + give them a one-click Launch button. */}
      {(() => {
        const recentlyChanged = justChangedAt && Date.now() - justChangedAt < 120_000;
        const stalled = (!tick?.running) || phase?.current_phase === 'orbit' || phase?.current_phase === 'arrival' || phase?.current_phase === 'prelaunch';
        if (!recentlyChanged && !stalled) return null;
        const reason: string[] = [];
        if (!tick?.running) reason.push('simulation paused');
        if (phase?.current_phase === 'orbit')     reason.push('phase ORBIT (main thrust 0%)');
        if (phase?.current_phase === 'arrival')   reason.push('phase ARRIVAL (already coasting in)');
        if (phase?.current_phase === 'prelaunch') reason.push('phase PRELAUNCH (engine in standby)');
        if (reason.length === 0) return null;
        return (
          <div className="px-3 py-2 border-b border-ui-border flex items-start gap-3 bg-sev-info/10">
            <div className="flex-1 min-w-0 text-xs text-ui-text">
              <div className="font-semibold mb-0.5">
                Target set to <span className="text-ui-accent">{t.target}</span> — but the ship isn't moving yet.
              </div>
              <div className="text-[11px] text-ui-text-dim leading-relaxed">
                Why: {reason.join(' · ')}.
                {' '}To begin the new voyage, transition to <code className="text-ui-accent">BOOST</code> phase
                and start the auto-tick.
              </div>
            </div>
            <button onClick={launchSim}
                    className="px-3 py-1.5 rounded border border-sev-ok bg-sev-ok/15 text-ui-text hover:bg-sev-ok/25 text-xs font-bold whitespace-nowrap transition-colors">
              ▶ Launch voyage
            </button>
          </div>
        );
      })()}

      {/* Star chart */}
      <div className="px-3 py-4 border-b border-ui-border">
        <svg viewBox={`0 0 ${SVG_W} 200`} className="w-full">
          {/* Cruise lane */}
          <line x1={earthX} y1="100" x2={targetX} y2="100" stroke="#334155" strokeWidth="2" strokeDasharray="6 4" />

          {/* Tick marks every 10 % */}
          {[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0].map((f, i) => {
            const x = earthX + (targetX - earthX) * f;
            return <line key={i} x1={x} y1="93" x2={x} y2="107" stroke="#475569" strokeWidth="1" />;
          })}

          {/* Earth */}
          <circle cx={earthX} cy="100" r="10" fill="#3b82f6" />
          <text x={earthX} y="135" textAnchor="middle" fontSize="11" fill="#94a3b8">Earth</text>
          <text x={earthX} y="148" textAnchor="middle" fontSize="9" fill="#64748b">0 ly</text>

          {/* Target */}
          <circle cx={targetX} cy="100" r="14" fill="#f97316" />
          <text x={targetX} y="135" textAnchor="middle" fontSize="11" fill="#94a3b8">{t.target}</text>
          <text x={targetX} y="148" textAnchor="middle" fontSize="9" fill="#64748b">{formatLy(t.distance_total_ly)}</text>

          {/* Ship */}
          <g transform={`translate(${shipX}, 100)`}>
            <polygon points="0,-12 14,0 0,12 5,0" fill="#06b6d4" stroke="#0891b2" strokeWidth="1" />
          </g>
          <text x={shipX} y="60" textAnchor="middle" fontSize="11" fontWeight="700" fill="#06b6d4">ARIA</text>
          <text x={shipX} y="74" textAnchor="middle" fontSize="9" fill="#475569">{formatLy(t.position_ly)}</text>

          {/* Frac */}
          <text x={SVG_W / 2} y="180" textAnchor="middle" fontSize="11" fill="#cbd5e1">
            {(frac * 100).toFixed(2)} % complete · remaining {formatLy(t.remaining_distance_ly)}
          </text>
        </svg>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 p-3">
        <Stat label="Velocity" value={`${t.velocity_m_s.toFixed(1)} m/s`} />
        <Stat label="β = v/c"  value={t.beta.toExponential(3)} />
        <Stat label="ΔV expended" value={`${(t.cumulative_dv_m_s / 1000).toFixed(2)} km/s`} />
        <Stat label="Burn time" value={fmtDuration(t.cumulative_burn_s)} />
        <Stat
          label="Mission time"
          value={
            /* Below β = 1e-3 the Lorentz factor is < 1 ppm and ground
               and crew clocks are indistinguishable — collapse to a
               single number to keep the panel uncluttered. Once β
               exceeds threshold, show both so crew-vs-ground time
               dilation is visible at a glance. */
            t.beta > 1e-3
              ? `${t.elapsed_yr.toFixed(2)} yr ground / ${t.proper_elapsed_yr.toFixed(2)} yr crew`
              : `${t.elapsed_yr.toFixed(2)} yr`
          }
        />
        <Stat label="ETA"      value={
          t.eta_yr == null ? '∞'
          : t.eta_yr <= 0 ? 'Arrived'
          : t.eta_yr < 1 ? `${Math.round(t.eta_yr * 365)} d`
          : `${t.eta_yr.toFixed(2)} yr`
        } />
        <Stat label="Thrust" value={`${(t.config.nominal_thrust_n / 1000).toFixed(0)} kN`} />
        <Stat label="Isp"    value={`${t.config.isp_s.toLocaleString()} s`} />
      </div>

      {/* Propellant bar */}
      <div className="px-3 pb-3">
        <div className="flex justify-between text-[11px] mb-1">
          <span className="text-ui-text-dim">Propellant remaining</span>
          <span className="font-mono text-ui-text">
            {(t.propellant_remaining_kg / 1e6).toFixed(2)} / {(t.config.propellant_mass_kg / 1e6).toFixed(0)} kt
            ({(t.propellant_fraction_remaining * 100).toFixed(2)} %)
          </span>
        </div>
        <div className="h-3 bg-ui-bg-2 rounded overflow-hidden border border-ui-border">
          <div className={`h-full transition-all ${
                t.propellant_fraction_remaining > 0.5 ? 'bg-sev-ok'
              : t.propellant_fraction_remaining > 0.2 ? 'bg-sev-warn'
              :                                          'bg-sev-crit'}`}
               style={{ width: `${t.propellant_fraction_remaining * 100}%` }} />
        </div>
      </div>

      {/* ISRU refuel — only meaningful once we're parked at a body */}
      <div className="px-3 pb-3 border-t border-ui-border pt-2">
        <div className="flex items-baseline gap-2">
          <div className="text-[10px] uppercase tracking-wide text-ui-accent font-bold">
            ISRU refuelling
          </div>
          <button onClick={refuel}
                  className="ml-auto px-2 py-1 text-[10px] rounded border border-sev-ok bg-sev-ok/40 hover:bg-sev-ok/60 text-sev-ok">
            🛢 Refuel from target
          </button>
        </div>
        <div className="text-[10px] text-ui-text-dim italic mt-1">
          Only active in ARRIVAL / ORBIT phase. Advances mission clock by
          the body-specific mining duration (Moon 0.3 yr, Mars 1.0 yr,
          Titan 2.0 yr, Uranus 3.0 yr — lunar-LCROSS-style H₂O
          electrolysis → LH₂). Restores propellant to 100 % for the next leg.
        </div>
        {refuelStatus && (
          <div className={`mt-1 text-[10px] font-mono ${
            refuelStatus.startsWith('⚠') ? 'text-sev-crit' :
            refuelStatus.startsWith('✓') ? 'text-sev-ok' : 'text-ui-text-dim'
          }`}>
            {refuelStatus}
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-ui-bg-1/60 rounded border border-ui-border px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wide text-ui-text-faint">{label}</div>
      <div className="font-mono text-sm text-ui-text">{value}</div>
    </div>
  );
}

function fmtDuration(s: number): string {
  if (s < 60)        return `${s.toFixed(0)} s`;
  if (s < 3600)      return `${(s / 60).toFixed(0)} min`;
  if (s < 86400)     return `${(s / 3600).toFixed(1)} hr`;
  if (s < 31_557_600) return `${(s / 86400).toFixed(1)} d`;
  return `${(s / 31_557_600).toFixed(2)} yr`;
}

// Solar-system distances are ~1e-8..1e-4 ly — display in km / AU so the
// Moon isn't rendered as "0.00 ly".
function formatLy(ly: number): string {
  const AU_PER_LY = 63241.077;
  const KM_PER_LY = 9.4607e12;
  if (ly < 1e-6)   return `${(ly * KM_PER_LY).toLocaleString(undefined, { maximumFractionDigits: 0 })} km`;
  if (ly < 1e-2)   return `${(ly * AU_PER_LY).toFixed(2)} AU`;
  return `${ly.toFixed(ly < 1 ? 4 : 2)} ly`;
}
