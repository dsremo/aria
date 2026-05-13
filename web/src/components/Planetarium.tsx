/**
 * Planetarium — star field view with relativistic effects.
 *
 * Shows what the crew would see out the window during interstellar
 * travel. Renders ~9000 stars from the Yale Bright Star Catalog
 * (BSC5, all naked-eye to V≈6.5) plus Sun, Moon, and all 8 planets +
 * Pluto with proper motion, relativistic aberration, Doppler color
 * shift, and Standish 1992 planetary ephemeris.
 *
 * Data sources:
 *   /api/star_field   — BSC5 stars (configurable epoch + β)
 *   /api/solar_system — Sun/Moon/planets at requested Julian Date
 */

import { useEffect, useRef, useState } from 'react';
import { Planetarium3D } from './Planetarium3D';

interface StarData {
  ra: number;
  dec: number;
  mag: number;
  r: number;
  g: number;
  b: number;
  name: string;
  hip_id: number;
}

interface ConstellationSegment {
  from: { ra: number; dec: number };
  to: { ra: number; dec: number };
}

interface ConstellationCentroid {
  abbr: string;
  name: string;
  ra: number;
  dec: number;
}

interface ExoplanetHost {
  name: string;
  ra: number;
  dec: number;
  mag: number;
  distance_ly: number;
  n_planets: number;
  description: string;
}

interface MessierEntry {
  m: number;
  ngc: string;
  name: string;
  ra: number;
  dec: number;
  mag: number;
  size_amaj: number;
  size_amin: number;
  obj_class: string;
}

interface StarFieldResponse {
  stars: StarData[];
  constellations: Record<string, ConstellationSegment[]>;
  constellation_centroids?: ConstellationCentroid[];
  messier?: MessierEntry[];
  exoplanet_hosts?: ExoplanetHost[];
  epoch_years_from_j2000: number;
  beta: number;
  velocity_direction: number[];
}

interface SolarBody {
  name: string;
  kind: 'sun' | 'moon' | 'planet' | 'asteroid' | 'comet' | 'satellite';
  ra: number;
  dec: number;
  magnitude: number;
  distance_au: number;
  color: [number, number, number];
}

interface SolarResponse {
  jd: number;
  bodies: SolarBody[];
  counts: { majors: number; small: number; moons?: number };
}

type Projection = 'equirectangular' | 'stereographic_n' | 'stereographic_s';

/** One hover-target rendered to the canvas this frame.  Populated
 *  during the draw loop; consumed by the mouse-move handler so we can
 *  identify whatever is closest to the cursor.
 *  Coords are in *native canvas pixel space* (1200 × 600), not DOM
 *  coordinates — the mouse handler rescales client events to match. */
interface HitTarget {
  x: number;
  y: number;
  r: number;                  // hit-radius (size + a small tolerance)
  kind: 'star' | 'sun' | 'moon' | 'planet' | 'asteroid' | 'comet'
      | 'satellite' | 'messier' | 'exoplanet';
  label: string;
  detail: string;             // "V=1.4 · 25 ly" etc. rendered below label
}

