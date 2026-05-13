/**
 * Mass Estimator — payload-to-spacecraft mass scaling.
 *
 * Heuristic estimator using SMAD Table 14-18 subsystem fractions.
 * Given payload mass + mission type, produces dry mass estimate
 * with subsystem breakdown. For conceptual/Phase-A mission sizing.
 */

import { useState } from 'react';

interface SubsystemFraction {
  subsystem: string;
  mass_kg: number;
  percent: number;
}

export function MassEstimator() {
  const [payloadMass, setPayloadMass] = useState(50);
  const [missionType, setMissionType] = useState<
    'leo_science' | 'gto_comm' | 'interplanetary'
  >('leo_science');
  const [dryMass, setDryMass] = useState<number | null>(null);
  const [subsystems, setSubsystems] = useState<SubsystemFraction[]>([]);

  const compute = () => {
    const fractions: Record<string, Record<string, number>> = {
      leo_science: {
        structure: 0.2, power: 0.25, thermal: 0.04, adcs: 0.08,
        comms: 0.04, avionics: 0.04, propulsion: 0.05,
        payload: 0.2, harness: 0.1,
      },
      gto_comm: {
        structure: 0.22, power: 0.28, thermal: 0.03, adcs: 0.06,
        comms: 0.06, avionics: 0.04, propulsion: 0.12,
        payload: 0.15, harness: 0.04,
      },
      interplanetary: {
        structure: 0.15, power: 0.3, thermal: 0.05, adcs: 0.08,
        comms: 0.05, avionics: 0.04, propulsion: 0.1,
        payload: 0.18, harness: 0.05,
      },
    };
    const frac = fractions[missionType];
    const total = payloadMass / frac.payload;
    const rows: SubsystemFraction[] = [];
    for (const [sub, f] of Object.entries(frac)) {
      rows.push({
        subsystem: sub,
        mass_kg: total * f,
        percent: f * 100,
      });
    }
    rows.sort((a, b) => b.mass_kg - a.mass_kg);
    setDryMass(total);
    setSubsystems(rows);
  };

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">
          Mass Estimator — SMAD Heuristic
        </h2>
        <p className="text-xs text-ui-text-dim">
          Scale dry mass from payload using Wertz & Larson (1999) Table 14-18
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <label className="flex flex-col text-xs">
          <span className="text-ui-text-dim">Payload mass (kg)</span>
          <input
            type="number"
            value={payloadMass}
            onChange={(e) => setPayloadMass(Number(e.target.value))}
            className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text"
          />
        </label>
        <label className="flex flex-col text-xs">
          <span className="text-ui-text-dim">Mission type</span>
          <select
            value={missionType}
            onChange={(e) => setMissionType(e.target.value as any)}
            className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text"
          >
            <option value="leo_science">LEO Science</option>
            <option value="gto_comm">GTO Communications</option>
            <option value="interplanetary">Interplanetary</option>
          </select>
        </label>
      </div>

      <button
        onClick={compute}
        className="mb-4 px-4 py-2 bg-ui-accent/40 hover:bg-ui-accent-strong text-white rounded text-sm"
      >
        Compute Mass Budget
      </button>

      {dryMass !== null && (
        <div className="space-y-3">
          <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
            <div className="text-sm text-ui-text mb-1">
              <strong>Estimated dry mass:</strong> {dryMass.toFixed(1)} kg
            </div>
            <div className="text-xs text-ui-text-dim">
              {payloadMass} kg payload →{' '}
              {((dryMass / payloadMass)).toFixed(1)}× scaling for{' '}
              {missionType.replace('_', ' ')}
            </div>
          </div>

          <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
            <div className="text-xs uppercase tracking-wider text-ui-text-faint mb-2">
              Subsystem Breakdown
            </div>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-ui-text-dim border-b border-ui-border">
                  <th className="text-left py-1">Subsystem</th>
                  <th className="text-right py-1">Mass (kg)</th>
                  <th className="text-right py-1">%</th>
                  <th className="text-left py-1 pl-3">Share</th>
                </tr>
              </thead>
              <tbody>
                {subsystems.map((s) => (
                  <tr key={s.subsystem} className="text-ui-text">
                    <td className="py-1 capitalize">{s.subsystem}</td>
                    <td className="text-right font-mono py-1">
                      {s.mass_kg.toFixed(1)}
                    </td>
                    <td className="text-right font-mono py-1">
                      {s.percent.toFixed(1)}%
                    </td>
                    <td className="pl-3 py-1">
                      <div className="h-2 bg-ui-bg-2 rounded overflow-hidden">
                        <div
                          className="h-full bg-ui-accent"
                          style={{ width: `${Math.min(100, s.percent * 3)}%` }}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3 text-[11px] text-ui-text">
            <p className="font-semibold mb-1">SMAD typical fractions:</p>
            <ul className="list-disc pl-4 text-ui-text-dim space-y-0.5">
              <li>Structure: 15-25%, Propulsion: 3-8%</li>
              <li>Power: 20-30%, Thermal: 2-5%</li>
              <li>ADCS: 5-10%, Comms: 3-6%, Avionics: 3-5%</li>
              <li>Payload: 15-25%, Harness: 3-8%</li>
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
