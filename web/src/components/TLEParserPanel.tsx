/**
 * TLE Parser Panel — decode NORAD Two-Line Element sets.
 *
 * Paste a TLE (3-line name + 2-line orbit) or just 2 lines, and see
 * derived orbit parameters: semi-major axis, period, apogee/perigee,
 * inclination, eccentricity, etc.
 */

import { useState } from 'react';

interface TLEResult {
  name: string;
  satellite_number: number;
  classification: string;
  epoch: string;
  inclination_deg: number;
  raan_deg: number;
  eccentricity: number;
  arg_perigee_deg: number;
  mean_anomaly_deg: number;
  mean_motion_rev_per_day: number;
  bstar: number;
  semi_major_axis_km: number;
  period_min: number;
  apogee_km: number;
  perigee_km: number;
  error?: string;
}

const EXAMPLE_TLE = `ISS (ZARYA)
1 25544U 98067A   24015.50000000  .00016717  00000-0  10270-3 0  9994
2 25544  51.6413   0.0000 0005291 132.2917  16.7083 15.49309239432456`;

export function TLEParserPanel() {
  const [text, setText] = useState(EXAMPLE_TLE);
  const [result, setResult] = useState<TLEResult | null>(null);

  const parse = () => {
    const lines = text.split('\n').filter((l) => l.trim());
    let name = '';
    let l1 = '';
    let l2 = '';
    if (lines.length >= 3 && !lines[0].startsWith('1 ')) {
      name = lines[0].trim();
      l1 = lines[1];
      l2 = lines[2];
    } else if (lines.length >= 2) {
      l1 = lines[0];
      l2 = lines[1];
    }

    try {
      if (l1.length !== 69 || l2.length !== 69) {
        throw new Error(`TLE lines must be 69 chars (got ${l1.length}/${l2.length})`);
      }
      const satNum = parseInt(l1.substring(2, 7), 10);
      const classification = l1[7];
      const epochYearShort = parseInt(l1.substring(18, 20), 10);
      const epochYear = epochYearShort < 57 ? 2000 + epochYearShort : 1900 + epochYearShort;
      const epochDay = parseFloat(l1.substring(20, 32));
      const bstarStr = l1.substring(53, 61).trim();
      let bstar = 0;
      if (bstarStr && bstarStr !== '00000-0') {
        const signStripped = bstarStr.replace(/^[-+]/, '');
        const match = signStripped.match(/(\d+)([-+])(\d+)/);
        if (match) {
          const sign = bstarStr[0] === '-' ? -1 : 1;
          const mantissa = parseFloat('0.' + match[1]);
          const exp = parseInt(match[2] + match[3], 10);
          bstar = sign * mantissa * Math.pow(10, exp);
        }
      }
      const inc = parseFloat(l2.substring(8, 16));
      const raan = parseFloat(l2.substring(17, 25));
      const ecc = parseFloat('0.' + l2.substring(26, 33));
      const argp = parseFloat(l2.substring(34, 42));
      const ma = parseFloat(l2.substring(43, 51));
      const mm = parseFloat(l2.substring(52, 63));

      // Derived
      const muEarth = 3.986e14;
      const nRadSec = (mm * 2 * Math.PI) / 86400;
      const a = Math.pow(muEarth / (nRadSec * nRadSec), 1 / 3);
      const periodSec = 86400 / mm;
      const apogee = (a * (1 + ecc) - 6378137) / 1000;
      const perigee = (a * (1 - ecc) - 6378137) / 1000;

      const date = new Date(epochYear, 0, 1);
      date.setTime(date.getTime() + (epochDay - 1) * 86400 * 1000);

      setResult({
        name,
        satellite_number: satNum,
        classification,
        epoch: date.toISOString(),
        inclination_deg: inc,
        raan_deg: raan,
        eccentricity: ecc,
        arg_perigee_deg: argp,
        mean_anomaly_deg: ma,
        mean_motion_rev_per_day: mm,
        bstar,
        semi_major_axis_km: a / 1000,
        period_min: periodSec / 60,
        apogee_km: apogee,
        perigee_km: perigee,
      });
    } catch (err: any) {
      setResult({
        name: '',
        satellite_number: 0,
        classification: '',
        epoch: '',
        inclination_deg: 0,
        raan_deg: 0,
        eccentricity: 0,
        arg_perigee_deg: 0,
        mean_anomaly_deg: 0,
        mean_motion_rev_per_day: 0,
        bstar: 0,
        semi_major_axis_km: 0,
        period_min: 0,
        apogee_km: 0,
        perigee_km: 0,
        error: err.message,
      });
    }
  };

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">TLE Parser</h2>
        <p className="text-xs text-ui-text-dim">
          Decode NORAD Two-Line Element sets (CCSDS / Spacetrack Report #3)
        </p>
      </div>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        className="w-full h-32 bg-ui-bg-2 border border-ui-border-strong rounded p-2 text-ui-text text-xs font-mono"
      />

      <button
        onClick={parse}
        className="mt-2 mb-4 px-4 py-2 bg-ui-accent/40 hover:bg-ui-accent-strong text-white rounded text-sm"
      >
        Parse TLE
      </button>

      {result && result.error && (
        <div className="bg-sev-crit/40 border border-sev-crit rounded p-3 text-sev-crit text-xs">
          Error: {result.error}
        </div>
      )}

      {result && !result.error && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
            <h3 className="text-sm font-semibold text-sev-ok mb-2">Identity</h3>
            <Row label="Name" value={result.name || '(unnamed)'} />
            <Row label="NORAD ID" value={result.satellite_number} />
            <Row label="Classification" value={result.classification} />
            <Row label="Epoch" value={new Date(result.epoch).toISOString().substring(0, 19)} />
          </div>

          <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
            <h3 className="text-sm font-semibold text-ui-accent mb-2">Elements</h3>
            <Row label="Inclination" value={`${result.inclination_deg.toFixed(4)}°`} />
            <Row label="RAAN" value={`${result.raan_deg.toFixed(4)}°`} />
            <Row label="Eccentricity" value={result.eccentricity.toFixed(7)} />
            <Row label="Arg of perigee" value={`${result.arg_perigee_deg.toFixed(4)}°`} />
            <Row label="Mean anomaly" value={`${result.mean_anomaly_deg.toFixed(4)}°`} />
            <Row label="Mean motion" value={`${result.mean_motion_rev_per_day.toFixed(8)} rev/day`} />
          </div>

          <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
            <h3 className="text-sm font-semibold text-sev-warn mb-2">Derived Orbit</h3>
            <Row label="Semi-major axis" value={`${result.semi_major_axis_km.toFixed(1)} km`} />
            <Row label="Period" value={`${result.period_min.toFixed(2)} min`} />
            <Row label="Apogee alt" value={`${result.apogee_km.toFixed(1)} km`} />
            <Row label="Perigee alt" value={`${result.perigee_km.toFixed(1)} km`} />
          </div>

          <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
            <h3 className="text-sm font-semibold text-sev-warn mb-2">Drag</h3>
            <Row label="BSTAR" value={result.bstar.toExponential(4)} />
            <div className="mt-2 text-[11px] text-ui-text-dim">
              BSTAR is the SGP4 drag term in units of 1/earth_radii.
              Larger BSTAR → more drag → faster orbital decay.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between text-xs py-0.5">
      <span className="text-ui-text-dim">{label}:</span>
      <span className="font-mono text-ui-text">{value}</span>
    </div>
  );
}
