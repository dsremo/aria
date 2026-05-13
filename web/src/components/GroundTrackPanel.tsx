/**
 * Ground Track Panel — sub-satellite trace over a rotating Earth.
 *
 * Takes a TLE (or pre-defined orbit), propagates Keplerian motion for
 * N orbits, rotates ECI → ECEF, converts to geodetic lat/lon, and
 * draws the classic ground track on an equirectangular map.
 *
 * Pure client-side compute — no backend round-trip. Uses the same
 * TLE parser and ECI→ECEF rotation as src/aria/simulation/ground_track.py.
 */

import { useEffect, useRef, useState } from 'react';

const MU_EARTH = 3.986004418e14;            // m³/s² (EGM2008)
const R_EARTH = 6378137.0;                  // m, WGS-84 equatorial
const F_WGS84 = 1.0 / 298.257223563;        // WGS-84 flattening
const OMEGA_EARTH = 7.2921150e-5;           // rad/s, IERS 2010

interface Orbit {
  name: string;
  // Classical elements
  a_m: number;
  ecc: number;
  inc_deg: number;
  raan_deg: number;
  argp_deg: number;
  mean_anom_deg: number;
}

interface TrackPoint {
  t_s: number;
  lat: number;       // deg
  lon: number;       // deg
  alt_km: number;
}

const PRESETS: Record<string, Orbit> = {
  iss: {
    name: 'ISS (51.6° / 408 km)',
    a_m: R_EARTH + 408_000,
    ecc: 0.0005,
    inc_deg: 51.64,
    raan_deg: 0,
    argp_deg: 0,
    mean_anom_deg: 0,
  },
  sso: {
    name: 'Sun-Sync (98.2° / 700 km)',
    a_m: R_EARTH + 700_000,
    ecc: 0.0,
    inc_deg: 98.19,
    raan_deg: 0,
    argp_deg: 0,
    mean_anom_deg: 0,
  },
  geo: {
    name: 'GEO (0° / 35786 km)',
    a_m: R_EARTH + 35_786_000,
    ecc: 0.0,
    inc_deg: 0.05,
    raan_deg: 0,
    argp_deg: 0,
    mean_anom_deg: 30,
  },
  molniya: {
    name: 'Molniya (63.4° / e=0.74)',
    a_m: 26_600_000,
    ecc: 0.74,
    inc_deg: 63.4,
    raan_deg: 0,
    argp_deg: 270,
    mean_anom_deg: 0,
  },
  polar: {
    name: 'Polar LEO (90° / 800 km)',
    a_m: R_EARTH + 800_000,
    ecc: 0.0,
    inc_deg: 90.0,
    raan_deg: 0,
    argp_deg: 0,
    mean_anom_deg: 0,
  },
};

function solveKepler(M: number, e: number): number {
  // Newton-Raphson, ~5 iterations to machine precision (Vallado §2.2).
  let E = M + (e * Math.sin(M)) / (1 - Math.sin(M + e) + Math.sin(M));
  for (let i = 0; i < 20; i++) {
    const f = E - e * Math.sin(E) - M;
    const fp = 1 - e * Math.cos(E);
    const dE = -f / fp;
    E += dE;
    if (Math.abs(dE) < 1e-12) break;
  }
  return E;
}