export function Planetarium() {
  const [data, setData] = useState<StarFieldResponse | null>(null);
  const [solar, setSolar] = useState<SolarResponse | null>(null);
  const [years, setYears] = useState(0);
  const [beta, setBeta] = useState(0);
  const [magLimit, setMagLimit] = useState(6.0);
  const [showConstellations, setShowConstellations] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [showPlanets, setShowPlanets] = useState(true);
  const [showMessier, setShowMessier] = useState(true);
  const [showConstellationLabels, setShowConstellationLabels] = useState(true);
  const [showExoplanets, setShowExoplanets] = useState(true);
  const [projection, setProjection] = useState<Projection>('equirectangular');
  const [viewMode, setViewMode] = useState<'2d' | '3d'>('2d');
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const hitsRef   = useRef<HitTarget[]>([]);
  const [hover, setHover] = useState<null | {
    x: number; y: number; hit: HitTarget;
  }>(null);

  useEffect(() => {
    const params = new URLSearchParams({
      years: years.toString(),
      beta: beta.toString(),
      vx: '1',
      vy: '0',
      vz: '0',
    });
    fetch(`/api/star_field?${params}`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => {});
  }, [years, beta]);

  // Solar-system bodies — fetch on mount and when epoch slider changes.
  useEffect(() => {
    // J2000.0 = JD 2451545.0; one Julian year = 365.25 d.
    const jd = 2451545.0 + years * 365.25;
    fetch(`/api/solar_system?jd=${jd}&mag_limit=13.5`)
      .then((r) => r.json())
      .then(setSolar)
      .catch(() => {});
  }, [years]);

  useEffect(() => {
    if (!data || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;

    // Clear with dark space color
    ctx.fillStyle = '#02050a';
    ctx.fillRect(0, 0, W, H);

    // Reset hit list — we repopulate it as items render so the hover
    // handler below can identify whatever is under the cursor with no
    // round-trip to the backend.
    const hits: HitTarget[] = [];

    // Project RA/Dec to 2D with selectable projection
    const project = (ra: number, dec: number): [number, number] | null => {
      if (projection === 'equirectangular') {
        // Simple: RA horizontal, Dec vertical
        return [(ra / 360) * W, ((90 - dec) / 180) * H];
      }
      // Stereographic (polar-centered) — less distortion near the pole
      const isNorth = projection === 'stereographic_n';
      const decRad = (dec * Math.PI) / 180;
      const raRad = (ra * Math.PI) / 180;
      // Projection distance from pole: r = 2*tan((90-|lat|)/2) for the hemisphere
      const colat = isNorth ? Math.PI / 2 - decRad : Math.PI / 2 + decRad;
      if (colat > Math.PI / 2) return null; // other hemisphere — hide
      const r = Math.tan(colat / 2);
      const rScale = Math.min(W, H) * 0.48;
      const cx = W / 2;
      const cy = H / 2;
      const signY = isNorth ? -1 : 1; // north pole at top
      return [
        cx + rScale * r * Math.cos(raRad),
        cy + signY * rScale * r * Math.sin(raRad),
      ];
    };

    // Draw constellation lines
    if (showConstellations) {
      ctx.strokeStyle = 'rgba(100, 150, 200, 0.3)';
      ctx.lineWidth = 1;
      for (const [, segments] of Object.entries(data.constellations)) {
        for (const seg of segments) {
          const p1 = project(seg.from.ra, seg.from.dec);
          const p2 = project(seg.to.ra, seg.to.dec);
          if (p1 === null || p2 === null) continue;
          const [x1, y1] = p1;
          const [x2, y2] = p2;
          // Skip lines that wrap around (for equirectangular)
          if (projection !== 'equirectangular' || Math.abs(x2 - x1) < W / 2) {
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.stroke();
          }
        }
      }
    }

    // Constellation centroid labels — drawn before stars so labels sit
    // behind any bright stars near them.
    if (showConstellationLabels && data.constellation_centroids) {
      ctx.fillStyle = 'rgba(120, 170, 220, 0.75)';
      ctx.font = '11px monospace';
      ctx.textAlign = 'center';
      for (const c of data.constellation_centroids) {
        const pt = project(c.ra, c.dec);
        if (pt === null) continue;
        const [x, y] = pt;
        ctx.fillText(c.abbr, x, y);
      }
      ctx.textAlign = 'left';
    }

    // Draw stars (mag-limited)
    let drawn = 0;
    for (const star of data.stars) {
      if (star.mag > magLimit) continue;
      const pt = project(star.ra, star.dec);
      if (pt === null) continue;
      const [x, y] = pt;
      drawn++;
      // Size based on magnitude (brighter = bigger). Pohlmann-style scaling.
      const size = Math.max(0.5, 4.5 - star.mag * 0.55);
      const alpha = Math.max(0.25, Math.min(1, (magLimit + 0.5 - star.mag) / (magLimit + 1)));

      ctx.fillStyle = `rgba(${Math.round(star.r * 255)}, ${Math.round(
        star.g * 255,
      )}, ${Math.round(star.b * 255)}, ${alpha})`;
      ctx.beginPath();
      ctx.arc(x, y, size, 0, Math.PI * 2);
      ctx.fill();
      hits.push({
        x, y,
        r: Math.max(size, 3),
        kind: 'star',
        label: star.name || `HIP ${star.hip_id}`,
        detail: `V=${star.mag.toFixed(2)} · RA ${star.ra.toFixed(2)}° · Dec ${star.dec.toFixed(2)}°`,
      });

      // Glow for very bright stars
      if (star.mag < 1.5) {
        const gradient = ctx.createRadialGradient(x, y, size, x, y, size * 4);
        gradient.addColorStop(0, `rgba(${Math.round(star.r * 255)}, ${Math.round(star.g * 255)}, ${Math.round(star.b * 255)}, 0.4)`);
        gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(x, y, size * 4, 0, Math.PI * 2);
        ctx.fill();
      }

      // Labels for named stars
      if (showLabels && star.name && star.mag < 2.0) {
        ctx.fillStyle = 'rgba(180, 200, 220, 0.8)';
        ctx.font = '11px monospace';
        ctx.fillText(star.name, x + size + 3, y + 3);
      }
    }
    (canvas as any)._lastDrawn = drawn;

    // Draw Messier deep-sky objects (galaxies/clusters/nebulae) above
    // stars but below planets. Each object class gets its own glyph.
    if (showMessier && data.messier) {
      for (const obj of data.messier) {
        if (obj.mag > magLimit + 2.0) continue; // give DSO a little extra latitude
        const pt = project(obj.ra, obj.dec);
        if (pt === null) continue;
        const [x, y] = pt;
        // Apparent radius: use major axis but cap so M31 doesn't fill the canvas.
        const px_per_arcmin = (Math.min(W, H) / 360) * 0.5;
        const r = Math.max(2.5, Math.min(18, obj.size_amaj * px_per_arcmin * 0.25));

        switch (obj.obj_class) {
          case 'G': {
            // Galaxy: faint elliptical outline, axis-aligned
            ctx.strokeStyle = 'rgba(180,140,200,0.65)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.ellipse(x, y, r, r * (obj.size_amin / obj.size_amaj), 0, 0, Math.PI * 2);
            ctx.stroke();
            break;
          }
          case 'GC':
            // Globular cluster: circle with a + cross (Stellarium convention)
            ctx.strokeStyle = 'rgba(220,180,120,0.75)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.moveTo(x - r, y); ctx.lineTo(x + r, y);
            ctx.moveTo(x, y - r); ctx.lineTo(x, y + r);
            ctx.stroke();
            break;
          case 'OC': {
            // Open cluster: dashed circle
            ctx.strokeStyle = 'rgba(200,220,140,0.7)';
            ctx.lineWidth = 1;
            ctx.setLineDash([2, 2]);
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.stroke();
            ctx.setLineDash([]);
            break;
          }
          case 'N':
          case 'PN': {
            // Nebula: soft glow disk
            const g = ctx.createRadialGradient(x, y, 0, x, y, r * 1.5);
            g.addColorStop(0, 'rgba(160,180,255,0.55)');
            g.addColorStop(1, 'rgba(0,0,0,0)');
            ctx.fillStyle = g;
            ctx.beginPath();
            ctx.arc(x, y, r * 1.5, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = 'rgba(160,180,255,0.65)';
            ctx.lineWidth = 0.5;
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.stroke();
            break;
          }
          case 'SR':
            // SNR: dotted circle
            ctx.strokeStyle = 'rgba(255,140,140,0.7)';
            ctx.setLineDash([1, 2]);
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.stroke();
            ctx.setLineDash([]);
            break;
          default:
            ctx.strokeStyle = 'rgba(180,180,180,0.5)';
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.stroke();
        }

        if (showLabels && obj.mag < 7.0) {
          ctx.fillStyle = 'rgba(200,180,220,0.8)';
          ctx.font = '9px monospace';
          ctx.fillText(`M${obj.m}`, x + r + 3, y + 3);
        }
        hits.push({
          x, y, r: Math.max(r, 5),
          kind: 'messier',
          label: `M${obj.m} · ${obj.name}`,
          detail: `${obj.obj_class} · V=${obj.mag.toFixed(1)} · NGC ${obj.ngc}`,
        });
      }
    }

    // Exoplanet hosts — small diamond markers to distinguish from regular stars.
    if (showExoplanets && data.exoplanet_hosts) {
      for (const h of data.exoplanet_hosts) {
        const pt = project(h.ra, h.dec);
        if (pt === null) continue;
        const [x, y] = pt;
        const size = Math.max(3, 6 - h.mag * 0.4);
        ctx.strokeStyle = 'rgba(244, 114, 182, 0.85)';
        ctx.lineWidth = 1.2;
        // Draw diamond (square rotated 45°)
        ctx.beginPath();
        ctx.moveTo(x, y - size);
        ctx.lineTo(x + size, y);
        ctx.lineTo(x, y + size);
        ctx.lineTo(x - size, y);
        ctx.closePath();
        ctx.stroke();
        // Planet count dot inside
        ctx.fillStyle = 'rgba(244, 114, 182, 0.85)';
        ctx.beginPath();
        ctx.arc(x, y, 1, 0, Math.PI * 2);
        ctx.fill();
        if (showLabels && h.mag < 5.5) {
          ctx.fillStyle = 'rgba(244, 114, 182, 0.85)';
          ctx.font = '9px monospace';
          ctx.fillText(`${h.name} (${h.n_planets}p)`, x + size + 3, y - 4);
        }
        hits.push({
          x, y, r: size + 3,
          kind: 'exoplanet',
          label: `${h.name} · ${h.n_planets} planet${h.n_planets > 1 ? 's' : ''}`,
          detail: `V=${h.mag.toFixed(1)} · ${h.distance_ly.toFixed(1)} ly · ${h.description}`,
        });
      }
    }

    // Draw solar system bodies on top so they overlay nearby stars.
    if (showPlanets && solar) {
      for (const b of solar.bodies) {
        const pt = project(b.ra, b.dec);
        if (pt === null) continue;
        const [x, y] = pt;

        const isMajor = b.kind === 'sun' || b.kind === 'moon' || b.kind === 'planet';
        const isComet = b.kind === 'comet';
        const isSatellite = b.kind === 'satellite';

        // Disk size: bigger for brighter / closer bodies. Sun & Moon get
        // a special bigger disk so they read as bodies, not stars. Planetary
        // satellites stay small — they cluster around their parent planet.
        let size = isMajor
          ? Math.max(2.5, 6.0 - b.magnitude * 0.5)
          : isSatellite
            ? Math.max(1.0, 3.5 - b.magnitude * 0.2)
            : Math.max(1.5, 5.5 - b.magnitude * 0.3);
        if (b.kind === 'sun')  size = 9;
        if (b.kind === 'moon') size = 8;

        const r = Math.round(b.color[0] * 255);
        const g = Math.round(b.color[1] * 255);
        const bl = Math.round(b.color[2] * 255);

        // Halo (skipped for asteroids — they're tiny points like stars)
        if (isMajor || isComet) {
          const halo = ctx.createRadialGradient(x, y, size * 0.5, x, y, size * 3);
          halo.addColorStop(0, `rgba(${r},${g},${bl},${isComet ? 0.35 : 0.55})`);
          halo.addColorStop(1, 'rgba(0,0,0,0)');
          ctx.fillStyle = halo;
          ctx.beginPath();
          ctx.arc(x, y, size * 3, 0, Math.PI * 2);
          ctx.fill();
        }

        // Disk
        ctx.fillStyle = `rgb(${r},${g},${bl})`;
        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.fill();

        // Outline — distinguishes planets/Sun/Moon from stars; comets get
        // a faint trailing tail line in the (-RA) direction.
        if (isMajor) {
          ctx.strokeStyle = 'rgba(255,255,255,0.7)';
          ctx.lineWidth = 1;
          ctx.stroke();
        } else if (isComet) {
          ctx.strokeStyle = 'rgba(180,200,255,0.5)';
          ctx.lineWidth = 0.8;
          ctx.stroke();
          // Tail: short stub away from the sun (approx anti-RA direction).
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.lineTo(x - size * 5, y - size * 2);
          ctx.strokeStyle = 'rgba(180,200,255,0.45)';
          ctx.stroke();
        }

        if (showLabels) {
          // Show labels for majors always; for satellites/asteroids/comets
          // only when bright enough to avoid crowding.
          const labelOK = isMajor || b.magnitude < (isSatellite ? 8.5 : 10.0);
          if (labelOK) {
            ctx.fillStyle = isMajor
              ? 'rgba(255,230,180,0.95)'
              : isComet ? 'rgba(180,200,255,0.85)'
              : isSatellite ? 'rgba(220,200,255,0.85)'
              : 'rgba(220,210,180,0.75)';
            ctx.font = isMajor ? '12px monospace' : '10px monospace';
            // Strip the "(N) " prefix from MPC asteroid names for compactness.
            const lbl = isMajor
              ? b.name.charAt(0).toUpperCase() + b.name.slice(1)
              : b.name.replace(/^\(\d+\)\s*/, '');
            ctx.fillText(lbl, x + size + 4, y - 4);
          }
        }

        const cleanName = isMajor
          ? b.name.charAt(0).toUpperCase() + b.name.slice(1)
          : b.name.replace(/^\(\d+\)\s*/, '');
        hits.push({
          x, y, r: Math.max(size + 2, 5),
          kind: b.kind,
          label: cleanName,
          detail: `${b.kind} · V=${b.magnitude.toFixed(2)} · ${b.distance_au.toFixed(3)} AU`,
        });
      }
    }
    // Commit hit list for the mouse handler.
    hitsRef.current = hits;
  }, [data, solar, showConstellations, showConstellationLabels, showLabels, showPlanets, showMessier, showExoplanets, projection, magLimit]);

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Planetarium — Star Field & Solar System</h2>
        <p className="text-xs text-ui-text-dim">
          {data
            ? `${data.stars.length} HYG stars (V≤${magLimit.toFixed(1)} drawn)`
            : 'Loading…'}
          {solar && ` · ${solar.counts.majors} planets+Sun+Moon · ${solar.counts.small} asteroids/comets`}
          {solar?.counts.moons !== undefined && ` · ${solar.counts.moons} moons`}
          {data?.messier && ` · ${data.messier.length} Messier`}
          {data?.constellation_centroids && ` · ${Object.keys(data.constellations).length}/${data.constellation_centroids.length} constellations drawn`}
          {' · '}Epoch: J2000 + {years}y · β = {beta.toFixed(3)} ({(beta * 299792.458).toFixed(0)} km/s)
        </p>
      </div>

      {/* Controls */}
      <div className="mb-3 bg-ui-bg-1/60 border border-ui-border rounded p-3 space-y-2">
        <div>
          <label className="text-xs text-ui-text-dim">
            Epoch offset (years from J2000): {years}
          </label>
          <input
            type="range"
            min={-500}
            max={2000}
            step={10}
            value={years}
            onChange={(e) => setYears(Number(e.target.value))}
            className="w-full"
          />
        </div>
        <div>
          <label className="text-xs text-ui-text-dim">
            Spacecraft velocity β = v/c: {beta.toFixed(3)} (
            {(beta * 299792.458).toFixed(0)} km/s toward +X)
          </label>
          <input
            type="range"
            min={0}
            max={0.9}
            step={0.01}
            value={beta}
            onChange={(e) => setBeta(Number(e.target.value))}
            className="w-full"
          />
        </div>
        <div>
          <label className="text-xs text-ui-text-dim">
            Magnitude cut-off (V): {magLimit.toFixed(1)}  — naked-eye ≈ 6, suburban ≈ 5
          </label>
          <input
            type="range"
            min={1.0}
            max={6.5}
            step={0.1}
            value={magLimit}
            onChange={(e) => setMagLimit(Number(e.target.value))}
            className="w-full"
          />
        </div>
        <div className="flex gap-3 text-xs flex-wrap">
          <label className="flex items-center gap-1 text-ui-text">
            <input
              type="checkbox"
              checked={showConstellations}
              onChange={(e) => setShowConstellations(e.target.checked)}
            />
            Constellation lines
          </label>
          <label className="flex items-center gap-1 text-ui-text">
            <input
              type="checkbox"
              checked={showConstellationLabels}
              onChange={(e) => setShowConstellationLabels(e.target.checked)}
            />
            Constellation labels (88 IAU)
          </label>
          <label className="flex items-center gap-1 text-ui-text">
            <input
              type="checkbox"
              checked={showLabels}
              onChange={(e) => setShowLabels(e.target.checked)}
            />
            Labels
          </label>
          <label className="flex items-center gap-1 text-ui-text">
            <input
              type="checkbox"
              checked={showPlanets}
              onChange={(e) => setShowPlanets(e.target.checked)}
            />
            Sun / Moon / Planets
          </label>
          <label className="flex items-center gap-1 text-ui-text">
            <input
              type="checkbox"
              checked={showMessier}
              onChange={(e) => setShowMessier(e.target.checked)}
            />
            Messier deep-sky
          </label>
          <label className="flex items-center gap-1 text-ui-text">
            <input
              type="checkbox"
              checked={showExoplanets}
              onChange={(e) => setShowExoplanets(e.target.checked)}
            />
            Exoplanet hosts {data?.exoplanet_hosts && `(${data.exoplanet_hosts.length})`}
          </label>
          <label className="flex items-center gap-1 text-ui-text">
            <span>Projection:</span>
            <select
              value={projection}
              onChange={(e) => setProjection(e.target.value as Projection)}
              disabled={viewMode === '3d'}
              className="bg-ui-bg-2 border border-ui-border-strong rounded px-1 disabled:opacity-40"
            >
              <option value="equirectangular">Equirectangular (full sky)</option>
              <option value="stereographic_n">Stereographic — North</option>
              <option value="stereographic_s">Stereographic — South</option>
            </select>
          </label>
          <label className="flex items-center gap-1 text-ui-text ml-auto">
            <span>View:</span>
            <div className="flex rounded overflow-hidden border border-ui-border-strong">
              <button onClick={() => setViewMode('2d')}
                      className={`px-2 py-0.5 ${viewMode === '2d'
                        ? 'bg-ui-accent/40 text-white'
                        : 'bg-ui-bg-2 text-ui-text hover:bg-ui-bg-3'}`}>
                2D
              </button>
              <button onClick={() => setViewMode('3d')}
                      className={`px-2 py-0.5 ${viewMode === '3d'
                        ? 'bg-ui-accent/40 text-white'
                        : 'bg-ui-bg-2 text-ui-text hover:bg-ui-bg-3'}`}>
                3D dome
              </button>
            </div>
          </label>
        </div>
      </div>

      {viewMode === '3d' && data && (
        <Planetarium3D
          stars={data.stars}
          constellations={data.constellations}
          messier={data.messier}
          solarBodies={solar?.bodies as any}
          showConstellations={showConstellations}
          showMessier={showMessier}
          showPlanets={showPlanets}
          showLabels={showLabels}
          magLimit={magLimit}
          height={600} />
      )}

      {/* Star field canvas with cursor hover identification.  The
          canvas is rendered at its natural 1200×600 but displayed at
          `w-full`, so we have to rescale client-event coordinates back
          to canvas space before checking against hitsRef.  Distance
          check uses Euclidean distance to the stored (x,y); the
          closest hit within its radius wins.  Nothing within range →
          clear the tooltip so it doesn't linger. */}
      <div
        className={`relative bg-ui-bg-0/80 border border-ui-border rounded overflow-hidden ${viewMode === '3d' ? 'hidden' : ''}`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const canvas = canvasRef.current;
          if (!canvas) return;
          const rect = canvas.getBoundingClientRect();
          const scaleX = canvas.width  / rect.width;
          const scaleY = canvas.height / rect.height;
          const cx = (e.clientX - rect.left) * scaleX;
          const cy = (e.clientY - rect.top)  * scaleY;
          let best: HitTarget | null = null;
          let bestDist = Infinity;
          for (const h of hitsRef.current) {
            const dx = h.x - cx, dy = h.y - cy;
            const d2 = dx * dx + dy * dy;
            const r2 = h.r * h.r * 4;    // 2× tolerance for easier pickup
            if (d2 < r2 && d2 < bestDist) { best = h; bestDist = d2; }
          }
          if (best) {
            setHover({
              x: e.clientX - rect.left,
              y: e.clientY - rect.top,
              hit: best,
            });
          } else if (hover) {
            setHover(null);
          }
        }}
      >
        <canvas ref={canvasRef} width={1200} height={600} className="w-full block" />
        {hover && (
          <div
            className="absolute pointer-events-none z-10 px-2 py-1 rounded
                       border border-ui-accent bg-ui-bg-1/95 text-xs shadow-lg
                       whitespace-nowrap"
            style={{
              left: Math.min(hover.x + 14, 800),
              top:  Math.max(hover.y - 28, 4),
            }}>
            <div className="text-[10px] uppercase tracking-wider text-ui-accent">{hover.hit.kind}</div>
            <div className="text-ui-text font-semibold">{hover.hit.label}</div>
            <div className="text-ui-text-dim font-mono text-[11px]">{hover.hit.detail}</div>
          </div>
        )}
      </div>

      {/* Info panel */}
      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
          <div className="text-[11px] text-ui-text">
            <p className="mb-2">
              <strong>Relativistic effects:</strong>
            </p>
            <ul className="space-y-1 text-ui-text-dim list-disc pl-4">
              <li>
                At β = 0.1: stars shift ~5.7° toward direction of motion (forward)
              </li>
              <li>
                At β = 0.5: most stars compress into forward hemisphere
              </li>
              <li>
                At β = 0.9: nearly all stars appear in a narrow forward cone
              </li>
              <li>Forward stars blue-shift, aft stars red-shift (Doppler)</li>
              <li>
                Proper motion: Barnard's Star moves ~10.4&quot;/yr
              </li>
            </ul>
          </div>
        </div>

        <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
          <div className="text-[11px] text-ui-text">
            <p className="mb-2">
              <strong>Solar System bodies — apparent geocentric (Standish 1992):</strong>
            </p>
            {solar ? (
              <div className="max-h-72 overflow-y-auto">
                <table className="w-full text-[11px] font-mono">
                  <thead className="text-ui-text-faint sticky top-0 bg-ui-bg-1">
                    <tr>
                      <th className="text-left">Body</th>
                      <th className="text-left">Kind</th>
                      <th className="text-right">V mag</th>
                      <th className="text-right">RA (°)</th>
                      <th className="text-right">Dec (°)</th>
                      <th className="text-right">d (AU)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {solar.bodies.map((b) => (
                      <tr key={b.name} className={b.kind === 'planet' || b.kind === 'sun' || b.kind === 'moon' ? '' : 'opacity-80'}>
                        <td className="text-ui-text truncate max-w-[160px]">
                          <span style={{ color: `rgb(${Math.round(b.color[0]*255)},${Math.round(b.color[1]*255)},${Math.round(b.color[2]*255)})` }}>●</span>{' '}
                          {b.name}
                        </td>
                        <td className="text-ui-text-faint">{b.kind}</td>
                        <td className="text-ui-text-dim text-right">{b.magnitude.toFixed(2)}</td>
                        <td className="text-ui-text-dim text-right">{b.ra.toFixed(1)}</td>
                        <td className="text-ui-text-dim text-right">{b.dec.toFixed(1)}</td>
                        <td className="text-ui-text-dim text-right">{b.distance_au.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-ui-text-faint">Loading solar system…</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
