/**
 * Space Weather Panel — current solar/geomagnetic state and ops advisories.
 *
 * Mirrors aria.physics.gravity.space_weather. Inputs: F10.7 solar flux, Kp
 * geomagnetic index, optional flare class and CME speed. Outputs:
 *   - NOAA G-scale storm classification (Bartels 1939 Kp definition)
 *   - Drag density multiplier vs. quiet baseline
 *   - CME arrival ETA (Gopalswamy 2001 drag model)
 *   - Live ops advisory list (charging risk, EVA defer, HF blackout)
 *
 * Uses canned solar-cycle phase predictor for "what should F10.7 be today?"
 * (Tapping 2013).
 */

import { useMemo, useState } from 'react';

// Bartels 1939 Kp→ap lookup, snapped to Kp± levels (third-of-unit).
const KP_TO_AP: Record<number, number> = {
  0.0: 0, 0.33: 2, 0.67: 3, 1.0: 4, 1.33: 5, 1.67: 6,
  2.0: 7, 2.33: 9, 2.67: 12, 3.0: 15, 3.33: 18, 3.67: 22,
  4.0: 27, 4.33: 32, 4.67: 39, 5.0: 48, 5.33: 56, 5.67: 67,
  6.0: 80, 6.33: 94, 6.67: 111, 7.0: 132, 7.33: 154, 7.67: 179,
  8.0: 207, 8.33: 236, 8.67: 300, 9.0: 400,
};

function kpToAp(kp: number): number {
  const snapped = Math.round(kp * 3) / 3;
  return KP_TO_AP[snapped] ?? 27;
}

function classifyStorm(kp: number): { code: string; color: string } {
  if (kp < 5) return { code: 'quiet', color: 'text-sev-ok' };
  if (kp < 6) return { code: 'G1 minor', color: 'text-sev-warn' };
  if (kp < 7) return { code: 'G2 moderate', color: 'text-sev-warn' };
  if (kp < 8) return { code: 'G3 strong', color: 'text-sev-warn' };
  if (kp < 9) return { code: 'G4 severe', color: 'text-sev-crit' };
  return { code: 'G5 extreme', color: 'text-sev-crit' };
}

function classifySep(pfu: number): { code: string; color: string } {
  if (pfu < 10) return { code: 'quiet', color: 'text-sev-ok' };
  if (pfu < 100) return { code: 'S1 minor', color: 'text-sev-warn' };
  if (pfu < 1000) return { code: 'S2 moderate', color: 'text-sev-warn' };
  if (pfu < 10000) return { code: 'S3 strong', color: 'text-sev-warn' };
  if (pfu < 100000) return { code: 'S4 severe', color: 'text-sev-crit' };
  return { code: 'S5 extreme', color: 'text-sev-crit' };
}

function classifyCme(speedKmS: number): string {
  if (speedKmS < 500) return 'slow';
  if (speedKmS < 1000) return 'moderate';
  if (speedKmS < 2000) return 'fast';
  return 'extreme';
}

function cmeArrivalHours(speedKmS: number, distAu = 1.0): number {
  if (speedKmS <= 0) return Infinity;
  const vSolarWind = 400; // ambient solar wind, km/s
  const vAvg = 0.5 * (speedKmS + vSolarWind);
  const distKm = distAu * 1.496e8;
  return distKm / vAvg / 3600;
}

function f107ByCyclePhase(yrsSinceMin: number): number {
  // Tapping 2013: solar cycle ~11 yr, sinusoidal F10.7 from ~70 to ~200 sfu.
  const fMin = 70, fMax = 200;
  const phase = (yrsSinceMin / 11.0) * 2 * Math.PI;
  return fMin + 0.5 * (fMax - fMin) * (1 - Math.cos(phase));
}

function dragMultiplier(f107: number, kp: number): number {
  const fFactor = Math.pow(f107 / 150, 1.5);
  const ap = kpToAp(kp);
  const aFactor = Math.exp(0.005 * Math.max(ap - 10, 0));
  return fFactor * aFactor;
}