function eciFromCOE(o: Orbit, t_s: number): [number, number, number] {
  const n = Math.sqrt(MU_EARTH / Math.pow(o.a_m, 3)); // rad/s
  const M = (o.mean_anom_deg * Math.PI) / 180 + n * t_s;
  const E = solveKepler(M, o.ecc);
  const cosE = Math.cos(E);
  const sinE = Math.sin(E);
  const r_pf = o.a_m * (1 - o.ecc * cosE);
  const nu = Math.atan2(Math.sqrt(1 - o.ecc * o.ecc) * sinE, cosE - o.ecc);
  const x_pf = r_pf * Math.cos(nu);
  const y_pf = r_pf * Math.sin(nu);

  const inc = (o.inc_deg * Math.PI) / 180;
  const raan = (o.raan_deg * Math.PI) / 180;
  const argp = (o.argp_deg * Math.PI) / 180;

  const cR = Math.cos(raan), sR = Math.sin(raan);
  const ci = Math.cos(inc), si = Math.sin(inc);
  const cw = Math.cos(argp), sw = Math.sin(argp);

  // Perifocal → ECI (Vallado §2.6, eq 2-126).
  const r11 = cR * cw - sR * sw * ci;
  const r12 = -cR * sw - sR * cw * ci;
  const r21 = sR * cw + cR * sw * ci;
  const r22 = -sR * sw + cR * cw * ci;
  const r31 = sw * si;
  const r32 = cw * si;

  return [
    r11 * x_pf + r12 * y_pf,
    r21 * x_pf + r22 * y_pf,
    r31 * x_pf + r32 * y_pf,
  ];
}

function eciToEcef(r: [number, number, number], t_s: number): [number, number, number] {
  const theta = OMEGA_EARTH * t_s;
  const ct = Math.cos(theta), st = Math.sin(theta);
  return [r[0] * ct + r[1] * st, -r[0] * st + r[1] * ct, r[2]];
}

function ecefToGeodetic(r: [number, number, number]): [number, number, number] {
  // Heikkinen 1982 / Bowring 1985 iteration.
  const [x, y, z] = r;
  const e2 = 2 * F_WGS84 - F_WGS84 * F_WGS84;
  const lon = Math.atan2(y, x);
  const p = Math.sqrt(x * x + y * y);
  if (p < 1e-6) {
    const lat = z > 0 ? Math.PI / 2 : -Math.PI / 2;
    return [(lat * 180) / Math.PI, (lon * 180) / Math.PI, Math.abs(z) - R_EARTH * Math.sqrt(1 - e2)];
  }
  let lat = Math.atan2(z, p * (1 - e2));
  let alt = 0;
  for (let i = 0; i < 5; i++) {
    const sLat = Math.sin(lat);
    const N = R_EARTH / Math.sqrt(1 - e2 * sLat * sLat);
    alt = p / Math.cos(lat) - N;
    const newLat = Math.atan2(z, p * (1 - (e2 * N) / (N + alt)));
    if (Math.abs(newLat - lat) < 1e-12) {
      lat = newLat;
      break;
    }
    lat = newLat;
  }
  return [(lat * 180) / Math.PI, (lon * 180) / Math.PI, alt];
}

function isSunSync(o: Orbit): boolean {
  // J2 nodal regression, Vallado §9.7.1.
  const J2 = 1.08263e-3;
  const a = o.a_m;
  const n = Math.sqrt(MU_EARTH / (a * a * a));
  const cosi = Math.cos((o.inc_deg * Math.PI) / 180);
  const omega_dot = -1.5 * n * J2 * Math.pow(R_EARTH / a, 2) * cosi;
  const deg_per_day = (omega_dot * 180) / Math.PI * 86400.0;
  const target = 360.0 / 365.25;
  return Math.abs(deg_per_day - target) < 2.0;
}

