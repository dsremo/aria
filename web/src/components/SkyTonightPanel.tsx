/**
 * Sky Tonight Panel — observer-location aware planisphere.
 *
 * Pick a city (or enter lat/lon) and a time, and see exactly what's
 * above the horizon: bright stars + planets + Messier deep-sky.
 * Zenith-centered azimuthal projection (the kind printed on a paper
 * planisphere): zenith at center, horizon at the rim, north up.
 *
 * Backend: /api/sky_now does Local Sidereal Time + the equatorial→
 * horizontal transform; the canvas only draws what we get back.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

interface HorizonPos {
  name: string;
  kind: 'sun' | 'moon' | 'planet' | 'star' | 'messier' | 'satellite' | 'asteroid' | 'comet';
  alt: number;        // degrees above horizon
  az: number;         // degrees from north through east
  ra: number;
  dec: number;
  mag: number;
  color: [number, number, number];
  distance_au?: number;
}

interface DayConditions {
  sunrise: number | null;
  sunset: number | null;
  solar_noon: number | null;
  civil_dawn: number | null;
  civil_dusk: number | null;
  astro_dawn: number | null;
  astro_dusk: number | null;
  moonrise: number | null;
  moonset: number | null;
  moon_phase_label: string;
  moon_phase_fraction: number;
  moon_age_days: number;
}

interface SkyResponse {
  jd: number;
  lat: number;
  lon: number;
  counts: Record<string, number>;
  planets: HorizonPos[];
  stars: HorizonPos[];
  messier: HorizonPos[];
  conditions?: DayConditions;
}

interface SatelliteData {
  name: string;
  category: string;
  norad: number;
  alt: number;
  az: number;
  range_km: number;
  altitude_km: number;
  speed_kmps: number;
  period_min: number;
  sub_lat: number;
  sub_lon: number;
  above_horizon: boolean;
}

interface SatellitesResponse {
  jd: number;
  lat: number;
  lon: number;
  count: number;
  visible_count: number;
  satellites: SatelliteData[];
}

interface City {
  name: string;
  lat: number;
  lon: number;
}

function jdNow(): number {
  return Date.now() / 86400000 + 2440587.5;
}

/** JD → "HH:MM UT" with optional offset_min for local-time display. */
function jdToTime(jd: number | null, offsetMin = 0): string {
  if (jd === null) return '—';
  const z = Math.floor(jd + 0.5);
  const dayFrac = jd + 0.5 - z;
  const totalMin = Math.floor(dayFrac * 24 * 60) + offsetMin;
  const norm = ((totalMin % 1440) + 1440) % 1440;
  const h = Math.floor(norm / 60);
  const m = norm % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

function jdFromCivil(year: number, month: number, day: number, hourUT: number): number {
  let y = year, m = month;
  if (m <= 2) { y -= 1; m += 12; }
  const a = Math.floor(y / 100);
  const b = 2 - a + Math.floor(a / 4);
  return Math.floor(365.25 * (y + 4716)) + Math.floor(30.6001 * (m + 1)) + day + b - 1524.5 + hourUT / 24;
}

/** Azimuthal equidistant projection centered on zenith.
 *  altitude → radius (0=horizon → R, 90=zenith → 0)
 *  azimuth  → angle (north=up, east=right)
 */
function project(alt: number, az: number, R: number): [number, number] {
  const r = (1 - alt / 90) * R;
  // Math: convert "from north, clockwise" to canvas (x right, y down).
  // North up = az=0 → upward = (0, -r). az=90 (east) → right = (r, 0).
  const a = (az * Math.PI) / 180;
  return [Math.sin(a) * r, -Math.cos(a) * r];
}

/** Azimuth degrees → 16-wind compass direction (N, NNE, NE, …). */
function azimuthToCompass(az: number): string {
  const dirs = ['N','NNE','NE','ENE','E','ESE','SE','SSE',
                'S','SSW','SW','WSW','W','WNW','NW','NNW'];
  const normalized = ((az % 360) + 360) % 360;
  return dirs[Math.round(normalized / 22.5) % 16];
}

export function SkyTonightPanel() {
  const [cities, setCities] = useState<City[]>([]);
  const [selectedCity, setSelectedCity] = useState('Bengaluru');
  const [lat, setLat] = useState(12.9716);
  const [lon, setLon] = useState(77.5946);

  const now = useMemo(() => {
    const d = new Date();
    return {
      year: d.getUTCFullYear(),
      month: d.getUTCMonth() + 1,
      day: d.getUTCDate(),
      hour: d.getUTCHours() + d.getUTCMinutes() / 60,
    };
  }, []);
  const [year, setYear] = useState(now.year);
  const [month, setMonth] = useState(now.month);
  const [day, setDay] = useState(now.day);
  const [hourUT, setHourUT] = useState(now.hour);

  const [magStars, setMagStars] = useState(4.5);
  const [showMessier, setShowMessier] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [showSatellites, setShowSatellites] = useState(true);
  const [showDoubles, setShowDoubles] = useState(false);
  const [data, setData] = useState<SkyResponse | null>(null);
  const [sats, setSats] = useState<SatellitesResponse | null>(null);
  const [doubles, setDoubles] = useState<{ doubles: Array<{ name: string; ra: number; dec: number; mag_a: number; notes: string }> } | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Load city list + double stars once
  useEffect(() => {
    fetch('/api/cities').then((r) => r.json())
      .then((j) => setCities(j.cities))
      .catch(() => {});
    fetch('/api/double_stars').then((r) => r.json())
      .then(setDoubles)
      .catch(() => {});
  }, []);

  // When city changes, update lat/lon
  useEffect(() => {
    const c = cities.find((c) => c.name === selectedCity);
    if (c) { setLat(c.lat); setLon(c.lon); }
  }, [selectedCity, cities]);

  const fetchSky = async () => {
    setLoading(true);
    setErr(null);
    try {
      const jd = jdFromCivil(year, month, day, hourUT);
      const params = new URLSearchParams({
        lat: String(lat), lon: String(lon), jd: String(jd),
        mag_stars: String(magStars), mag_dso: showMessier ? '7' : '0',
      });
      const [skyResp, satResp] = await Promise.all([
        fetch(`/api/sky_now?${params}`),
        fetch(`/api/satellites?lat=${lat}&lon=${lon}&jd=${jd}&min_alt=-15`),
      ]);
      if (!skyResp.ok) throw new Error(`sky_now HTTP ${skyResp.status}`);
      const j = await skyResp.json();
      setData(j);
      if (satResp.ok) setSats(await satResp.json());
    } catch (e: any) {
      setErr(e.message ?? String(e));
    } finally {
      setLoading(false);
    }
  };

  // Initial load: wait until cities are populated so lat/lon is correct.
  useEffect(() => { if (cities.length > 0) fetchSky(); }, [cities.length]);

  // Re-render canvas whenever data / toggles change.
  useEffect(() => {
    if (!data || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const W = canvas.width, H = canvas.height;
    const cx = W / 2, cy = H / 2;
    const R = Math.min(W, H) / 2 - 22;

    // Sky background — color depends on Sun altitude at the requested time.
    // Day:    bright blue     (Sun > 0°)
    // Civil:  sunset orange   (0° > Sun > -6°)
    // Naut:   dark blue       (-6° > Sun > -12°)
    // Astro:  indigo          (-12° > Sun > -18°)
    // Night:  near-black      (Sun < -18°)
    const sunHere = data.planets.find((p) => p.kind === 'sun');
    const sunAlt = sunHere ? sunHere.alt : -90;
    let centerColor = '#020617', edgeColor = '#162347';
    if (sunAlt > 0) {
      centerColor = '#3b82f6'; edgeColor = '#93c5fd';           // day
    } else if (sunAlt > -6) {
      centerColor = '#1e3a8a'; edgeColor = '#f97316';           // civil / sunset
    } else if (sunAlt > -12) {
      centerColor = '#0f172a'; edgeColor = '#1e3a8a';           // nautical
    } else if (sunAlt > -18) {
      centerColor = '#020617'; edgeColor = '#1e293b';           // astronomical
    }
    const sky = ctx.createRadialGradient(cx, cy, 0, cx, cy, R);
    sky.addColorStop(0, centerColor);
    sky.addColorStop(1, edgeColor);
    ctx.fillStyle = '#020308';
    ctx.fillRect(0, 0, W, H);
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.fillStyle = sky;
    ctx.fill();

    // Altitude grid: 30°/60° circles
    ctx.strokeStyle = '#1e3a5f';
    ctx.lineWidth = 0.8;
    for (const h of [30, 60]) {
      const r = (1 - h / 90) * R;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
    }
    // Cardinal directions
    ctx.strokeStyle = '#1e3a5f';
    for (let az = 0; az < 360; az += 30) {
      const [x, y] = project(0, az, R);
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + x, cy + y);
      ctx.stroke();
    }
    // Horizon ring + labels
    ctx.strokeStyle = '#475569';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = '#94a3b8';
    ctx.font = 'bold 13px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('N', cx, cy - R - 6);
    ctx.fillText('S', cx, cy + R + 14);
    ctx.fillText('E', cx + R + 12, cy + 4);
    ctx.fillText('W', cx - R - 12, cy + 4);
    ctx.textAlign = 'left';

    // Stars
    for (const s of data.stars) {
      const [x, y] = project(s.alt, s.az, R);
      const px = cx + x, py = cy + y;
      const size = Math.max(0.7, 3.5 - s.mag * 0.5);
      const alpha = Math.max(0.3, Math.min(1, (magStars + 0.5 - s.mag) / (magStars + 1)));
      ctx.fillStyle = `rgba(${Math.round(s.color[0]*255)},${Math.round(s.color[1]*255)},${Math.round(s.color[2]*255)},${alpha})`;
      ctx.beginPath();
      ctx.arc(px, py, size, 0, Math.PI * 2);
      ctx.fill();
      if (showLabels && s.mag < 1.5 && s.name && !s.name.startsWith('HIP')) {
        ctx.fillStyle = 'rgba(180,200,220,0.8)';
        ctx.font = '11px monospace';
        ctx.fillText(s.name, px + size + 3, py + 3);
      }
    }

    // Messier deep-sky
    if (showMessier) {
      for (const m of data.messier) {
        const [x, y] = project(m.alt, m.az, R);
        const px = cx + x, py = cy + y;
        ctx.strokeStyle = 'rgba(180,140,200,0.6)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(px, py, 4, 0, Math.PI * 2);
        ctx.stroke();
        if (showLabels && m.mag < 6) {
          ctx.fillStyle = 'rgba(180,140,200,0.8)';
          ctx.font = '9px monospace';
          ctx.fillText(m.name.split(' ')[0], px + 6, py + 3);
        }
      }
    }

    // Double stars — small twin-circle marker (drawn before satellites).
    if (showDoubles && doubles && data) {
      const lst = /* reuse already-computed sky coordinates */ 0;   // unused here; backend has alt/az
      // The double-star catalog doesn't include alt/az; compute from RA/Dec + LST.
      // (We use the same Meeus transform as the observer module below, but in-line it.)
      const phi = (data.lat * Math.PI) / 180;
      const nowJD = data.jd;
      const T = (nowJD - 2451545) / 36525;
      const gmstDeg = (280.46061837 + 360.98564736629 * (nowJD - 2451545)
                      + 0.000387933 * T * T) % 360;
      const lstDeg = (gmstDeg + data.lon) % 360;
      for (const d of doubles.doubles) {
        const hDeg = (lstDeg - d.ra + 360) % 360;
        const hRad = (hDeg * Math.PI) / 180;
        const decRad = (d.dec * Math.PI) / 180;
        const sinAlt = Math.sin(decRad) * Math.sin(phi) + Math.cos(decRad) * Math.cos(phi) * Math.cos(hRad);
        const altDeg = Math.asin(Math.max(-1, Math.min(1, sinAlt))) * 180 / Math.PI;
        if (altDeg < 0) continue;
        const cosAlt = Math.cos(Math.asin(sinAlt));
        const sinAz = (-Math.sin(hRad) * Math.cos(decRad) / Math.max(cosAlt, 1e-6));
        const cosAz = (Math.sin(decRad) - Math.sin(phi) * sinAlt) / Math.max(Math.cos(phi) * cosAlt, 1e-6);
        const azDeg = (Math.atan2(sinAz, Math.max(-1, Math.min(1, cosAz))) * 180 / Math.PI + 360) % 360;

        const [x, y] = project(altDeg, azDeg, R);
        const px = cx + x, py = cy + y;
        ctx.strokeStyle = 'rgba(192, 132, 252, 0.8)';
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.arc(px - 2, py, 2.5, 0, Math.PI * 2);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(px + 2, py, 2.5, 0, Math.PI * 2);
        ctx.stroke();
        if (showLabels && d.mag_a < 4) {
          ctx.fillStyle = 'rgba(192, 132, 252, 0.9)';
          ctx.font = '9px monospace';
          ctx.fillText(d.name.split(' ')[0], px + 8, py + 3);
        }
      }
    }

    // Satellites — drawn before planets so the Sun/Moon overlay them.
    if (showSatellites && sats) {
      const catColor: Record<string, string> = {
        crewed:     '#fbbf24',   // amber
        science:    '#a78bfa',   // violet
        navigation: '#34d399',   // emerald
        comm:       '#60a5fa',   // sky blue
        earth_obs:  '#fde68a',   // pale yellow
        geo:        '#f97316',   // orange
      };
      for (const s of sats.satellites) {
        if (s.alt < 0) continue;        // only above-horizon
        const [x, y] = project(s.alt, s.az, R);
        const px = cx + x, py = cy + y;
        const color = catColor[s.category] || '#94a3b8';
        // Triangle marker for satellites — visually distinct from circles (stars/planets)
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(px,         py - 5);
        ctx.lineTo(px + 4.5,   py + 4);
        ctx.lineTo(px - 4.5,   py + 4);
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,0.6)';
        ctx.lineWidth = 0.7;
        ctx.stroke();

        if (showLabels) {
          ctx.fillStyle = color;
          ctx.font = '10px monospace';
          ctx.fillText(s.name.split(' ')[0], px + 7, py + 3);
        }
      }
    }

    // Planets / Sun / Moon — drawn last so they sit on top
    for (const p of data.planets) {
      const [x, y] = project(p.alt, p.az, R);
      const px = cx + x, py = cy + y;
      let size = Math.max(2.5, 6 - p.mag * 0.5);
      if (p.kind === 'sun')  size = 12;
      if (p.kind === 'moon') size = 10;
      const r = Math.round(p.color[0] * 255);
      const g = Math.round(p.color[1] * 255);
      const b = Math.round(p.color[2] * 255);
      // Halo
      const grad = ctx.createRadialGradient(px, py, size * 0.5, px, py, size * 3);
      grad.addColorStop(0, `rgba(${r},${g},${b},0.55)`);
      grad.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(px, py, size * 3, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = `rgb(${r},${g},${b})`;
      ctx.beginPath();
      ctx.arc(px, py, size, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.7)';
      ctx.lineWidth = 1;
      ctx.stroke();
      if (showLabels) {
        ctx.fillStyle = 'rgba(255,230,180,0.95)';
        ctx.font = '12px monospace';
        ctx.fillText(p.name.charAt(0).toUpperCase() + p.name.slice(1), px + size + 4, py - 3);
      }
    }
  }, [data, sats, doubles, magStars, showLabels, showMessier, showSatellites, showDoubles]);

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Sky Tonight — Observer Planisphere</h2>
        <p className="text-xs text-ui-text-dim">
          {data
            ? `${data.counts.stars} stars · ${data.counts.planets} planets · ${data.counts.messier} Messier above horizon`
            : 'Loading…'}
          {data && ` · lat ${data.lat.toFixed(2)}° lon ${data.lon.toFixed(2)}°`}
        </p>
      </div>

      {/* Quick-scan chip row: which named solar-system bodies are above
          the horizon right now, with their altitude + azimuth.  Saves
          the user from hunting the dot on the planisphere when all
          they want to know is "is Jupiter up?". */}
      {data && data.planets.some((p) => p.alt > 0) && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-ui-text-faint">Up now:</span>
          {data.planets
            .filter((p) => p.alt > 0)
            .sort((a, b) => b.alt - a.alt)
            .map((p) => {
              const [r, g, b] = p.color;
              const c = `rgb(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)})`;
              const azDir = azimuthToCompass(p.az);
              return (
                <span key={p.name}
                      className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] rounded
                                 bg-ui-bg-1/70 border border-ui-border"
                      title={`alt ${p.alt.toFixed(1)}° · az ${p.az.toFixed(1)}° (${azDir}) · mag ${p.mag.toFixed(1)}`}>
                  <span className="w-2 h-2 rounded-full" style={{ background: c }} />
                  <span className="text-ui-text">{p.name}</span>
                  <span className="text-ui-text-dim font-mono">{p.alt.toFixed(0)}°</span>
                  <span className="text-ui-text-faint">{azDir}</span>
                </span>
              );
            })}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3 text-xs">
        <label className="flex flex-col">
          <span className="text-ui-text-dim">City</span>
          <select
            value={selectedCity}
            onChange={(e) => setSelectedCity(e.target.value)}
            className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text"
          >
            {cities.map((c) => (
              <option key={c.name} value={c.name}>{c.name}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col">
          <span className="text-ui-text-dim">Latitude (°N)</span>
          <input type="number" step="0.01" value={lat} onChange={(e) => setLat(Number(e.target.value))}
                 className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text" />
        </label>
        <label className="flex flex-col">
          <span className="text-ui-text-dim">Longitude (°E)</span>
          <input type="number" step="0.01" value={lon} onChange={(e) => setLon(Number(e.target.value))}
                 className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text" />
        </label>
        <div className="flex flex-col">
          <span className="text-ui-text-dim">Hour (UT)</span>
          <input type="range" min={0} max={23.99} step={0.25} value={hourUT}
                 onChange={(e) => setHourUT(Number(e.target.value))} />
          <span className="text-ui-text font-mono">
            {String(Math.floor(hourUT)).padStart(2, '0')}:
            {String(Math.floor((hourUT % 1) * 60)).padStart(2, '0')} UT
          </span>
        </div>
        <label className="flex flex-col">
          <span className="text-ui-text-dim">Year</span>
          <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))}
                 className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text" />
        </label>
        <label className="flex flex-col">
          <span className="text-ui-text-dim">Month</span>
          <input type="number" min={1} max={12} value={month} onChange={(e) => setMonth(Number(e.target.value))}
                 className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text" />
        </label>
        <label className="flex flex-col">
          <span className="text-ui-text-dim">Day</span>
          <input type="number" min={1} max={31} value={day} onChange={(e) => setDay(Number(e.target.value))}
                 className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text" />
        </label>
        <button onClick={fetchSky} disabled={loading}
                className="self-end px-4 py-1.5 bg-ui-accent/40 hover:bg-ui-accent-strong text-white rounded disabled:opacity-50">
          {loading ? 'Computing…' : 'Refresh sky'}
        </button>
      </div>

      <div className="flex flex-wrap gap-3 mb-3 text-xs">
        <label className="flex flex-col flex-1 min-w-[200px]">
          <span className="text-ui-text-dim">Star magnitude limit: {magStars.toFixed(1)}</span>
          <input type="range" min={1} max={6} step={0.5} value={magStars}
                 onChange={(e) => setMagStars(Number(e.target.value))} />
        </label>
        <label className="flex items-center gap-1 text-ui-text">
          <input type="checkbox" checked={showMessier} onChange={(e) => setShowMessier(e.target.checked)} />
          Messier
        </label>
        <label className="flex items-center gap-1 text-ui-text">
          <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} />
          Labels
        </label>
        <label className="flex items-center gap-1 text-ui-text">
          <input type="checkbox" checked={showSatellites} onChange={(e) => setShowSatellites(e.target.checked)} />
          Satellites {sats && `(${sats.satellites.filter((s) => s.alt > 0).length} up)`}
        </label>
        <label className="flex items-center gap-1 text-ui-text">
          <input type="checkbox" checked={showDoubles} onChange={(e) => setShowDoubles(e.target.checked)} />
          Double stars {doubles && `(${doubles.doubles.length})`}
        </label>
      </div>

      {err && (
        <div className="bg-sev-crit/40 border border-sev-crit rounded p-2 text-sev-crit text-xs mb-2">Error: {err}</div>
      )}

      <div className="bg-ui-bg-0/80 border border-ui-border rounded overflow-hidden flex justify-center">
        <canvas ref={canvasRef} width={720} height={720} className="block" />
      </div>

      {data?.conditions && (
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
            <h3 className="text-sm font-semibold text-sev-warn mb-2">
              Tonight's Conditions (UT)
            </h3>
            <table className="w-full font-mono">
              <tbody>
                <tr><td className="text-ui-text-dim">Astronomical dawn (Sun -18°)</td><td className="text-right text-ui-text">{jdToTime(data.conditions.astro_dawn)}</td></tr>
                <tr><td className="text-ui-text-dim">Civil dawn (Sun -6°)</td><td className="text-right text-ui-text">{jdToTime(data.conditions.civil_dawn)}</td></tr>
                <tr><td className="text-ui-text-dim">Sunrise</td><td className="text-right text-sev-warn">{jdToTime(data.conditions.sunrise)}</td></tr>
                <tr><td className="text-ui-text-dim">Solar noon</td><td className="text-right text-ui-text">{jdToTime(data.conditions.solar_noon)}</td></tr>
                <tr><td className="text-ui-text-dim">Sunset</td><td className="text-right text-sev-warn">{jdToTime(data.conditions.sunset)}</td></tr>
                <tr><td className="text-ui-text-dim">Civil dusk</td><td className="text-right text-ui-text">{jdToTime(data.conditions.civil_dusk)}</td></tr>
                <tr><td className="text-ui-text-dim">Astronomical dusk (full dark)</td><td className="text-right text-ui-text">{jdToTime(data.conditions.astro_dusk)}</td></tr>
                <tr className="border-t border-ui-border"><td className="text-ui-text-dim pt-1">Moonrise</td><td className="text-right text-ui-text">{jdToTime(data.conditions.moonrise)}</td></tr>
                <tr><td className="text-ui-text-dim">Moonset</td><td className="text-right text-ui-text">{jdToTime(data.conditions.moonset)}</td></tr>
                <tr className="border-t border-ui-border"><td className="text-ui-text-dim pt-1">Moon phase</td><td className="text-right text-ui-text">{data.conditions.moon_phase_label}</td></tr>
                <tr><td className="text-ui-text-dim">Illuminated</td><td className="text-right font-mono text-ui-text">{(data.conditions.moon_phase_fraction * 100).toFixed(1)}%</td></tr>
                <tr><td className="text-ui-text-dim">Moon age</td><td className="text-right font-mono text-ui-text">{data.conditions.moon_age_days.toFixed(1)} days</td></tr>
              </tbody>
            </table>
          </div>
          <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
            <h3 className="text-sm font-semibold text-ui-accent mb-2">Dark-sky window</h3>
            <DarkSkyBar conditions={data.conditions} jd={data.jd} />
          </div>
        </div>
      )}

      {data && (
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
            <h3 className="text-sm font-semibold text-sev-ok mb-2">Planets above horizon</h3>
            {data.planets.length === 0 && <p className="text-ui-text-faint">— none right now —</p>}
            <table className="w-full font-mono">
              <tbody>
                {data.planets.map((p) => (
                  <tr key={p.name}>
                    <td className="text-ui-text">
                      <span style={{ color: `rgb(${Math.round(p.color[0]*255)},${Math.round(p.color[1]*255)},${Math.round(p.color[2]*255)})` }}>●</span>
                      {' '}{p.name}
                    </td>
                    <td className="text-ui-text-dim text-right">{p.mag.toFixed(2)}</td>
                    <td className="text-ui-text-dim text-right">alt {p.alt.toFixed(1)}°</td>
                    <td className="text-ui-text-dim text-right">az {p.az.toFixed(1)}°</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
            <h3 className="text-sm font-semibold text-ui-accent mb-2">Brightest stars overhead</h3>
            <table className="w-full font-mono">
              <tbody>
                {[...data.stars].sort((a, b) => a.mag - b.mag).slice(0, 10).map((s) => (
                  <tr key={s.name + s.ra}>
                    <td className="text-ui-text truncate max-w-[140px]">{s.name}</td>
                    <td className="text-ui-text-dim text-right">V {s.mag.toFixed(2)}</td>
                    <td className="text-ui-text-dim text-right">alt {s.alt.toFixed(1)}°</td>
                    <td className="text-ui-text-dim text-right">az {s.az.toFixed(1)}°</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="mt-3 text-[11px] text-ui-text-dim space-y-1">
        <p>• Zenith-centered azimuthal equidistant projection (paper-planisphere style). North = top, East = right.</p>
        <p>• Outer rim = horizon. Center = directly overhead. Concentric circles at 30° / 60° altitude.</p>
        <p>• Atmospheric refraction not corrected — actual horizon may differ by ~0.5°.</p>
      </div>
    </div>
  );
}

/** Visual 24-hour bar showing day / twilight / dark-sky windows. */
function DarkSkyBar({ conditions, jd }: { conditions: DayConditions; jd: number }) {
  // Reference midnight UT of the displayed JD's day.
  const baseJd = Math.floor(jd - 0.5) + 0.5;
  const minutes = (j: number | null): number =>
    j === null ? -1 : Math.max(0, Math.min(1440, Math.round((j - baseJd) * 1440)));

  const sr = minutes(conditions.sunrise);
  const ss = minutes(conditions.sunset);
  const cd = minutes(conditions.civil_dawn);
  const cu = minutes(conditions.civil_dusk);
  const ad = minutes(conditions.astro_dawn);
  const au = minutes(conditions.astro_dusk);
  const W = 100;  // percent

  // Render fills from earliest segment to latest.
  // Order: pre-astro-dawn (dark), astro twilight, civil twilight, day, civil twilight, astro twilight, post-astro-dusk (dark).
  const x = (m: number) => (m / 1440) * W;

  return (
    <div>
      <div className="relative h-7 w-full bg-sev-info/80 rounded overflow-hidden border border-ui-border">
        {/* astronomical twilight bands */}
        {ad > 0 && cd > 0 && (
          <div className="absolute h-full bg-sev-info/70" style={{ left: `${x(ad)}%`, width: `${x(cd) - x(ad)}%` }} />
        )}
        {/* civil twilight bands */}
        {cd > 0 && sr > 0 && (
          <div className="absolute h-full bg-sev-info/60" style={{ left: `${x(cd)}%`, width: `${x(sr) - x(cd)}%` }} />
        )}
        {/* day */}
        {sr > 0 && ss > 0 && (
          <div className="absolute h-full bg-sev-warn/70" style={{ left: `${x(sr)}%`, width: `${x(ss) - x(sr)}%` }} />
        )}
        {/* evening civil */}
        {ss > 0 && cu > 0 && (
          <div className="absolute h-full bg-sev-info/60" style={{ left: `${x(ss)}%`, width: `${x(cu) - x(ss)}%` }} />
        )}
        {/* evening astro */}
        {cu > 0 && au > 0 && (
          <div className="absolute h-full bg-sev-info/70" style={{ left: `${x(cu)}%`, width: `${x(au) - x(cu)}%` }} />
        )}
        {/* "now" marker */}
        <div className="absolute top-0 h-full w-px bg-sev-crit"
             style={{ left: `${x(minutes(jd))}%` }} title="Selected time" />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-ui-text-faint font-mono">
        <span>00 UT</span><span>06</span><span>12</span><span>18</span><span>24</span>
      </div>
      <div className="mt-2 text-[11px] text-ui-text space-y-0.5">
        <div><span className="inline-block w-3 h-3 mr-1 align-middle bg-sev-info/10 border border-ui-border-strong" />night</div>
        <div><span className="inline-block w-3 h-3 mr-1 align-middle bg-sev-info/70 border border-indigo-600" />astronomical twilight (Sun -18° to -6°)</div>
        <div><span className="inline-block w-3 h-3 mr-1 align-middle bg-sev-info/60 border border-blue-400" />civil twilight (Sun -6° to 0°)</div>
        <div><span className="inline-block w-3 h-3 mr-1 align-middle bg-sev-warn/70 border border-yellow-300" />day (Sun above horizon)</div>
        <div><span className="inline-block w-3 h-px mr-1 align-middle bg-sev-crit" /> red line = your selected time</div>
      </div>
    </div>
  );
}
