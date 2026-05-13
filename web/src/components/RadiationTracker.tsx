/**
 * Radiation Dose Tracker — crew dose vs NASA career limits.
 *
 * Shows cumulative radiation dose from GCR + SPE with annual breakdown,
 * compared against NASA-STD-3001 career dose limits (1000 mSv career,
 * 500 mSv/yr, 250 mSv/30-day). Uses data from /api/crew/health and
 * calculates dose from elapsed mission time × GCR flux.
 *
 * GCR baseline: 420 mSv/yr at solar minimum behind 20 g/cm² shielding
 * (Cucinotta 2014 NASA/TP-2013-217375).
 */

import { useEffect, useState } from 'react';
import { ariaApi, type CrewHealth } from '../api/aria';

// NASA-STD-3001 Vol 1 Rev C Table 6 — career dose limits
const LIMITS = {
  career_msv: 1000,      // 1 Sv career total
  annual_msv: 500,       // 500 mSv/yr
  thirtyDay_msv: 250,    // 250 mSv/30-day
};

// GCR dose rate behind typical shielding
// (Cucinotta 2014 NASA/TP-2013-217375, solar minimum at 20 g/cm² Al-eq)
const GCR_DOSE_RATE_MSV_YR_BASELINE = 420;
const SHIELDING_BASELINE_G_CM2 = 20;

/** Empirical shielding attenuation: dose falls roughly as exp(-k * Δx)
 *  where k ≈ 0.015/(g/cm²) for GCR at interplanetary energies
 *  (Cucinotta 2014, Fig. 8 — dose ratio vs. aluminum depth, curve for
 *  solar minimum).  20 g/cm² is the baseline; each extra 10 g/cm²
 *  buys ~14 % additional reduction.  Saturates near 60 g/cm² (past
 *  that, secondary showers start dominating and adding shield is
 *  counter-productive — not modelled here; we just clamp). */
function gcrDoseRate(shieldingGCm2: number): number {
  const delta = Math.max(0, shieldingGCm2 - SHIELDING_BASELINE_G_CM2);
  const clampedDelta = Math.min(delta, 60);   // avoid unphysical reductions
  return GCR_DOSE_RATE_MSV_YR_BASELINE * Math.exp(-0.015 * clampedDelta);
}

const SHIELD_PRESETS: { name: string; gCm2: number; note: string }[] = [
  { name: 'Baseline',     gCm2: 20,  note: '7-layer Al-eq (current)' },
  { name: '+ water wall', gCm2: 30,  note: '10 g/cm² water shielding' },
  { name: '+ polyethylene', gCm2: 40, note: 'lunar regolith lining' },
  { name: 'Heavy',        gCm2: 60,  note: 'deep-space long-duration' },
];

