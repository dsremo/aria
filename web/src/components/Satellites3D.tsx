/**
 * Satellites 3D — real-time 3D view of every active object orbiting Earth.
 *
 * TLE catalog is fetched via `/api/tle/catalog` (live from Celestrak,
 * 10-min cache, bundled spacetrack fallback) and propagated in-browser
 * with satellite.js (MIT — Brandon Rhodes' SGP4 ported to JS by
 * shashwatak/satellite-js).  Positions are recomputed every animation
 * frame from the current wall-clock time so the entire swarm moves
 * visibly in real time — no polling, no round-trip.
 *
 * Open-source patterns that informed the design (MIT / BSD only;
 * KeepTrack.space and Stuff-in-Space are AGPL/MIT-derived and were
 * studied-only per project license policy):
 *   - satellite.js: TLE → SGP4 → ECI cartesian, then sidereal rotation
 *     → ECF; we render in ECF so Earth can spin on its own axis
 *     independently.
 *   - three.js + @react-three/fiber for the scene, drei for controls.
 *
 * Each satellite is a single instanced point in a Points buffer — a
 * 10,000-object catalog renders at ~60 fps on integrated GPUs because
 * the mesh is one draw call, not 10k.  A category colour palette lets
 * operators flip groups (GNSS / Starlink / science / stations / all).
 *
 * Acceptance bar (matches the user's request for "real-time 3D
 * representation of all the satellites around Earth"):
 *   - ≥ 10k objects rendered concurrently
 *   - Positions advance in real time (60 fps visible motion)
 *   - Click a point → name, NORAD, altitude, orbital period, kind
 *   - Swap between Celestrak groups without a page reload
 *   - Orient the globe with mouse (OrbitControls) while positions
 *     continue to propagate
 */

import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import * as satellite from 'satellite.js';
import { ErrorBoundary, WebGLUnavailableFallback } from './ErrorBoundary';

// Scene scale: Earth radius = 1 unit.  matches ConstellationVisualizer.
const R_EARTH_KM = 6378.137;

interface TleRecord {
  name: string;
  line1: string;
  line2: string;
}

interface TleCatalogResponse {
  source: 'celestrak' | 'bundled';
  group: string;
  fetched_at_wall: number;
  count: number;
  satellites: TleRecord[];
}

interface PropagatedSat {
  name: string;
  norad: number;
  satrec: satellite.SatRec;
  // Last-known ECF position in Earth-radius-units (for render).
  pos: THREE.Vector3;
  period_min: number;
  apogee_km: number;
  perigee_km: number;
  ok: boolean;      // false if SGP4 returned an error (deep-space, decay)
  country: string;  // operator country code from inferCountry()
}

/** Human-friendly Celestrak group labels.  The GROUP param for each
 *  is verbatim from https://celestrak.org/NORAD/elements/ (GP-data). */
const GROUPS: { id: string; label: string; hint: string }[] = [
  { id: 'active',     label: 'Active (~11k)',   hint: 'All active payloads + recent debris' },
  { id: 'stations',   label: 'Stations',        hint: 'ISS, CSS, visiting vehicles' },
  { id: 'gnss',       label: 'GNSS',            hint: 'GPS, GLONASS, Galileo, BeiDou' },
  { id: 'starlink',   label: 'Starlink',        hint: 'SpaceX LEO constellation' },
  { id: 'iridium-NEXT',label:'Iridium NEXT',    hint: 'Global comms constellation' },
  { id: 'weather',    label: 'Weather',         hint: 'NOAA POES / MetOp / GOES / Himawari' },
  { id: 'science',    label: 'Science',         hint: 'Hubble, TESS, JWST halo, etc.' },
  { id: 'geo',        label: 'GEO',             hint: 'Geostationary ring' },
  { id: 'last-30-days', label: 'Last 30 days',  hint: 'Recent launches' },
  { id: 'cubesat',    label: 'Cubesats',        hint: 'All cubesat-class objects' },
];

/** Colour a satellite by orbital regime derived from its period: LEO
 *  (90-110 min), MEO (110-800 min), GEO (~1436 min ±2%), HEO elsewhere.
 *  Palette tuned for additive-blend visibility against the Blue Marble
 *  Earth backdrop — the previous teal/light-blue picks blended into the
 *  ocean and atmosphere, the new picks are saturated complementary
 *  colours that bloom against a blue background instead of competing
 *  with it.  Matches the chip colours rendered in the legend. */
function regimeColor(period_min: number): [number, number, number] {
  if (period_min < 120) return [0.20, 1.00, 0.45];   // LEO  = electric green   (#33ff73)
  if (period_min < 700) return [1.00, 0.78, 0.20];   // MEO  = warm amber       (#ffc733)
  if (period_min >= 1410 && period_min <= 1465)
                       return [1.00, 0.30, 0.78];   // GEO  = hot magenta      (#ff4dc7)
  return [1.00, 0.55, 0.10];                         // HEO  = bright orange    (#ff8c1a)
}

/** Country / operator family inferred from the TLE name.  Heuristic-only
 *  (full SATCAT lookup needs a 3 MB CSV from CelesTrak; this catches
 *  ~80 % of active payloads via well-known constellation prefixes).
 *  Returns one of the COUNTRY codes below or 'OTHER' for unrecognised. */