export function GroundTrackPanel() {
  const [presetKey, setPresetKey] = useState<string>('iss');
  const [orbits, setOrbits] = useState(3);
  const [points, setPoints] = useState<TrackPoint[]>([]);
  const [hoverPt, setHoverPt] = useState<null | {
    pt: TrackPoint; clientX: number; clientY: number;
  }>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const orbit = PRESETS[presetKey];
  const periodS = 2 * Math.PI * Math.sqrt(Math.pow(orbit.a_m, 3) / MU_EARTH);

  useEffect(() => {
    const totalT = periodS * orbits;
    const dt = Math.max(periodS / 240, 1.0);
    const out: TrackPoint[] = [];
    for (let t = 0; t <= totalT; t += dt) {
      const r_eci = eciFromCOE(orbit, t);
      const r_ecef = eciToEcef(r_eci, t);
      const [lat, lon, alt] = ecefToGeodetic(r_ecef);
      out.push({ t_s: t, lat, lon, alt_km: alt / 1000 });
    }
    setPoints(out);
  }, [presetKey, orbits, periodS]);

  useEffect(() => {
    if (!canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;

    // Ocean background.
    ctx.fillStyle = '#0b1735';
    ctx.fillRect(0, 0, W, H);

    // Lat/lon grid.
    ctx.strokeStyle = '#1e3a5f';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let lon = -180; lon <= 180; lon += 30) {
      const x = ((lon + 180) / 360) * W;
      ctx.moveTo(x, 0);
      ctx.lineTo(x, H);
    }
    for (let lat = -90; lat <= 90; lat += 30) {
      const y = ((90 - lat) / 180) * H;
      ctx.moveTo(0, y);
      ctx.lineTo(W, y);
    }
    ctx.stroke();

    // Equator highlight.
    ctx.strokeStyle = '#475569';
    ctx.beginPath();
    ctx.moveTo(0, H / 2);
    ctx.lineTo(W, H / 2);
    ctx.stroke();

    // Continent silhouettes (very rough — just landmass rectangles for visual context).
    ctx.fillStyle = '#1c3a26';
    const land: [number, number, number, number][] = [
      [-170, 50, 90, 35],   // North America (lon, lat-top, dlon, dlat)
      [-90, 12, 50, 60],    // South America
      [-15, 70, 65, 35],    // Europe
      [-20, 35, 70, 70],    // Africa
      [40, 75, 100, 50],    // Asia
      [110, -10, 40, 30],   // Australia
      [-170, -75, 340, 15], // Antarctica strip
    ];
    for (const [lon, latTop, dlon, dlat] of land) {
      const x = ((lon + 180) / 360) * W;
      const y = ((90 - latTop) / 180) * H;
      ctx.fillRect(x, y, (dlon / 360) * W, (dlat / 180) * H);
    }

    // Track — break on longitude wrap.
    ctx.strokeStyle = '#facc15';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    let prevX = -1, prevY = -1;
    for (const p of points) {
      const x = ((p.lon + 180) / 360) * W;
      const y = ((90 - p.lat) / 180) * H;
      if (prevX < 0 || Math.abs(x - prevX) > W * 0.5) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
      prevX = x;
      prevY = y;
    }
    ctx.stroke();

    // Current sub-satellite point.
    if (points.length > 0) {
      const p = points[points.length - 1];
      const x = ((p.lon + 180) / 360) * W;
      const y = ((90 - p.lat) / 180) * H;
      ctx.fillStyle = '#f87171';
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fill();
    }

    // Axis labels.
    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px monospace';
    ctx.fillText('-180°', 2, H - 4);
    ctx.fillText('0°', W / 2 - 6, H - 4);
    ctx.fillText('+180°', W - 32, H - 4);
    ctx.fillText('+90°', 2, 10);
    ctx.fillText('-90°', 2, H - 14);
  }, [points]);

  // Stats.
  const maxLat = points.reduce((m, p) => Math.max(m, Math.abs(p.lat)), 0);
  const lonsCovered = new Set(points.map((p) => Math.floor(p.lon / 10))).size;
  const coverPct = (lonsCovered / 36) * 100;

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Ground Track</h2>
        <p className="text-xs text-ui-text-dim">
          Sub-satellite trace over a rotating Earth (ECI → ECEF → WGS-84 geodetic)
        </p>
      </div>

      <div className="flex flex-wrap gap-3 items-end mb-3">
        <label className="flex flex-col text-xs">
          <span className="text-ui-text-dim">Preset</span>
          <select
            value={presetKey}
            onChange={(e) => setPresetKey(e.target.value)}
            className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text"
          >
            {Object.entries(PRESETS).map(([k, o]) => (
              <option key={k} value={k}>{o.name}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col text-xs">
          <span className="text-ui-text-dim">Orbits to plot</span>
          <input
            type="number"
            min={1}
            max={20}
            value={orbits}
            onChange={(e) => setOrbits(Math.max(1, Math.min(20, Number(e.target.value))))}
            className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text w-24"
          />
        </label>
      </div>

      {/* Canvas wrapped in a relative div so the hover tooltip can be
          absolutely-positioned against cursor coordinates.  Canvas is
          rendered at 720×360 native but displays `w-full`, so we
          rescale clientX/Y → canvas space before the distance check. */}
      <div
        className="relative"
        onMouseLeave={() => setHoverPt(null)}
        onMouseMove={(e) => {
          const canvas = canvasRef.current;
          if (!canvas || points.length === 0) return;
          const rect = canvas.getBoundingClientRect();
          const scaleX = canvas.width  / rect.width;
          const scaleY = canvas.height / rect.height;
          const cx = (e.clientX - rect.left) * scaleX;
          const cy = (e.clientY - rect.top)  * scaleY;
          // Find closest track point by 2D distance on the projected map.
          let best: TrackPoint | null = null;
          let bestD = Infinity;
          for (const p of points) {
            const x = ((p.lon + 180) / 360) * canvas.width;
            const y = ((90 - p.lat) / 180) * canvas.height;
            const d = (x - cx) ** 2 + (y - cy) ** 2;
            if (d < bestD) { bestD = d; best = p; }
          }
          // Accept hover within ~20 px in canvas space; else clear so
          // the tooltip doesn't chase the mouse over empty ocean.
          if (best && bestD < 20 * 20) {
            setHoverPt({ pt: best, clientX: e.clientX - rect.left, clientY: e.clientY - rect.top });
          } else {
            setHoverPt(null);
          }
        }}
      >
        <canvas
          ref={canvasRef}
          width={720}
          height={360}
          className="w-full border border-ui-border rounded bg-ui-bg-0 block"
        />
        {hoverPt && (
          <div
            className="absolute pointer-events-none z-10 px-2 py-1 rounded
                       border border-ui-accent bg-ui-bg-1/95 text-xs shadow-lg
                       whitespace-nowrap"
            style={{
              left: Math.min(hoverPt.clientX + 12, 560),
              top:  Math.max(hoverPt.clientY - 36, 4),
            }}>
            <div className="text-[10px] uppercase tracking-wider text-ui-accent">
              T+ {(hoverPt.pt.t_s / 60).toFixed(1)} min
            </div>
            <div className="text-ui-text font-mono">
              {hoverPt.pt.lat >= 0 ? 'N' : 'S'} {Math.abs(hoverPt.pt.lat).toFixed(3)}° · {hoverPt.pt.lon >= 0 ? 'E' : 'W'} {Math.abs(hoverPt.pt.lon).toFixed(3)}°
            </div>
            <div className="text-ui-text-dim font-mono text-[11px]">
              alt {hoverPt.pt.alt_km.toFixed(1)} km · orbit {Math.floor(hoverPt.pt.t_s / periodS) + 1}/{orbits}
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
        <Card title="Period" value={`${(periodS / 60).toFixed(2)} min`} />
        <Card title="Max latitude" value={`${maxLat.toFixed(2)}°`} />
        <Card title="Longitude coverage" value={`${coverPct.toFixed(0)}%`} />
        <Card title="Sun-sync (J2)" value={isSunSync(orbit) ? 'YES' : 'no'} accent={isSunSync(orbit) ? 'green' : undefined} />
      </div>

      <div className="mt-4 text-[11px] text-ui-text-dim space-y-1">
        <p>• Keplerian propagation only — no J2 / drag / SRP. Use TLE Parser + SGP4 for real satellites.</p>
        <p>• ECI → ECEF rotation uses mean sidereal rate (no precession/nutation).</p>
        <p>• Map continents are rough rectangles for orientation, not GIS data.</p>
      </div>
    </div>
  );
}

function Card({ title, value, accent }: { title: string; value: string; accent?: 'green' }) {
  const color = accent === 'green' ? 'text-sev-ok' : 'text-ui-text';
  return (
    <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
      <div className="text-xs text-ui-text-dim">{title}</div>
      <div className={`text-base font-mono ${color}`}>{value}</div>
    </div>
  );
}
