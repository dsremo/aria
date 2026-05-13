/**
 * Subsystem Sizing Panel — SMAD first-order sizing calculators.
 *
 * Computes radiator area, solar array size, battery capacity, RCS
 * propellant, and on-board storage given payload requirements.
 * Client-side compute using SMAD formulas.
 */

import { useState } from 'react';

interface RadiatorResult {
  area_m2: number;
  mass_kg: number;
}

interface SolarResult {
  area_m2: number;
  bol_power_w: number;
  mass_kg: number;
}

interface BatteryResult {
  capacity_wh: number;
  mass_kg: number;
}

interface RCSResult {
  propellant_kg: number;
  total_dv_ms: number;
}

export function SubsystemSizingPanel() {
  // Inputs
  const [wasteHeat, setWasteHeat] = useState(500);
  const [tRad, setTRad] = useState(300);
  const [powerReq, setPowerReq] = useState(1000);
  const [missionYr, setMissionYr] = useState(5);
  const [distAU, setDistAU] = useState(1.0);
  const [loadEclipse, setLoadEclipse] = useState(500);
  const [eclipseMin, setEclipseMin] = useState(35);
  const [vehicleMass, setVehicleMass] = useState(1000);

  // Results
  const [rad, setRad] = useState<RadiatorResult | null>(null);
  const [solar, setSolar] = useState<SolarResult | null>(null);
  const [bat, setBat] = useState<BatteryResult | null>(null);
  const [rcs, setRcs] = useState<RCSResult | null>(null);

  const SIGMA = 5.670374419e-8;
  const SOLAR_CONST = 1361;
  const G0 = 9.80665;

  const computeAll = () => {
    // Radiator: Q = ε σ A (T^4 - T_env^4)
    const eps = 0.85;
    const tEnv = 250;
    const tEff4 = Math.pow(tRad, 4) - Math.pow(tEnv, 4);
    const radArea = wasteHeat / (eps * SIGMA * 0.5 * tEff4);
    setRad({ area_m2: radArea, mass_kg: radArea * 5 });

    // Solar array
    const flux = SOLAR_CONST / (distAU * distAU);
    const eolFactor = Math.pow(1 - 0.02, missionYr);
    const effEff = 0.3 * 0.8 * (1 - 0.1);
    const bol = powerReq / eolFactor;
    const solArea = bol / (flux * effEff);
    setSolar({ area_m2: solArea, bol_power_w: bol, mass_kg: solArea * 2.5 });

    // Battery (Li-ion 150 Wh/kg, 40% DoD)
    const energyWh = (loadEclipse * eclipseMin * 60) / 3600 / 0.9;
    const capWh = energyWh / 0.4;
    setBat({ capacity_wh: capWh, mass_kg: capWh / 150 });

    // RCS (5 yr mission, Isp=220, 75 m/s/yr total Δv * 1.3 margin)
    const totalDv = 75 * missionYr * 1.3;
    const exhV = 220 * G0;
    const massRatio = Math.exp(totalDv / exhV);
    const propMass = vehicleMass * (1 - 1 / massRatio);
    setRcs({ propellant_kg: propMass, total_dv_ms: totalDv });
  };

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">
          Subsystem Sizing — First-Order Estimates
        </h2>
        <p className="text-xs text-ui-text-dim">
          SMAD Ch. 11 formulas for conceptual spacecraft design
        </p>
      </div>

      {/* Input grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4">
        <Input label="Waste heat (W)" value={wasteHeat} onChange={setWasteHeat} />
        <Input label="Rad temp (K)" value={tRad} onChange={setTRad} />
        <Input label="Power req (W)" value={powerReq} onChange={setPowerReq} />
        <Input label="Mission (yr)" value={missionYr} onChange={setMissionYr} />
        <Input label="Distance (AU)" value={distAU} onChange={setDistAU} />
        <Input label="Eclipse load (W)" value={loadEclipse} onChange={setLoadEclipse} />
        <Input label="Eclipse (min)" value={eclipseMin} onChange={setEclipseMin} />
        <Input label="Vehicle mass (kg)" value={vehicleMass} onChange={setVehicleMass} />
      </div>

      <button
        onClick={computeAll}
        className="mb-4 px-4 py-2 bg-ui-accent/40 hover:bg-ui-accent-strong text-white rounded text-sm"
      >
        Compute All Subsystems
      </button>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {rad && (
          <Card title="Radiator" accent="orange">
            <Row label="Area" value={`${rad.area_m2.toFixed(2)} m²`} />
            <Row label="Mass (@5 kg/m²)" value={`${rad.mass_kg.toFixed(1)} kg`} />
            <Row label="Operating temp" value={`${tRad} K`} />
            <Row label="Waste heat" value={`${wasteHeat} W`} />
          </Card>
        )}
        {solar && (
          <Card title="Solar Array" accent="yellow">
            <Row label="Area" value={`${solar.area_m2.toFixed(2)} m²`} />
            <Row label="BOL power" value={`${solar.bol_power_w.toFixed(0)} W`} />
            <Row label="EOL power" value={`${powerReq} W`} />
            <Row label="Mass (@2.5 kg/m²)" value={`${solar.mass_kg.toFixed(1)} kg`} />
          </Card>
        )}
        {bat && (
          <Card title="Battery" accent="green">
            <Row label="Capacity" value={`${bat.capacity_wh.toFixed(0)} Wh`} />
            <Row label="Mass (Li-ion)" value={`${bat.mass_kg.toFixed(1)} kg`} />
            <Row label="DoD" value="40%" />
            <Row label="Chemistry" value="150 Wh/kg" />
          </Card>
        )}
        {rcs && (
          <Card title="RCS Propellant" accent="cyan">
            <Row label="Propellant mass" value={`${rcs.propellant_kg.toFixed(1)} kg`} />
            <Row label="Total Δv" value={`${rcs.total_dv_ms.toFixed(0)} m/s`} />
            <Row label="Isp" value="220 s (monoprop)" />
            <Row label="Margin" value="30%" />
          </Card>
        )}
      </div>
    </div>
  );
}

function Input({
  label, value, onChange,
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

function Card({
  title, accent, children,
}: {
  title: string;
  accent: 'orange' | 'yellow' | 'green' | 'cyan';
  children: React.ReactNode;
}) {
  const colors: Record<string, string> = {
    orange: 'text-sev-warn',
    yellow: 'text-sev-warn',
    green: 'text-sev-ok',
    cyan: 'text-ui-accent',
  };
  return (
    <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
      <h3 className={`text-sm font-semibold mb-2 ${colors[accent]}`}>{title}</h3>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between text-xs">
      <span className="text-ui-text-dim">{label}:</span>
      <span className="font-mono text-ui-text">{value}</span>
    </div>
  );
}