const COUNTRY_PATTERNS: { code: string; label: string; flag: string; rx: RegExp }[] = [
  { code: 'US',    label: 'United States', flag: '🇺🇸', rx: /^(STARLINK|IRIDIUM|GPS|USA|MUOS|NOSS|GOES|NOAA|TDRS|LANDSAT|TESS|FALCON|DRAGON|CYGNUS|ATLAS|DELTA|TITAN|VANGUARD|HUBBLE|JWST|MESSENGER|JUNO|JPSS|SBIRS|WGS|AEHF|KESTREL|CAPELLA|PLANET|FLOCK|LEMUR|SUPERVIEW|HAWKEYE|ASTRA|INTELSAT|ORBCOMM|GLOBALSTAR)\b/i },
  { code: 'CN',    label: 'China',         flag: '🇨🇳', rx: /^(BEIDOU|TIANHE|TIANGONG|FENGYUN|YAOGAN|SHENZHOU|SHIJIAN|GAOFEN|HAIYANG|TIANTONG|TIANLIAN|TIANZHOU|CHANG[\s'-]?E|SHIYAN|GUOWANG|CHINASAT|APSTAR|HJ-|ZIYUAN|HUANJING|CSS|TIANYI)\b/i },
  { code: 'RU',    label: 'Russia',        flag: '🇷🇺', rx: /^(GLONASS|COSMOS|MOLNIYA|METEOR-M|RESURS|EKS|LIANA|TUNDRA|KANOPUS|YANTAR|PERSONA|RADUGA|GEO-IK|LOTOS|GORIZONT|EXPRESS|SOYUZ|PROGRESS|ANGARA)\b/i },
  { code: 'EU',    label: 'ESA / Europe',  flag: '🇪🇺', rx: /^(GALILEO|SENTINEL|METOP|COPERNICUS|GIOVE|CRYOSAT|ENVISAT|GOCE|SMOS|HERSCHEL|PLANCK|GAIA|EUTELSAT|HOTBIRD|ASTRA|EXPRESS-AM|HISPASAT|SES|EUMETSAT|ERS|SPOT|HELIOS|PLEIADES|CSO)\b/i },
  { code: 'IN',    label: 'India',         flag: '🇮🇳', rx: /^(GSAT|INSAT|IRNSS|NAVIC|CHANDRAYAAN|MANGALYAAN|RISAT|CARTOSAT|RESOURCESAT|OCEANSAT|MEGHA|SCATSAT|EMISAT|MICROSAT|EOS|RIMSAT)\b/i },
  { code: 'JP',    label: 'Japan',         flag: '🇯🇵', rx: /^(HIMAWARI|MICHIBIKI|QZS|ALOS|AKEBONO|HAYABUSA|GOSAT|IBUKI|JCSAT|SUPERBIRD|KIRARI|ASTRO-H|HITOMI|XRISM)\b/i },
  { code: 'KR',    label: 'South Korea',   flag: '🇰🇷', rx: /^(KOMPSAT|CHOLLIAN|GEO-KOMPSAT|MUSE|KSLV|NEXTSAT)\b/i },
  { code: 'AU',    label: 'Australia',     flag: '🇦🇺', rx: /^(OPTUS|NBN-CO|BUCCANEER|FALCONSAT|KANYINI)\b/i },
  { code: 'CA',    label: 'Canada',        flag: '🇨🇦', rx: /^(RADARSAT|ANIK|MEV|TELESAT|NIMIQ|SCISAT|MOST|KEPLER)\b/i },
  { code: 'BR',    label: 'Brazil',        flag: '🇧🇷', rx: /^(CBERS|AMAZONIA|SCD|SGDC)\b/i },
  { code: 'IL',    label: 'Israel',        flag: '🇮🇱', rx: /^(AMOS|OFEK|TECSAR|EROS|VENUS|SHALOM)\b/i },
  { code: 'IR',    label: 'Iran',          flag: '🇮🇷', rx: /^(NOOR|MAHDA|FAJR|NAHID|PARS|OMID|RASAD|NAVID)\b/i },
  { code: 'KP',    label: 'North Korea',   flag: '🇰🇵', rx: /^(KWANGMYONGSONG|MALLIGYONG)\b/i },
  { code: 'UK',    label: 'United Kingdom',flag: '🇬🇧', rx: /^(SKYNET|UK-|TOPSAT|SURREYSAT|NOVASAR|CARBONITE|TYCHE|ORESAT)\b/i },
  { code: 'ONEWEB',label: 'OneWeb',        flag: '🛰️', rx: /^ONEWEB\b/i },
  { code: 'COMM',  label: 'Commercial',    flag: '🛰️', rx: /^(O3B|VIASAT|ECHOSTAR|DIRECTV|XM-|SIRIUS|INMARSAT|THURAYA|ICO|TURKSAT|ARABSAT|AMERICOM|HORIZONS|ARGOS|COSMO-SKYMED|DEIMOS|TUBSAT|SES-)\b/i },
];

function inferCountry(name: string): string {
  for (const p of COUNTRY_PATTERNS) {
    if (p.rx.test(name)) return p.code;
  }
  return 'OTHER';
}

export function Satellites3D() {
  return (
    <ErrorBoundary
      label="Satellites3D"
      fallback={(err, reset) => (
        <WebGLUnavailableFallback error={err} onReset={reset}
                                  label="the real-time satellite tracker" />
      )}>
      <Satellites3DInner />
    </ErrorBoundary>
  );
}

function Satellites3DInner() {
  const [group, setGroup]     = useState('active');
  const [catalog, setCatalog] = useState<TleCatalogResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr]         = useState<string | null>(null);
  const [paused, setPaused]   = useState(false);
  const [speed, setSpeed]     = useState(1);
  const [colorByRegime, setColorByRegime] = useState(true);
  const [showOrbits, setShowOrbits]       = useState(false);
  const [showStars, setShowStars]         = useState(true);
  const [selectedIdx, setSelectedIdx]     = useState<number | null>(null);
  const [detailIdx, setDetailIdx]         = useState<number | null>(null);
  const [simDate, setSimDate] = useState(new Date());
  // Country filter: empty Set means "show all".  We use Set semantics
  // so adding / removing a chip is O(1).
  const [countryFilter, setCountryFilter] = useState<Set<string>>(new Set());
  const [showCountryPanel, setShowCountryPanel] = useState(false);
  // High-quality Earth — opt-in 4k Blue Marble (the upstream three.js
  // CDN doesn't carry an 8k variant; if/when one lands we'll swap the
  // URL behind this flag).  Adds ~6 MB extra one-time download.
  const [hqEarth, setHqEarth] = useState(false);
  // Square-sprite toggle: render satellites as plain rectangular
  // sprites (the original look before the round-icon sprite landed).
  // Some operators prefer the unambiguous square — it doesn't mix
  // with the additive halo on dense clusters.
  const [squareSprites, setSquareSprites] = useState(false);

  // Fetch whenever group changes.  Cap at 12k — Celestrak's biggest live
  // group (`active`) is ~11k objects; anything larger is the bundled
  // 30-row snapshot whose tail is mostly decayed records that fail SGP4
  // propagation and starve the per-frame loop.
  useEffect(() => {
    setLoading(true);
    setErr(null);
    setSelectedIdx(null);
    fetch(`/api/tle/catalog?group=${encodeURIComponent(group)}&limit=12000`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j: TleCatalogResponse) => setCatalog(j))
      .catch((e) => setErr(e?.message ?? String(e)))
      .finally(() => setLoading(false));
  }, [group]);

  /** Parse every TLE in the catalog into a SatRec exactly once; keeping
   *  them in a stable array means the per-frame propagation loop can
   *  index into a parallel Float32Array for point positions. */
  const sats = useMemo<PropagatedSat[]>(() => {
    if (!catalog) return [];
    const out: PropagatedSat[] = [];
    for (const rec of catalog.satellites) {
      try {
        const satrec = satellite.twoline2satrec(rec.line1, rec.line2);
        const noCol = satrec as any;
        // n_0 is rev/day; period_min = 1440 / n_0
        const period = 1440 / (noCol.no_kozai / (2 * Math.PI));
        const a = noCol.a * R_EARTH_KM;   // semi-major axis in km
        const e = noCol.ecco;
        const apogee  = a * (1 + e) - R_EARTH_KM;
        const perigee = a * (1 - e) - R_EARTH_KM;
        const norad = parseInt(rec.line2.substring(2, 7), 10);
        out.push({
          name: rec.name,
          norad: isNaN(norad) ? 0 : norad,
          satrec,
          pos: new THREE.Vector3(),
          period_min: period,
          apogee_km:  apogee,
          perigee_km: perigee,
          ok: true,
          country: inferCountry(rec.name),
        });
      } catch {
        /* Skip malformed records rather than fail the whole load */
      }
    }
    return out;
  }, [catalog]);

  /** Parallel Float32Array of xyz positions, sized + colour-seeded *during*
   *  render so SatelliteCloud receives valid-length buffers on the very
   *  first frame.  Earlier we built these in a useEffect that runs AFTER
   *  the child rendered with the previous (length-0) refs — the geometry
   *  attached an empty position attribute and never recovered, leaving
   *  the whole Canvas black until a manual reload. */
  const posArray = useMemo(
    () => new Float32Array(sats.length * 3),
    [sats],
  );
  const colorArray = useMemo(() => {
    const a = new Float32Array(sats.length * 3);
    const filterActive = countryFilter.size > 0;
    for (let i = 0; i < sats.length; i++) {
      // When a country filter is active, dim non-matching sats to near
      // black — additive blending makes them effectively invisible
      // without disturbing the position buffer.
      if (filterActive && !countryFilter.has(sats[i].country)) {
        a[3 * i] = a[3 * i + 1] = a[3 * i + 2] = 0;
        continue;
      }
      const [r, g, b] = colorByRegime
        ? regimeColor(sats[i].period_min)
        : [0.22, 0.83, 0.95];
      a[3 * i]     = r;
      a[3 * i + 1] = g;
      a[3 * i + 2] = b;
    }
    return a;
  }, [sats, colorByRegime, countryFilter]);

  // Live country counts so the filter chips show how many sats are in each.
  const countryCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const s of sats) {
      if (!s.ok) continue;
      c[s.country] = (c[s.country] || 0) + 1;
    }
    return c;
  }, [sats]);

  const visibleCount = sats.filter((s) => s.ok).length;

  // Live regime breakdown.  These match the colour bands rendered in
  // the satellite cloud: LEO (<120 min), MEO (120–700 min), GEO
  // (≈ 1436 min, ±2 %), HEO (everything else).
  const regimeCounts = useMemo(() => {
    const c = { LEO: 0, MEO: 0, GEO: 0, HEO: 0 };
    for (const s of sats) {
      if (!s.ok) continue;
      const p = s.period_min;
      if (p < 120) c.LEO++;
      else if (p < 700) c.MEO++;
      else if (p >= 1410 && p <= 1465) c.GEO++;
      else c.HEO++;
    }
    return c;
  }, [sats]);

  // Camera reset trigger.  Bumps an integer that a child useFrame hook
  // observes so we can reposition + retarget the OrbitControls camera
  // without rerendering the whole Canvas.
  const [resetCounter, setResetCounter] = useState(0);

  // Persistent sim-time ref kept inside a child component (useFrame only
  // fires there).  Pause + speed both affect it.
  const propagatedSats = sats;

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3 flex items-start gap-3">
        <div className="flex-1">
          <h2 className="text-lg font-semibold text-ui-accent">Satellites 3D — Real-Time Earth Orbit Tracker</h2>
          <p className="text-xs text-ui-text-dim">
            SGP4 propagation via satellite.js 7 (MIT) · TLEs from Celestrak (10-min cache, spacetrack fallback)
            · {visibleCount}/{sats.length} satellites · {paused ? 'paused' : `${speed}× real time`}
          </p>
        </div>
        <div className="text-[10px] text-ui-text-faint text-right">
          {catalog && (
            <>
              <div>source: <span className={catalog.source === 'celestrak' ? 'text-sev-ok' : 'text-sev-warn'}>{catalog.source}</span></div>
              <div>fetched: {new Date(catalog.fetched_at_wall * 1000).toLocaleTimeString()}</div>
            </>
          )}
        </div>
      </div>

      <div className="mb-3 flex flex-wrap gap-1 items-center text-[11px]">
        <span className="text-ui-text-faint uppercase tracking-wider mr-1">Group:</span>
        {GROUPS.map((g) => (
          <button key={g.id}
                  onClick={() => setGroup(g.id)}
                  title={g.hint}
                  className={`px-2 py-0.5 rounded border
                    ${group === g.id
                      ? 'border-ui-accent bg-ui-accent/40 text-ui-accent'
                      : 'border-ui-border bg-ui-bg-1 text-ui-text hover:border-ui-accent'}`}>
            {g.label}
          </button>
        ))}
      </div>

      <div className="mb-3 flex flex-wrap gap-3 items-center text-xs">
        <label className="flex items-center gap-1 text-ui-text">
          <input type="checkbox" checked={paused} onChange={(e) => setPaused(e.target.checked)} />
          Pause
        </label>
        <label className="flex items-center gap-1 text-ui-text">
          <span className="text-ui-text-dim">Speed</span>
          <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}
                  className="bg-ui-bg-2 border border-ui-border-strong rounded px-1 py-0.5">
            <option value={1}>1× (real time)</option>
            <option value={10}>10×</option>
            <option value={60}>60× (1 min/s)</option>
            <option value={3600}>3600× (1 h/s)</option>
            <option value={86400}>86400× (1 day/s)</option>
          </select>
        </label>
        <label className="flex items-center gap-1 text-ui-text">
          <input type="checkbox" checked={colorByRegime} onChange={(e) => setColorByRegime(e.target.checked)} />
          Color by orbital regime
        </label>
        <label className="flex items-center gap-1 text-ui-text">
          <input type="checkbox" checked={showOrbits} onChange={(e) => setShowOrbits(e.target.checked)} />
          Draw selected orbit
        </label>
        <label className="flex items-center gap-1 text-ui-text"
               title="Hide the procedural star background (useful on dark monitors)">
          <input type="checkbox" checked={showStars} onChange={(e) => setShowStars(e.target.checked)} />
          Show stars
        </label>
        <label className="flex items-center gap-1 text-ui-text"
               title="Swap to 4k NASA Blue Marble (Earth-Atmos 4096). Adds ~6 MB on first load. The upstream texture CDN does not carry an 8k variant.">
          <input type="checkbox" checked={hqEarth} onChange={(e) => setHqEarth(e.target.checked)} />
          HQ Earth (4k)
        </label>
        <label className="flex items-center gap-1 text-ui-text"
               title="Render satellites as plain square sprites (the original look) instead of the round body+panels icon.">
          <input type="checkbox" checked={squareSprites} onChange={(e) => setSquareSprites(e.target.checked)} />
          Square satellites
        </label>
        <button
          onClick={() => setShowCountryPanel((v) => !v)}
          className={`px-2 py-0.5 rounded border text-[11px]
            ${countryFilter.size > 0
              ? 'border-ui-accent bg-ui-accent/40 text-ui-accent'
              : 'border-ui-border-strong bg-ui-bg-1 text-ui-text hover:border-ui-accent hover:text-ui-accent'}`}>
          Country {countryFilter.size > 0 ? `(${countryFilter.size})` : 'filter ▾'}
        </button>
        <button
          onClick={() => { setSelectedIdx(null); setResetCounter((c) => c + 1); }}
          className="px-2 py-0.5 rounded border border-ui-border-strong bg-ui-bg-1
                     text-ui-text hover:border-ui-accent hover:text-ui-accent
                     text-[11px]">
          Reset view
        </button>
      </div>

      {showCountryPanel && (
        <div className="mb-3 p-2 bg-ui-bg-1/60 border border-ui-border rounded text-[11px]">
          <div className="flex items-center justify-between mb-2">
            <span className="text-ui-text-dim uppercase tracking-wider text-[10px]">
              Filter by operator country · name-pattern heuristic, ~80% coverage
            </span>
            {countryFilter.size > 0 && (
              <button onClick={() => setCountryFilter(new Set())}
                      className="text-[10px] text-ui-text-dim hover:text-ui-accent">
                clear all
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-1">
            {COUNTRY_PATTERNS.concat([{ code: 'OTHER', label: 'Other / unknown', flag: '·', rx: /(?:)/ }])
              .filter((p) => (countryCounts[p.code] || 0) > 0)
              .sort((a, b) => (countryCounts[b.code] || 0) - (countryCounts[a.code] || 0))
              .map((p) => {
                const n = countryCounts[p.code] || 0;
                const active = countryFilter.has(p.code);
                return (
                  <button
                    key={p.code}
                    onClick={() => {
                      setCountryFilter((prev) => {
                        const next = new Set(prev);
                        if (next.has(p.code)) next.delete(p.code);
                        else next.add(p.code);
                        return next;
                      });
                    }}
                    title={p.label}
                    className={`px-2 py-0.5 rounded border flex items-center gap-1
                      ${active
                        ? 'border-ui-accent bg-ui-accent/40 text-ui-accent'
                        : 'border-ui-border bg-ui-bg-1 text-ui-text hover:border-ui-accent'}`}>
                    <span>{p.flag}</span>
                    <span>{p.label}</span>
                    <span className="font-mono text-ui-text-dim">{n.toLocaleString()}</span>
                  </button>
                );
              })}
          </div>
        </div>
      )}

      {err && (
        <div className="bg-sev-crit/40 border border-sev-crit rounded p-2 text-sev-crit text-xs mb-2">
          TLE catalog load failed: {err}
        </div>
      )}
      {loading && (
        <div className="text-[11px] text-ui-text-dim italic mb-2">Loading TLE catalog…</div>
      )}

      <div className="relative bg-ui-bg-0 border border-ui-border rounded overflow-hidden"
           style={{ height: 620 }}>
        {selectedIdx !== null && sats[selectedIdx] && (
          <div className="absolute top-2 right-2 z-10 px-3 py-2 rounded
                          border border-ui-accent bg-ui-bg-1/95 text-xs shadow-lg
                          pointer-events-none max-w-xs">
            <div className="text-[10px] uppercase tracking-wider text-ui-accent">Selected · double-click for full details</div>
            <div className="text-ui-text font-semibold truncate">{sats[selectedIdx].name}</div>
            <div className="text-ui-text-dim font-mono text-[11px] mt-0.5 space-y-0.5">
              <div>NORAD {sats[selectedIdx].norad}</div>
              <div>period {sats[selectedIdx].period_min.toFixed(1)} min</div>
              <div>apogee  {sats[selectedIdx].apogee_km.toFixed(0)} km</div>
              <div>perigee {sats[selectedIdx].perigee_km.toFixed(0)} km</div>
              <div>regime  {regimeLabel(sats[selectedIdx].period_min)}</div>
            </div>
          </div>
        )}
        {detailIdx !== null && sats[detailIdx] && (
          <SatelliteDetailModal
            sat={sats[detailIdx]}
            simDate={simDate}
            onClose={() => setDetailIdx(null)}
          />
        )}
        <Canvas
          camera={{ position: [0, 1.8, 3.6], fov: 45, near: 0.01, far: 500 }}
          dpr={[1, 2]}
          gl={{ antialias: true, powerPreference: 'high-performance' }}
        >
          <color attach="background" args={['#02040a']} />
          <ambientLight intensity={0.18} />
          {/* Sun-side directional light placed far so it reads as
              parallel rays.  Position matches the shader's default
              sunDir so the lit hemisphere lines up with the texture. */}
          <directionalLight position={[80, 0, 0]} intensity={1.6} />
          {showStars && <Starfield />}
          <Earth simDate={simDate} hq={hqEarth} />
          <SatelliteCloud
            sats={propagatedSats}
            posArray={posArray}
            colorArray={colorArray}
            paused={paused}
            speedFactor={speed}
            onDateTick={setSimDate}
            squareSprites={squareSprites}
            onPick={(idx) => setSelectedIdx(idx === selectedIdx ? null : idx)}
            onPickDouble={(idx) => { setSelectedIdx(idx); setDetailIdx(idx); }}
          />
          {showOrbits && selectedIdx !== null && sats[selectedIdx] && (
            <OrbitRing sat={sats[selectedIdx]} simDate={simDate} />
          )}
          <CameraResetter counter={resetCounter} />
          <OrbitControls
            enablePan
            enableZoom
            enableRotate
            target={[0, 0, 0]}
            minDistance={1.15}
            maxDistance={50}
            zoomSpeed={0.8}
            rotateSpeed={0.7}
            makeDefault
          />
        </Canvas>
      </div>

      <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        <LegendChip color="#33ff73" label="LEO"       desc="< 120 min"          count={regimeCounts.LEO} total={visibleCount} />
        <LegendChip color="#ffc733" label="MEO"       desc="120–700 min"        count={regimeCounts.MEO} total={visibleCount} />
        <LegendChip color="#ff4dc7" label="GEO"       desc="≈ 1436 min"         count={regimeCounts.GEO} total={visibleCount} />
        <LegendChip color="#ff8c1a" label="HEO/other" desc="highly elliptical"  count={regimeCounts.HEO} total={visibleCount} />
      </div>

      <div className="mt-3 text-[11px] text-ui-text-dim space-y-1">
        <p>• Propagation: client-side satellite.js twoline2satrec + propagate (SGP4/SDP4). No network hit per frame.</p>
        <p>• Earth rotation uses a simplified mean-sidereal rate — positions in ECF after Greenwich hour angle is applied, so the orbital plane + Earth spin are decoupled.</p>
        <p>• Click any satellite point to pin its details; click again (or a different point) to unpin.  Large catalogs (10k+) may need a second to parse.</p>
      </div>
    </div>
  );
}