export function RadiationTracker() {
  const [crew, setCrew] = useState<CrewHealth | null>(null);
  const [shielding, setShielding] = useState(SHIELDING_BASELINE_G_CM2);

  useEffect(() => {
    const refresh = () => ariaApi.crewHealth().then(setCrew).catch(() => {});
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);

  if (!crew) return <div className="p-4 text-sm text-ui-text-dim">Loading radiation data...</div>;

  const elapsed_yr = crew.elapsed_yr;
  const GCR_DOSE_RATE_MSV_YR = gcrDoseRate(shielding);
  const baselineRate = GCR_DOSE_RATE_MSV_YR_BASELINE;
  const cumulative_msv = GCR_DOSE_RATE_MSV_YR * elapsed_yr;
  const annual_msv = GCR_DOSE_RATE_MSV_YR;
  const thirtyDay_msv = GCR_DOSE_RATE_MSV_YR * (30 / 365.25);
  const reduction_pct = (1 - GCR_DOSE_RATE_MSV_YR / baselineRate) * 100;

  const career_pct = (cumulative_msv / LIMITS.career_msv) * 100;
  const annual_pct = (annual_msv / LIMITS.annual_msv) * 100;
  const thirtyDay_pct = (thirtyDay_msv / LIMITS.thirtyDay_msv) * 100;

  // Annual dose breakdown for bar chart (up to 10 years)
  const maxYears = Math.min(Math.ceil(elapsed_yr), 50);
  const annualBars: { year: number; dose: number }[] = [];
  for (let y = 0; y < maxYears; y++) {
    const frac = y + 1 <= elapsed_yr ? 1 : Math.max(0, elapsed_yr - y);
    annualBars.push({ year: y + 1, dose: GCR_DOSE_RATE_MSV_YR * frac });
  }

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Radiation Dose Tracker</h2>
        <p className="text-xs text-ui-text-dim">
          Cumulative GCR dose: {cumulative_msv.toFixed(0)} mSv after {elapsed_yr.toFixed(2)} yr.
          Behind {shielding} g/cm² Al-equivalent shielding ({GCR_DOSE_RATE_MSV_YR.toFixed(0)} mSv/yr —
          {reduction_pct >= 1
            ? <> <span className="text-sev-ok">{reduction_pct.toFixed(0)} % below</span> 20 g/cm² baseline</>
            : ' at 20 g/cm² baseline'}).
        </p>
      </div>

      {/* Shielding what-if — slider + preset buttons, all client-side.
          Lets mission planners see how an extra water wall or regolith
          liner would affect career dose and career-limit utilisation
          without running a backend sim. */}
      <div className="mb-3 bg-ui-bg-1/60 border border-ui-border rounded p-3">
        <div className="flex items-center justify-between mb-2">
          <div className="text-sm font-semibold text-sev-warn">Shielding what-if</div>
          <div className="text-[10px] text-ui-text-faint">Cucinotta 2014 exp(-0.015 · Δ g/cm²)</div>
        </div>
        <div className="flex flex-wrap gap-1 mb-2 text-[11px]">
          {SHIELD_PRESETS.map((p) => (
            <button key={p.name}
                    onClick={() => setShielding(p.gCm2)}
                    className={`px-2 py-0.5 rounded border
                      ${shielding === p.gCm2
                        ? 'border-ui-accent bg-ui-accent/40 text-ui-accent'
                        : 'border-ui-border bg-ui-bg-1 text-ui-text hover:border-ui-accent'}`}
                    title={`${p.gCm2} g/cm² — ${p.note}`}>
              {p.name}
              <span className="text-ui-text-dim ml-1">{p.gCm2}g/cm²</span>
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-ui-text-dim">Shielding:</span>
          <input type="range" min={5} max={80} step={1}
                 value={shielding}
                 onChange={(e) => setShielding(Number(e.target.value))}
                 className="flex-1" />
          <span className="text-ui-text font-mono w-16 text-right">{shielding} g/cm²</span>
        </div>
      </div>

      {/* Dose limit gauges */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        <DoseGauge
          label="Career Dose"
          current={cumulative_msv}
          limit={LIMITS.career_msv}
          unit="mSv"
          sublabel="NASA-STD-3001 lifetime limit"
        />
        <DoseGauge
          label="Annual Dose"
          current={annual_msv}
          limit={LIMITS.annual_msv}
          unit="mSv/yr"
          sublabel="Blood-forming organ limit"
        />
        <DoseGauge
          label="30-Day Dose"
          current={thirtyDay_msv}
          limit={LIMITS.thirtyDay_msv}
          unit="mSv/30d"
          sublabel="Acute exposure limit"
        />
      </div>

      {/* Annual breakdown bar chart */}
      <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-3">
        <div className="text-[10px] uppercase tracking-wider text-ui-text-faint mb-2">
          Annual Dose Breakdown (mSv/yr)
        </div>
        {annualBars.length === 0 ? (
          <div className="flex items-center justify-center text-ui-text-faint text-xs min-h-[120px]">
            No annual dose data yet — chart populates after the first mission year.
          </div>
        ) : (
          <div className="flex items-end gap-1 h-32 min-h-[120px]">
            {annualBars.slice(-20).map(bar => {
              const pct = (bar.dose / LIMITS.annual_msv) * 100;
              const overLimit = bar.dose > LIMITS.annual_msv;
              return (
                <div key={bar.year} className="flex-1 flex flex-col items-center justify-end" title={`Year ${bar.year}: ${bar.dose.toFixed(0)} mSv`}>
                  <div
                    className={`w-full rounded-t ${overLimit ? 'bg-sev-crit' : 'bg-ui-accent'}`}
                    style={{ height: `max(4px, ${Math.min(pct, 100)}%)` }}
                  />
                  {annualBars.length <= 20 && (
                    <div className="text-[7px] text-ui-text-faint mt-0.5">{bar.year}</div>
                  )}
                </div>
              );
            })}
          </div>
        )}
        {annualBars.length > 0 && (
          <div className="relative h-0 -mt-32 pointer-events-none">
            <div className="absolute w-full border-t border-dashed border-sev-crit/60" style={{ top: '0%' }} />
          </div>
        )}
        <div className="text-[9px] text-ui-text-faint mt-1">
          Red dashed line = 500 mSv/yr NASA limit. Showing last {Math.min(annualBars.length, 20)} years.
        </div>
      </div>

      {/* Risk summary */}
      <div className="mt-3 grid grid-cols-2 gap-2 text-[10px]">
        <div className="bg-ui-bg-1/60 border border-ui-border rounded p-2">
          <div className="text-ui-text-faint uppercase tracking-wider mb-1">Shielding</div>
          <div className="text-ui-text">{shielding} g/cm² Al-equivalent</div>
          <div className="text-ui-text-dim">
            {reduction_pct >= 1
              ? <>{reduction_pct.toFixed(0)} % below baseline · saves {(baselineRate - GCR_DOSE_RATE_MSV_YR).toFixed(0)} mSv/yr</>
              : 'at baseline Cucinotta 2014 curve'}
          </div>
        </div>
        <div className="bg-ui-bg-1/60 border border-ui-border rounded p-2">
          <div className="text-ui-text-faint uppercase tracking-wider mb-1">Risk Assessment</div>
          <div className={career_pct > 80 ? 'text-sev-crit' : career_pct > 50 ? 'text-sev-warn' : 'text-sev-ok'}>
            {career_pct < 50 ? 'LOW RISK' : career_pct < 80 ? 'MODERATE RISK' : 'HIGH RISK'}
          </div>
          <div className="text-ui-text-dim">
            {career_pct.toFixed(0)}% of career limit used after {elapsed_yr.toFixed(1)} yr
          </div>
        </div>
      </div>
    </div>
  );
}

function DoseGauge({
  label, current, limit, unit, sublabel,
}: {
  label: string; current: number; limit: number; unit: string; sublabel: string;
}) {
  // R65-R5 (2026-04-24): guard `limit=0` — previously 0/0 → NaN → bar
  // rendered with `NaN%` width (invisible).  Also clamp negatives to 0.
  const pct = limit > 0 ? Math.max(0, Math.min((current / limit) * 100, 100)) : 0;
  const color = pct > 80 ? 'bg-sev-crit' : pct > 50 ? 'bg-sev-warn' : 'bg-sev-ok';
  const textColor = pct > 80 ? 'text-sev-crit' : pct > 50 ? 'text-sev-warn' : 'text-sev-ok';

  return (
    <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-3">
      <div className="text-[9px] uppercase tracking-wider text-ui-text-faint mb-1">{label}</div>
      <div className="flex items-baseline gap-1 mb-2">
        <span className={`text-2xl font-bold font-mono ${textColor}`}>
          {current >= 1000 ? (current / 1000).toFixed(2) : current.toFixed(0)}
        </span>
        <span className="text-xs text-ui-text-dim">
          {current >= 1000 ? 'Sv' : unit} / {limit >= 1000 ? `${limit / 1000} Sv` : `${limit} mSv`}
        </span>
      </div>
      <div className="h-2 bg-ui-bg-2 rounded-full overflow-hidden">
        <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <div className="text-[8px] text-ui-text-faint mt-1">{sublabel}</div>
    </div>
  );
}
