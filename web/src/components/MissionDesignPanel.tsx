/**
 * Mission Design Panel — end-to-end interplanetary mission planning.
 *
 * Uses the mission_design backend to:
 * 1. Generate porkchop plot over departure × arrival window
 * 2. Find optimal C3 window
 * 3. Compute Lambert transfer Δv
 * 4. Check fuel feasibility with Tsiolkovsky
 *
 * Visualizes:
 * - C3 contour plot (departure vs arrival days)
 * - Summary of optimal window (Δv, TOF, fuel required)
 * - Feasibility verdict
 */

import { useState, useRef, useEffect } from 'react';

interface MissionDesignResult {
  route: string;
  departure_day: number;
  arrival_day: number;
  time_of_flight_days: number;
  c3_km2_s2: number;
  v_infinity_arrival_km_s: number;
  departure_dv_ms: number;
  arrival_dv_ms: number;
  total_dv_ms: number;
  dry_mass_kg: number;
  fuel_required_kg: number;
  feasible: boolean;
}

export function MissionDesignPanel() {
  const [dryMass, setDryMass] = useState(3000);
  const [fuelBudget, setFuelBudget] = useState(6000);
  const [isp, setIsp] = useState(320);
  const [depStart, setDepStart] = useState(0);
  const [depEnd, setDepEnd] = useState(400);
  const [arrStart, setArrStart] = useState(150);
  const [arrEnd, setArrEnd] = useState(600);
  const [result, setResult] = useState<MissionDesignResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runDesign = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        dry_mass_kg: String(dryMass),
        fuel_budget_kg: String(fuelBudget),
        isp_s: String(isp),
        dep_start: String(depStart),
        dep_end: String(depEnd),
        arr_start: String(arrStart),
        arr_end: String(arrEnd),
      });
      const resp = await fetch(`/api/mission_design/earth_mars?${params}`);
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setResult(data);
    } catch (e: any) {
      setError(e.message || 'Design failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Mission Design — Earth → Mars</h2>
        <p className="text-xs text-ui-text-dim">
          Porkchop optimization + Izzo Lambert + Tsiolkovsky fuel sizing
        </p>
      </div>

      {/* Parameters */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4">
        <InputField label="Dry mass (kg)" value={dryMass} onChange={setDryMass} />
        <InputField label="Fuel budget (kg)" value={fuelBudget} onChange={setFuelBudget} />
        <InputField label="Isp (s)" value={isp} onChange={setIsp} />
        <InputField label="Dep start (day)" value={depStart} onChange={setDepStart} />
        <InputField label="Dep end (day)" value={depEnd} onChange={setDepEnd} />
        <InputField label="Arr start (day)" value={arrStart} onChange={setArrStart} />
        <InputField label="Arr end (day)" value={arrEnd} onChange={setArrEnd} />
      </div>

      <button
        onClick={runDesign}
        disabled={loading}
        className="mb-4 px-4 py-2 bg-ui-accent/40 hover:bg-ui-accent-strong disabled:bg-ui-bg-3 text-white rounded text-sm"
      >
        {loading ? 'Computing...' : 'Run Mission Design'}
      </button>

      {error && (
        <div className="mb-4 p-3 bg-sev-crit/40 border border-sev-crit rounded text-sev-crit text-xs">
          Error: {error}
        </div>
      )}

      {result && (
        <div className="space-y-3">
          <div
            className={`p-3 border rounded ${
              result.feasible
                ? 'bg-sev-ok/30 border-sev-ok'
                : 'bg-sev-crit/30 border-sev-crit'
            }`}
          >
            <h3 className="font-semibold text-sm mb-2">
              {result.feasible ? '✓ FEASIBLE' : '✗ INFEASIBLE (insufficient fuel)'}
            </h3>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-ui-text">
              <Stat label="Route" value={result.route} />
              <Stat label="Departure day" value={result.departure_day} />
              <Stat label="Arrival day" value={result.arrival_day} />
              <Stat label="Time of flight" value={`${result.time_of_flight_days} days`} />
              <Stat label="C3" value={`${result.c3_km2_s2} km²/s²`} />
              <Stat
                label="v∞ at arrival"
                value={`${result.v_infinity_arrival_km_s} km/s`}
              />
              <Stat
                label="Departure Δv"
                value={`${result.departure_dv_ms.toFixed(0)} m/s`}
              />
              <Stat
                label="Arrival Δv"
                value={`${result.arrival_dv_ms.toFixed(0)} m/s`}
              />
              <Stat
                label="Total Δv"
                value={`${result.total_dv_ms.toFixed(0)} m/s`}
              />
              <Stat
                label="Fuel required"
                value={`${result.fuel_required_kg.toFixed(0)} kg`}
              />
            </div>
          </div>

          <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
            <div className="text-[11px] text-ui-text">
              <p className="mb-1 font-semibold">Interpretation:</p>
              <ul className="list-disc pl-4 space-y-1 text-ui-text-dim">
                <li>
                  C3 is departure hyperbolic excess energy — directly relates to
                  launch vehicle capability. Falcon 9 can launch ~4000 kg to C3=10;
                  Falcon Heavy to C3=60.
                </li>
                <li>
                  v∞ at arrival determines orbit insertion Δv — higher v∞ means
                  more propellant to capture into Mars orbit.
                </li>
                <li>
                  For chemical propulsion (Isp~320), total Δv up to ~6 km/s is
                  practical. Above that, electric propulsion (Isp~3000+) is
                  needed.
                </li>
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function InputField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex flex-col text-xs">
      <span className="text-ui-text-dim">{label}</span>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text"
      />
    </label>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <>
      <span className="text-ui-text-dim">{label}:</span>
      <span className="font-mono">{value}</span>
    </>
  );
}