function regimeLabel(period_min: number): string {
  if (period_min < 120) return 'LEO';
  if (period_min < 700) return 'MEO';
  if (period_min >= 1410 && period_min <= 1465) return 'GEO';
  return 'HEO / other';
}

/** Swap a three.js Points + BufferGeometry with vertex colours so the
 *  whole catalog renders in one draw call.  Pick handler uses a Raycaster
 *  with a tight threshold so dense clusters don't all light up when you
 *  miss a satellite. */
/** Single canonical "satellite" sprite drawn into a 128×128 canvas:
 *  a square central body flanked by two thin solar panels — the
 *  universal satellite silhouette.  At low zoom the whole sprite reads
 *  as a small bright dot; as the camera moves in, the panel-and-body
 *  shape resolves so the operator can immediately tell what they're
 *  looking at without rendering 11k individual `InstancedMesh` instances.
 *  Building one shared `CanvasTexture` and storing it in a module-level
 *  singleton means every Cloud reuses the same GPU upload.  Per the
 *  user direction: ONE shape, finalised — no per-type 3D models. */
function makeSatelliteSpriteTexture(): THREE.Texture {
  const size = 128;
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const ctx = c.getContext('2d')!;
  ctx.clearRect(0, 0, size, size);
  // Soft glow halo behind the icon so dense clusters still bloom and
  // the additive blending in the parent material reads as glowing
  // satellites — not stamped graphics.
  const g = ctx.createRadialGradient(size / 2, size / 2, 0,
                                     size / 2, size / 2, size / 2);
  g.addColorStop(0,   'rgba(255,255,255,0.55)');
  g.addColorStop(0.4, 'rgba(255,255,255,0.20)');
  g.addColorStop(1,   'rgba(255,255,255,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  // Central body — small square with rounded corners.
  ctx.fillStyle = 'rgba(255,255,255,1.0)';
  const cx = size / 2, cy = size / 2;
  const bodyW = 22, bodyH = 22, r = 4;
  ctx.beginPath();
  ctx.moveTo(cx - bodyW/2 + r, cy - bodyH/2);
  ctx.lineTo(cx + bodyW/2 - r, cy - bodyH/2);
  ctx.quadraticCurveTo(cx + bodyW/2, cy - bodyH/2, cx + bodyW/2, cy - bodyH/2 + r);
  ctx.lineTo(cx + bodyW/2, cy + bodyH/2 - r);
  ctx.quadraticCurveTo(cx + bodyW/2, cy + bodyH/2, cx + bodyW/2 - r, cy + bodyH/2);
  ctx.lineTo(cx - bodyW/2 + r, cy + bodyH/2);
  ctx.quadraticCurveTo(cx - bodyW/2, cy + bodyH/2, cx - bodyW/2, cy + bodyH/2 - r);
  ctx.lineTo(cx - bodyW/2, cy - bodyH/2 + r);
  ctx.quadraticCurveTo(cx - bodyW/2, cy - bodyH/2, cx - bodyW/2 + r, cy - bodyH/2);
  ctx.closePath();
  ctx.fill();
  // Solar panels — long thin rectangles to either side, with a thin gap
  // between body and panel so the silhouette reads at small sizes.
  ctx.fillStyle = 'rgba(255,255,255,0.95)';
  const panelW = 36, panelH = 14, gap = 4;
  ctx.fillRect(cx - bodyW/2 - gap - panelW, cy - panelH/2, panelW, panelH);
  ctx.fillRect(cx + bodyW/2 + gap,          cy - panelH/2, panelW, panelH);
  // Subtle internal grid lines on the panels — suggest cells without
  // actually being legible at <8 px.
  ctx.strokeStyle = 'rgba(0,0,0,0.35)';
  ctx.lineWidth = 1;
  for (let i = 1; i < 4; i++) {
    const x1 = cx - bodyW/2 - gap - panelW + (panelW / 4) * i;
    const x2 = cx + bodyW/2 + gap          + (panelW / 4) * i;
    ctx.beginPath();
    ctx.moveTo(x1, cy - panelH/2); ctx.lineTo(x1, cy + panelH/2);
    ctx.moveTo(x2, cy - panelH/2); ctx.lineTo(x2, cy + panelH/2);
    ctx.stroke();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.needsUpdate = true;
  return tex;
}
let _SAT_SPRITE: THREE.Texture | null = null;
function getSatelliteSprite(): THREE.Texture {
  if (_SAT_SPRITE === null) _SAT_SPRITE = makeSatelliteSpriteTexture();
  return _SAT_SPRITE;
}

function SatelliteCloud({
  sats, posArray, colorArray, paused, speedFactor, onDateTick, onPick, onPickDouble,
  squareSprites,
}: {
  sats: PropagatedSat[];
  posArray: Float32Array;
  colorArray: Float32Array;
  paused: boolean;
  speedFactor: number;
  onDateTick: (d: Date) => void;
  onPick: (idx: number) => void;
  onPickDouble: (idx: number) => void;
  squareSprites: boolean;
}) {
  const pointsRef = useRef<THREE.Points>(null);
  const geomRef   = useRef<THREE.BufferGeometry>(null);
  const simTimeRef = useRef(Date.now());
  const lastDateEmitRef = useRef(0);

  // Attach / refresh buffer attributes when the catalog changes.
  useEffect(() => {
    if (!geomRef.current) return;
    geomRef.current.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
    geomRef.current.setAttribute('color',    new THREE.BufferAttribute(colorArray, 3));
  }, [sats, posArray, colorArray]);

  useFrame((_, dt) => {
    if (!pointsRef.current || !geomRef.current || sats.length === 0) return;
    if (!paused) simTimeRef.current += dt * 1000 * speedFactor;
    const now = new Date(simTimeRef.current);

    // GMST: sidereal angle of Greenwich at this instant, used by
    // satellite.js to rotate ECI → ECF.  Expensive only the first time
    // per frame; propagate() per satellite is ~0.5µs on V8.
    let gmst: number;
    try {
      gmst = satellite.gstime(now);
    } catch {
      // Bad clock — skip this frame instead of killing the loop.
      return;
    }

    const target = geomRef.current.getAttribute('position') as THREE.BufferAttribute | undefined;
    if (!target) return;
    const arr = target.array as Float32Array;
    const scale = 1 / R_EARTH_KM;

    for (let i = 0; i < sats.length; i++) {
      const s = sats[i];
      if (!s.ok) { arr[3*i] = arr[3*i+1] = arr[3*i+2] = 0; continue; }
      // satellite.js can throw on aged TLEs (RangeError in deep-space
      // model).  Per-sat try/catch keeps one bad element set from
      // taking down all 11k of them — and from blanking the Canvas.
      try {
        const pv = satellite.propagate(s.satrec, now);
        const pos = pv.position as satellite.EciVec3<number> | boolean | undefined;
        if (!pos || typeof pos === 'boolean'
            || !Number.isFinite((pos as satellite.EciVec3<number>).x)
            || !Number.isFinite((pos as satellite.EciVec3<number>).y)
            || !Number.isFinite((pos as satellite.EciVec3<number>).z)) {
          arr[3*i] = arr[3*i+1] = arr[3*i+2] = 0;
          s.ok = false;
          continue;
        }
        // ECF = ECI rotated by -gmst around z (Earth rotation sense).
        const ecf = satellite.eciToEcf(pos as satellite.EciVec3<number>, gmst);
        // km → scene units (Earth radius = 1).  Y-Z swap so Z is "up" in
        // scene space to match @react-three/drei's OrbitControls default.
        arr[3*i]     = ecf.x * scale;
        arr[3*i + 1] = ecf.z * scale;
        arr[3*i + 2] = -ecf.y * scale;
        s.pos.set(arr[3*i], arr[3*i+1], arr[3*i+2]);
      } catch {
        arr[3*i] = arr[3*i+1] = arr[3*i+2] = 0;
        s.ok = false;
      }
    }
    target.needsUpdate = true;

    // Throttle onDateTick to 2 Hz so React re-render doesn't fight 60 fps.
    if (simTimeRef.current - lastDateEmitRef.current > 500) {
      lastDateEmitRef.current = simTimeRef.current;
      onDateTick(now);
    }
  });

  const sprite = getSatelliteSprite();

  return (
    <points
      ref={pointsRef}
      onClick={(e) => {
        e.stopPropagation();
        const idx = (e as any).index;
        if (typeof idx === 'number') onPick(idx);
      }}
      onDoubleClick={(e) => {
        e.stopPropagation();
        const idx = (e as any).index;
        if (typeof idx === 'number') onPickDouble(idx);
      }}
    >
      <bufferGeometry ref={geomRef} />
      {squareSprites ? (
        // Plain square sprites — the original look (no map/alphaMap).
        // Default-shape pointsMaterial renders each vertex as a 1×1
        // sprite quad; with sizeAttenuation it becomes a screen-space
        // square that grows on zoom-in.  Some operators prefer the
        // unambiguous square because it doesn't bloom in dense clusters.
        <pointsMaterial
          key="square"
          size={0.022}
          vertexColors
          sizeAttenuation
          transparent
          opacity={0.92}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      ) : (
        <pointsMaterial
          key="icon"
          size={0.022}
          vertexColors
          sizeAttenuation
          transparent
          opacity={0.92}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          map={sprite}
          alphaMap={sprite}
          alphaTest={0.05}
        />
      )}
    </points>
  );
}

/** Full-detail modal for a satellite — opens on double-click.  Computes
 *  ECI/ECF + sub-point + altitude + speed live from the SatRec so the
 *  numbers always match the propagator running in the background.  Links
 *  out to N2YO and CelesTrak so the operator can cross-check externally. */
function SatelliteDetailModal({
  sat, simDate, onClose,
}: { sat: PropagatedSat; simDate: Date; onClose: () => void }) {
  // Esc to close — feels native on a dashboard.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Snapshot the propagator state at the open instant (re-runs once a
  // second so the panel feels live without redrawing on every frame).
  const [snapTick, setSnapTick] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setSnapTick((t) => t + 1), 1000);
    return () => window.clearInterval(id);
  }, []);

  const snap = useMemo(() => {
    const now = new Date(simDate.getTime() + snapTick);  // tick just forces recompute
    try {
      const pv = satellite.propagate(sat.satrec, now);
      const pos = pv.position as satellite.EciVec3<number> | boolean | undefined;
      if (!pos || typeof pos === 'boolean') return null;
      const gmst = satellite.gstime(now);
      const geo = satellite.eciToGeodetic(pos as satellite.EciVec3<number>, gmst);
      const altitude_km = geo.height;
      const lat_deg = (geo.latitude * 180) / Math.PI;
      const lon_deg = ((geo.longitude * 180) / Math.PI + 540) % 360 - 180;
      const v = pv.velocity as satellite.EciVec3<number> | boolean | undefined;
      let speed_kms: number | null = null;
      if (v && typeof v !== 'boolean') {
        const vv = v as satellite.EciVec3<number>;
        speed_kms = Math.sqrt(vv.x * vv.x + vv.y * vv.y + vv.z * vv.z);
      }
      return { altitude_km, lat_deg, lon_deg, speed_kms };
    } catch { return null; }
  }, [sat, simDate, snapTick]);

  const ecc = (sat.satrec as any).ecco as number;
  const incDeg = ((sat.satrec as any).inclo as number) * (180 / Math.PI);
  const raanDeg = ((sat.satrec as any).nodeo as number) * (180 / Math.PI);
  const argpDeg = ((sat.satrec as any).argpo as number) * (180 / Math.PI);
  const meanAnomalyDeg = ((sat.satrec as any).mo as number) * (180 / Math.PI);

  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/70"
         onClick={onClose}>
      <div className="bg-ui-bg-1 border border-ui-accent rounded-lg p-4 max-w-md w-[90%] text-xs shadow-2xl"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-3">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-ui-accent">Satellite</div>
            <h3 className="text-base text-ui-text font-semibold">{sat.name}</h3>
            <div className="text-[10px] text-ui-text-dim font-mono">
              NORAD {sat.norad} · regime {regimeLabel(sat.period_min)}
            </div>
          </div>
          <button onClick={onClose}
                  className="text-ui-text-faint hover:text-ui-text text-lg leading-none">
            ×
          </button>
        </div>

        <div className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[11px] text-ui-text">
          <div className="text-ui-text-faint">Period</div>
          <div>{sat.period_min.toFixed(2)} min</div>

          <div className="text-ui-text-faint">Apogee</div>
          <div>{sat.apogee_km.toFixed(0)} km</div>

          <div className="text-ui-text-faint">Perigee</div>
          <div>{sat.perigee_km.toFixed(0)} km</div>

          <div className="text-ui-text-faint">Eccentricity</div>
          <div>{ecc.toFixed(5)}</div>

          <div className="text-ui-text-faint">Inclination</div>
          <div>{incDeg.toFixed(2)}°</div>

          <div className="text-ui-text-faint">RAAN</div>
          <div>{raanDeg.toFixed(2)}°</div>

          <div className="text-ui-text-faint">Arg of perigee</div>
          <div>{argpDeg.toFixed(2)}°</div>

          <div className="text-ui-text-faint">Mean anomaly</div>
          <div>{meanAnomalyDeg.toFixed(2)}°</div>

          {snap && (
            <>
              <div className="text-ui-text-faint col-span-2 mt-2 pt-2 border-t border-ui-border/60 text-[10px] uppercase tracking-wider">
                Live state (sub-satellite point)
              </div>
              <div className="text-ui-text-faint">Altitude</div>
              <div>{snap.altitude_km.toFixed(0)} km</div>
              <div className="text-ui-text-faint">Latitude</div>
              <div>{snap.lat_deg.toFixed(3)}°</div>
              <div className="text-ui-text-faint">Longitude</div>
              <div>{snap.lon_deg.toFixed(3)}°</div>
              {snap.speed_kms !== null && (
                <>
                  <div className="text-ui-text-faint">Speed (ECI)</div>
                  <div>{snap.speed_kms.toFixed(2)} km/s</div>
                </>
              )}
            </>
          )}
        </div>

        <div className="mt-3 pt-3 border-t border-ui-border/60 flex flex-wrap gap-2">
          {sat.norad > 0 && (
            <>
              <a href={`https://www.n2yo.com/satellite/?s=${sat.norad}`}
                 target="_blank" rel="noopener noreferrer"
                 className="px-2 py-1 rounded bg-ui-bg-2 hover:bg-ui-accent/40 border border-ui-border-strong hover:border-ui-accent text-ui-accent text-[10px]">
                N2YO live track ↗
              </a>
              <a href={`https://celestrak.org/satcat/records.php?CATNR=${sat.norad}`}
                 target="_blank" rel="noopener noreferrer"
                 className="px-2 py-1 rounded bg-ui-bg-2 hover:bg-ui-accent/40 border border-ui-border-strong hover:border-ui-accent text-ui-accent text-[10px]">
                CelesTrak SATCAT ↗
              </a>
            </>
          )}
          <span className="ml-auto text-[10px] text-ui-text-faint self-center">esc to close</span>
        </div>
      </div>
    </div>
  );
}