export function SpaceWeatherPanel() {
  const [f107, setF107] = useState(120);
  const [kp, setKp] = useState(3.0);
  const [flareFlux, setFlareFlux] = useState(1e-6); // C1
  const [cmeSpeed, setCmeSpeed] = useState(0);
  const [sepFlux, setSepFlux] = useState(0);
  const [yrsSinceMin, setYrsSinceMin] = useState(2.0);

  const storm = classifyStorm(kp);
  const ap = kpToAp(kp);
  const drag = dragMultiplier(f107, kp);
  const sep = classifySep(sepFlux);
  const cmeEta = cmeSpeed > 0 ? cmeArrivalHours(cmeSpeed) : null;
  const cmeClass = cmeSpeed > 0 ? classifyCme(cmeSpeed) : null;
  const cycleF107 = f107ByCyclePhase(yrsSinceMin);

  const flareClass = useMemo(() => {
    if (flareFlux < 1e-7) return { letter: 'A', mult: flareFlux / 1e-8 };
    if (flareFlux < 1e-6) return { letter: 'B', mult: flareFlux / 1e-7 };
    if (flareFlux < 1e-5) return { letter: 'C', mult: flareFlux / 1e-6 };
    if (flareFlux < 1e-4) return { letter: 'M', mult: flareFlux / 1e-5 };
    return { letter: 'X', mult: flareFlux / 1e-4 };
  }, [flareFlux]);

  const advisories: string[] = [];
  if (storm.code !== 'quiet') {
    advisories.push(`Geomagnetic storm in progress: ${storm.code}; monitor surface charging on dielectrics.`);
  }
  if (f107 > 200) {
    advisories.push(`High solar flux (F10.7=${f107.toFixed(0)} sfu): expect ${(drag * 100 - 100).toFixed(0)}% above-baseline LEO drag.`);
  }
  if (sepFlux >= 10) {
    advisories.push(`SEP event ${sep.code}: defer EVA, retreat crew to shielded zone.`);
  }
  if (flareClass.letter === 'X') {
    advisories.push(`X-class flare active: HF comms blackout on dayside, GPS degraded.`);
  }
  if (cmeSpeed >= 1000) {
    advisories.push(`Earth-directed CME (${cmeClass}): expect Kp jump in ~${cmeEta?.toFixed(0)}h; pre-position safe-mode.`);
  }
  if (advisories.length === 0) {
    advisories.push('All clear — nominal space environment.');
  }

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3 flex items-start gap-3">
        <div className="flex-1">
          <h2 className="text-lg font-semibold text-ui-accent">Space Weather State</h2>
          <p className="text-xs text-ui-text-dim">
            NOAA G/S scales · F10.7 drag forcing · CME arrival (Gopalswamy 2001)
          </p>
        </div>
        {/* Headline badge — immediately tells the operator whether
            they should be worried without reading the tables. */}
        <div className={`px-4 py-2 rounded border ${
          storm.code === 'quiet'
            ? 'border-sev-ok bg-sev-ok/30 text-sev-ok'
            : kp >= 7
              ? 'border-sev-crit bg-sev-crit/40 text-sev-crit animate-pulse'
              : 'border-sev-warn bg-sev-warn/30 text-sev-warn'
        }`}>
          <div className="text-[10px] uppercase tracking-wider opacity-70">Storm class</div>
          <div className={`text-lg font-bold ${storm.color}`}>{storm.code.toUpperCase()}</div>
          <div className="text-[10px] font-mono">ap = {ap} · drag × {drag.toFixed(2)}</div>
        </div>
      </div>

      {/* Preset scenarios — one-click jumps to illustrative space-weather
          states, for testing response + demonstration.  All values
          sourced from historical events or NOAA climatology. */}
      <div className="mb-3 flex flex-wrap gap-1 text-[11px]">
        <span className="text-ui-text-faint uppercase tracking-wider self-center mr-1">Presets:</span>
        {PRESETS.map((p) => (
          <button key={p.name}
                  onClick={() => {
                    setF107(p.f107); setKp(p.kp); setFlareFlux(p.flareFlux);
                    setCmeSpeed(p.cmeSpeed); setSepFlux(p.sepFlux);
                    setYrsSinceMin(p.yrsSinceMin);
                  }}
                  className="px-2 py-0.5 rounded border border-ui-border bg-ui-bg-1
                             hover:border-ui-accent hover:bg-ui-bg-2 text-ui-text">
            {p.name}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-4">
        <Slider label="F10.7 (sfu)" value={f107} onChange={setF107} min={60} max={300} step={5} />
        <Slider label="Kp index" value={kp} onChange={setKp} min={0} max={9} step={0.33} />
        <Slider label="Years since solar min" value={yrsSinceMin} onChange={setYrsSinceMin} min={0} max={11} step={0.5} />
        <NumIn label="Flare X-ray flux (W/m²)" value={flareFlux} onChange={setFlareFlux} step={1e-7} />
        <NumIn label="CME initial speed (km/s)" value={cmeSpeed} onChange={setCmeSpeed} step={50} />
        <NumIn label="SEP >10 MeV flux (pfu)" value={sepFlux} onChange={setSepFlux} step={10} />
      </div>

      {/* Solar-cycle context chart — shows where the current
          "yrsSinceMin" sits within a full 11-year sinusoid, and marks
          the operator's current F10.7 against it.  Helps a reader who
          isn't up on cycle phase see at a glance "we're near max" or
          "deep minimum + high F10.7 means something anomalous". */}
      <div className="mb-4 bg-ui-bg-1/60 border border-ui-border rounded p-3">
        <div className="flex items-center justify-between mb-1">
          <div className="text-sm font-semibold text-sev-warn">Solar-cycle phase</div>
          <div className="text-[10px] text-ui-text-faint">Tapping 2013 · 11-yr sinusoid</div>
        </div>
        <SolarCycleChart currentYrsSinceMin={yrsSinceMin} currentF107={f107} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
          <h3 className="text-sm font-semibold text-ui-accent mb-2">Geomagnetic</h3>
          <Row label="Kp" value={kp.toFixed(2)} />
          <Row label="ap" value={ap.toFixed(0)} />
          <Row label="Storm class" value={storm.code} valueClass={storm.color} />
        </div>

        <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
          <h3 className="text-sm font-semibold text-sev-warn mb-2">Solar Activity</h3>
          <Row label="F10.7" value={`${f107.toFixed(0)} sfu`} />
          <Row label="Cycle-phase F10.7" value={`${cycleF107.toFixed(0)} sfu`} />
          <Row label="Flare class" value={`${flareClass.letter}${flareClass.mult.toFixed(1)}`} />
        </div>

        <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
          <h3 className="text-sm font-semibold text-sev-warn mb-2">Drag Forcing</h3>
          <Row label="Density × baseline" value={`${drag.toFixed(2)}×`} />
          <Row label="Lifetime impact" value={drag > 1.5 ? 'shortened' : drag < 0.7 ? 'extended' : 'nominal'} />
          <div className="mt-2 text-[11px] text-ui-text-dim">
            Multiplier vs. F10.7=150 sfu, ap≤10 quiet baseline.
          </div>
        </div>

        <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
          <h3 className="text-sm font-semibold text-sev-crit mb-2">Energetic Particles</h3>
          <Row label="SEP class" value={sep.code} valueClass={sep.color} />
          {cmeEta !== null && (
            <>
              <Row label="CME class" value={cmeClass!} />
              <Row label="CME ETA" value={`${cmeEta.toFixed(1)} h`} />
            </>
          )}
        </div>
      </div>

      <div className="mt-4 bg-ui-bg-1/60 border border-ui-border rounded p-3">
        <h3 className="text-sm font-semibold text-sev-ok mb-2">Operations Advisory</h3>
        <ul className="space-y-1 text-xs text-ui-text">
          {advisories.map((a, i) => (
            <li key={i} className="before:content-['•'] before:text-ui-accent before:mr-2">
              {a}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function Slider({
  label, value, onChange, min, max, step,
}: {
  label: string; value: number; onChange: (v: number) => void;
  min: number; max: number; step: number;
}) {
  return (
    <label className="flex flex-col text-xs">
      <span className="text-ui-text-dim">
        {label}: <span className="text-ui-text font-mono">{value.toFixed(2)}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full"
      />
    </label>
  );
}

function NumIn({
  label, value, onChange, step,
}: {
  label: string; value: number; onChange: (v: number) => void; step: number;
}) {
  return (
    <label className="flex flex-col text-xs">
      <span className="text-ui-text-dim">{label}</span>
      <input
        type="number"
        value={value}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text"
      />
    </label>
  );
}

function Row({
  label, value, valueClass,
}: {
  label: string; value: string; valueClass?: string;
}) {
  return (
    <div className="flex justify-between text-xs py-0.5">
      <span className="text-ui-text-dim">{label}:</span>
      <span className={`font-mono ${valueClass ?? 'text-ui-text'}`}>{value}</span>
    </div>
  );
}

/** Inline SVG of the 11-year F10.7 sinusoid with the current phase +
 *  operator's F10.7 marked.  Pure SVG, no deps. */
function SolarCycleChart({
  currentYrsSinceMin, currentF107,
}: { currentYrsSinceMin: number; currentF107: number }) {
  const W = 520, H = 80, padL = 24, padR = 8, padT = 6, padB = 16;
  const yrs = 11;
  const f107Min = 60, f107Max = 240;
  const xOf = (y: number) => padL + (y / yrs) * (W - padL - padR);
  const yOf = (f: number) => H - padB - ((f - f107Min) / (f107Max - f107Min)) * (H - padT - padB);
  const steps = 88;
  let path = '';
  for (let i = 0; i <= steps; i++) {
    const y = (i / steps) * yrs;
    const f = f107ByCyclePhase(y);
    path += `${i === 0 ? 'M' : 'L'}${xOf(y).toFixed(1)} ${yOf(f).toFixed(1)} `;
  }
  const opF = f107ByCyclePhase(currentYrsSinceMin);
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} className="block">
      {/* horizontal grid */}
      {[f107Min, 120, 180, f107Max].map((v) => (
        <line key={v} x1={padL} x2={W - padR} y1={yOf(v)} y2={yOf(v)}
              stroke="#1e293b" strokeWidth={0.5} />
      ))}
      <text x={4} y={yOf(f107Min) + 3} fontSize={8} fill="#64748b">60</text>
      <text x={4} y={yOf(240) + 3}     fontSize={8} fill="#64748b">240</text>
      {/* cycle curve */}
      <path d={path} stroke="#fbbf24" strokeWidth={1.3} fill="none" />
      {/* expected F10.7 at this phase */}
      <circle cx={xOf(currentYrsSinceMin)} cy={yOf(opF)} r={3.5}
              fill="#fbbf24" />
      {/* operator's actual F10.7 — offset horizontally to make both dots visible */}
      <circle cx={xOf(currentYrsSinceMin)} cy={yOf(currentF107)} r={4}
              fill="#22d3ee" stroke="#0f172a" strokeWidth={1} />
      {/* year ticks */}
      {Array.from({ length: yrs + 1 }, (_, i) => (
        <text key={i} x={xOf(i)} y={H - 2} fontSize={8} fill="#64748b" textAnchor="middle">
          {i === 0 ? 'min' : i === 11 ? 'next min' : i}
        </text>
      ))}
      {/* legend */}
      <text x={W - 110} y={12} fontSize={9} fill="#fbbf24">● expected</text>
      <text x={W - 55}  y={12} fontSize={9} fill="#22d3ee">● actual</text>
    </svg>
  );
}

/** Scenario presets keyed to historical / climatological references.
 *  Not exhaustive — just a scaffolding to jump the sliders to a few
 *  useful states without hand-typing six numbers. */
const PRESETS: {
  name: string; f107: number; kp: number; flareFlux: number;
  cmeSpeed: number; sepFlux: number; yrsSinceMin: number;
}[] = [
  { name: 'Quiet',        f107: 75,  kp: 1.0, flareFlux: 1e-8, cmeSpeed: 0,    sepFlux: 0,     yrsSinceMin: 0.5 },
  { name: 'Nominal',      f107: 120, kp: 3.0, flareFlux: 1e-7, cmeSpeed: 0,    sepFlux: 0,     yrsSinceMin: 3 },
  { name: 'Solar max',    f107: 195, kp: 4.0, flareFlux: 1e-6, cmeSpeed: 400,  sepFlux: 0,     yrsSinceMin: 5.5 },
  { name: 'G3 storm',     f107: 160, kp: 6.5, flareFlux: 5e-6, cmeSpeed: 1100, sepFlux: 30,    yrsSinceMin: 5 },
  { name: 'X-class flare',f107: 180, kp: 5.0, flareFlux: 1e-4, cmeSpeed: 1500, sepFlux: 150,   yrsSinceMin: 5 },
  { name: 'Carrington',   f107: 220, kp: 9.0, flareFlux: 4e-3, cmeSpeed: 2500, sepFlux: 25000, yrsSinceMin: 5.5 },
];