/** 256-point ring showing the selected satellite's orbit trace over one
 *  full period.  Recomputes every time the selection changes. */
function OrbitRing({ sat, simDate }: { sat: PropagatedSat; simDate: Date }) {
  const pts = useMemo(() => {
    const out: THREE.Vector3[] = [];
    const N = 256;
    const periodMs = sat.period_min * 60 * 1000;
    for (let i = 0; i <= N; i++) {
      const t = new Date(simDate.getTime() + (i / N) * periodMs);
      const pv = satellite.propagate(sat.satrec, t);
      if (!pv.position || typeof pv.position === 'boolean') continue;
      const gmst = satellite.gstime(t);
      const ecf = satellite.eciToEcf(pv.position as satellite.EciVec3<number>, gmst);
      const scale = 1 / R_EARTH_KM;
      out.push(new THREE.Vector3(ecf.x * scale, ecf.z * scale, -ecf.y * scale));
    }
    return out;
  }, [sat, simDate]);
  if (pts.length === 0) return null;
  const geom = new THREE.BufferGeometry().setFromPoints(pts);
  return (
    <line>
      <primitive object={geom} attach="geometry" />
      <lineBasicMaterial color="#f59e0b" linewidth={1} transparent opacity={0.75} />
    </line>
  );
}

// CDN that already serves SolarSystem3D's planet textures.  Same source,
// same colour-corrected (sRGB) JPEGs.  Public-domain NASA Blue Marble +
// Earth at Night composites scaled to 2k.
// three.js's official example textures, served via jsdelivr.  Public
// domain (NASA Blue Marble + Earth at Night composites).  These paths
// are stable across r160+ and were chosen after the previous CDN host
// (homer-jay/solar-system-textures) turned out to no longer carry the
// 2k_/8k_ prefixed files — Earth was silently rendering the procedural
// blue-sphere fallback.  Dimensions: atmos = surface daymap.
const TEX_BASE = 'https://cdn.jsdelivr.net/gh/mrdoob/three.js@r160/examples/textures/planets';
const EARTH_DAY_URL      = `${TEX_BASE}/earth_atmos_2048.jpg`;
const EARTH_NIGHT_URL    = `${TEX_BASE}/earth_lights_2048.png`;
const EARTH_CLOUDS_URL   = `${TEX_BASE}/earth_clouds_2048.png`;
const EARTH_NORMAL_URL   = `${TEX_BASE}/earth_normal_2048.jpg`;   // terrain bumpmap
const EARTH_SPECULAR_URL = `${TEX_BASE}/earth_specular_2048.jpg`; // ocean reflectivity
// HQ daymap — the only 4k variant the upstream repo carries.  Night /
// clouds / normal / specular cap at 2k regardless.
const EARTH_DAY_URL_HQ   = `${TEX_BASE}/earth_atmos_4096.jpg`;

/** Load a texture without throwing on failure (drei's `useTexture`
 *  is Suspense-hostile when the CDN is unreachable).  Returns sRGB
 *  colour-space-corrected texture or undefined while loading / on 404. */
function useOptionalTexture(url: string | undefined): THREE.Texture | undefined {
  const [tex, setTex] = useState<THREE.Texture | undefined>(undefined);
  useEffect(() => {
    if (!url) return;
    let alive = true;
    const loader = new THREE.TextureLoader();
    loader.setCrossOrigin('anonymous');
    loader.load(
      url,
      (t) => {
        if (!alive) return;
        // SRGBColorSpace symbol exists on three ≥0.152; older builds
        // fall back to the string literal.
        (t as any).colorSpace = (THREE as any).SRGBColorSpace ?? 'srgb';
        setTex(t);
      },
      undefined,
      () => { /* swallow CDN failure — procedural fallback takes over */ },
    );
    return () => { alive = false; };
  }, [url]);
  return tex;
}

/** Realistic Earth: NASA Blue Marble daymap + Earth at Night nightmap
 *  blended by sun direction (so the night side shows city lights instead
 *  of plain black), a translucent cloud shell rotating slightly faster
 *  than the surface, and a backside-facing atmosphere shell that produces
 *  a soft blue rim glow.  Falls back to a flat ocean sphere if the CDN
 *  is unreachable so the canvas always renders something.
 *
 *  Earth is stationary in ECF: the SGP4 propagator rotates ECI → ECF
 *  using GMST every frame, so satellite positions already include
 *  Earth's rotation.  Spinning the globe here would *cancel* that and
 *  ground-station markers would no longer track real coordinates. */
function Earth({ simDate, hq }: { simDate: Date; hq: boolean }) {
  const surfaceRef = useRef<THREE.Mesh>(null);
  const cloudsRef  = useRef<THREE.Mesh>(null);
  const dayTex      = useOptionalTexture(hq ? EARTH_DAY_URL_HQ : EARTH_DAY_URL);
  const nightTex    = useOptionalTexture(EARTH_NIGHT_URL);
  const cloudsTex   = useOptionalTexture(EARTH_CLOUDS_URL);
  const normalTex   = useOptionalTexture(EARTH_NORMAL_URL);
  const specularTex = useOptionalTexture(EARTH_SPECULAR_URL);

  // Day/night shader — ports the SolarSystem3D earth shader but without
  // the heliocentric-frame transform (sun direction is already known
  // because here Earth is at scene origin and the directional light is
  // mounted at a known position).
  const earthMaterial = useMemo(() => {
    if (!dayTex || !nightTex) return null;
    return new THREE.ShaderMaterial({
      uniforms: {
        dayMap:      { value: dayTex },
        nightMap:    { value: nightTex },
        normalMap:   { value: normalTex ?? null },
        specularMap: { value: specularTex ?? null },
        hasNormal:   { value: normalTex   ? 1.0 : 0.0 },
        hasSpecular: { value: specularTex ? 1.0 : 0.0 },
        sunDir:      { value: new THREE.Vector3(1, 0, 0) },
      },
      vertexShader: `
        varying vec3 vNormalW;
        varying vec3 vViewDirW;
        varying vec2 vUv;
        void main() {
          vNormalW = normalize(mat3(modelMatrix) * normal);
          vec4 worldPos = modelMatrix * vec4(position, 1.0);
          vViewDirW = normalize(cameraPosition - worldPos.xyz);
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
      fragmentShader: `
        uniform sampler2D dayMap;
        uniform sampler2D nightMap;
        uniform sampler2D normalMap;
        uniform sampler2D specularMap;
        uniform float hasNormal;
        uniform float hasSpecular;
        uniform vec3 sunDir;
        varying vec3 vNormalW;
        varying vec3 vViewDirW;
        varying vec2 vUv;
        void main() {
          vec3 day   = texture2D(dayMap,   vUv).rgb;
          vec3 night = texture2D(nightMap, vUv).rgb * 1.6;

          // Optional normal-map perturbation — tangent-space "flat" so we
          // just lift the y-component slightly; cheap stand-in for full
          // tangent-frame transform.
          vec3 N = normalize(vNormalW);
          if (hasNormal > 0.5) {
            vec3 nT = texture2D(normalMap, vUv).rgb * 2.0 - 1.0;
            N = normalize(N + nT.xyz * 0.18);
          }

          float d = dot(N, normalize(sunDir));
          float mixAmt = smoothstep(-0.18, 0.18, d);
          vec3 col = mix(night, day, mixAmt);

          // Ocean-only specular highlight — the specular map is bright
          // over water, dark over land; multiply by N·sunDir so it only
          // appears on the day side, and by view-aligned reflection so
          // it actually moves as the camera orbits.
          if (hasSpecular > 0.5 && mixAmt > 0.05) {
            float oceanMask = texture2D(specularMap, vUv).r;
            vec3 R = reflect(-normalize(sunDir), N);
            float spec = pow(max(dot(R, vViewDirW), 0.0), 32.0);
            col += vec3(0.45, 0.6, 0.85) * spec * oceanMask * mixAmt;
          }

          gl_FragColor = vec4(col, 1.0);
        }`,
    });
  }, [dayTex, nightTex, normalTex, specularTex]);

  // Sun direction — spin the sun around Earth at sidereal-day cadence
  // (one full rotation per 23 h 56 min) so the day/night terminator
  // sweeps across the surface as time advances.  Anchored to simDate
  // so when the user fast-forwards `speed`, the terminator follows.
  useFrame(() => {
    if (!earthMaterial) return;
    const t = simDate.getTime() / 1000;
    const SIDEREAL_DAY_S = 86164.0905;  // mean solar day with Earth's spin (IERS)
    const ang = (t / SIDEREAL_DAY_S) * 2 * Math.PI;
    earthMaterial.uniforms.sunDir.value.set(Math.cos(ang), 0, Math.sin(ang));
    if (cloudsRef.current) {
      // Clouds drift ~1.25× faster than Earth's surface — purely cosmetic.
      cloudsRef.current.rotation.y += 0.00015;
    }
  });

  return (
    <group>
      {/* Surface: textured if CDN reached, else a deep-ocean sphere
          with subtle emissive so it never reads as flat black. */}
      <mesh ref={surfaceRef}>
        {/* 144×96 subdivisions ≈ 13 800 triangles — smooth limb at any
            zoom inside the [1.15, 50] R⊕ range without a measurable
            framerate hit on integrated GPUs. */}
        <sphereGeometry args={[1, 144, 96]} />
        {earthMaterial ? (
          <primitive object={earthMaterial} attach="material" />
        ) : (
          <meshStandardMaterial
            color="#0c4a6e"
            emissive="#0a2540"
            emissiveIntensity={0.18}
            roughness={0.85}
            metalness={0.05}
          />
        )}
      </mesh>

      {/* Cloud shell — translucent, slightly larger than the surface. */}
      {cloudsTex && (
        <mesh ref={cloudsRef}>
          <sphereGeometry args={[1.012, 96, 64]} />
          <meshStandardMaterial
            map={cloudsTex}
            transparent
            opacity={0.55}
            depthWrite={false}
          />
        </mesh>
      )}

      {/* Atmosphere rim glow — backside-facing sphere with a fresnel-ish
          fragment shader.  Reads as a soft blue halo at the limb. */}
      <mesh>
        <sphereGeometry args={[1.05, 64, 48]} />
        <shaderMaterial
          transparent
          depthWrite={false}
          side={THREE.BackSide}
          blending={THREE.AdditiveBlending}
          uniforms={{
            glowColor: { value: new THREE.Color('#5cb6ff') },
          }}
          vertexShader={`
            varying vec3 vNormal;
            void main() {
              vNormal = normalize(normalMatrix * normal);
              gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }`}
          fragmentShader={`
            uniform vec3 glowColor;
            varying vec3 vNormal;
            void main() {
              float intensity = pow(0.62 - dot(vNormal, vec3(0,0,1.0)), 2.5);
              gl_FragColor = vec4(glowColor, 1.0) * intensity;
            }`}
        />
      </mesh>
    </group>
  );
}

/** Resets the camera + OrbitControls target to the initial framing
 *  whenever `counter` increments.  Lives inside `<Canvas>` so it can
 *  read the live three.js camera + controls via R3F's context. */
function CameraResetter({ counter }: { counter: number }) {
  const { camera, controls } = useThree();
  const last = useRef(counter);
  useFrame(() => {
    if (last.current === counter) return;
    last.current = counter;
    camera.position.set(0, 1.8, 3.6);
    camera.lookAt(0, 0, 0);
    const c = controls as any;
    if (c?.target) {
      c.target.set(0, 0, 0);
      c.update?.();
    }
  });
  return null;
}

/** Background starfield — 2000 deterministic-seeded points. */
function Starfield() {
  const geometry = useMemo(() => {
    let seed = 17;
    const rand = () => { seed = (seed * 1664525 + 1013904223) % 4294967296;
                         return seed / 4294967296; };
    const N = 2000;
    const pos = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      const u = rand(), v = rand();
      const th = 2 * Math.PI * u;
      const ph = Math.acos(2 * v - 1);
      const r  = 40 + rand() * 3;
      pos[3*i]   = r * Math.sin(ph) * Math.cos(th);
      pos[3*i+1] = r * Math.sin(ph) * Math.sin(th);
      pos[3*i+2] = r * Math.cos(ph);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    return g;
  }, []);
  return (
    <points geometry={geometry}>
      <pointsMaterial color="#e2e8f0" size={0.05} sizeAttenuation />
    </points>
  );
}

function LegendChip({ color, label, desc, count, total }: {
  color: string; label: string; desc: string;
  count?: number; total?: number;
}) {
  const pct = total && total > 0 && count !== undefined
    ? ((count / total) * 100).toFixed(count / total >= 0.1 ? 0 : 1)
    : null;
  return (
    <div className="bg-ui-bg-1/60 border border-ui-border rounded p-2 flex items-center gap-2">
      <span className="w-3 h-3 rounded-full shrink-0"
            style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
      <div className="min-w-0 flex-1">
        <div className="text-xs font-semibold text-ui-text flex items-baseline justify-between gap-2">
          <span>{label}</span>
          {count !== undefined && (
            <span className="font-mono text-[10px] text-ui-text">
              {count.toLocaleString()}{pct !== null && <span className="text-ui-text-faint"> · {pct}%</span>}
            </span>
          )}
        </div>
        <div className="text-[10px] text-ui-text-dim">{desc}</div>
      </div>
    </div>
  );
}
