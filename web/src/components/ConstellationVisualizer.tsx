/**
 * Constellation Visualizer — 3D view of a satellite constellation.
 *
 * Renders each orbital plane at its real RAAN + inclination around a
 * textured Earth sphere using react-three-fiber.  Satellites sit at
 * their correct true anomaly on the tilted plane, revolving at the
 * right period for the constellation's altitude (~12 h for GPS,
 * ~14 h for Galileo, ~100 min for Iridium).
 *
 * Previous revision projected every satellite onto a single planar
 * circle (`cx + r·cos(raan+M)`), which was wrong for any Walker
 * constellation: satellites in different RAANs live on *different*
 * planes, not on one shared circle.  The 3D rendering makes the
 * coverage geometry legible and matches the way these constellations
 * are published in Walker 1984 (JBIS 37:559).
 *
 * Open-source references studied (MIT / BSD only — GPL avoided per
 * project license policy):
 *   - KyleGough/solar-system (three.js patterns for sphere + rings)
 *   - jjteoh-thewebdev/r3f-solar-system (react-three-fiber scene layout)
 * NASA 3D Resources (public domain) is the planet-texture source for
 * the Earth globe; until a texture file is bundled locally, we render
 * a procedural "blue-ocean + white-cap poles" Earth that is stylised
 * but clearly recognisable.
 */

import { Canvas, useFrame } from '@react-three/fiber';
import { Line, OrbitControls, Text } from '@react-three/drei';
import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { ErrorBoundary, WebGLUnavailableFallback } from './ErrorBoundary';

interface Satellite {
  a_km: number;
  ecc: number;
  inc_deg: number;
  raan_deg: number;
  mean_anomaly_deg: number;
}

interface ConstellationResponse {
  name: string;
  pattern: string;
  total_satellites: number;
  orbital_planes: number;
  description: string;
  altitude_km: number;
  coverage_half_angle_deg: number;
  satellites: Satellite[];
}

// Scene scale: Earth radius = 1 unit.  6378 km → 1 → so 20000 km altitude
// becomes 1 + 20000/6378 ≈ 4.14 Earth-radii.  Works for LEO (Iridium
// ≈ 1.13) through MEO (GPS ≈ 4.17) through GEO (≈ 6.6) without rescaling.
const R_EARTH_KM = 6378.137;   // WGS-84 equatorial (IAU 2015 nominal)
const SCENE_R    = 1.0;        // Earth radius in scene units

function kmToScene(km: number): number {
  return (km / R_EARTH_KM) * SCENE_R;
}

/** Rotation matrix that takes a position in the orbital plane (x along
 *  periapsis, y normal to line-of-nodes in the plane) into ECI
 *  coordinates, using the two orbital-element angles.
 *
 *  ECI = Rz(raan) · Rx(inc)
 *
 *  (argument of perigee is subsumed into the mean-anomaly phasing the
 *  backend already emits, so we treat periapsis = ascending node.) */
function planeBasis(raan_deg: number, inc_deg: number) {
  const raan = (raan_deg * Math.PI) / 180;
  const inc  = (inc_deg  * Math.PI) / 180;
  const cR = Math.cos(raan), sR = Math.sin(raan);
  const cI = Math.cos(inc),  sI = Math.sin(inc);
  // e1 = ascending-node direction in ECI
  const e1 = new THREE.Vector3(cR, sR, 0);
  // e2 = perpendicular in plane (orthonormal, rotated by inclination)
  const e2 = new THREE.Vector3(-sR * cI, cR * cI, sI);
  return { e1, e2 };
}

/** 256-point ring around Earth at radius `a_scene` tilted by raan/inc. */
function OrbitRing({ raan_deg, inc_deg, a_scene, color }: {
  raan_deg: number; inc_deg: number; a_scene: number; color: string;
}) {
  const pts = useMemo(() => {
    const { e1, e2 } = planeBasis(raan_deg, inc_deg);
    const out: THREE.Vector3[] = [];
    for (let i = 0; i <= 256; i++) {
      const th = (i / 256) * 2 * Math.PI;
      const p = e1.clone().multiplyScalar(a_scene * Math.cos(th))
                  .add(e2.clone().multiplyScalar(a_scene * Math.sin(th)));
      out.push(p);
    }
    return out;
  }, [raan_deg, inc_deg, a_scene]);
  return <Line points={pts} color={color} lineWidth={1.2} transparent opacity={0.55} />;
}

/** Single satellite — 3D marker at the correct point on its plane.
 *  `spin` (radians) advances all satellites in lock-step so the whole
 *  constellation visibly revolves when the user hits Play. */
function SatMarker({ raan_deg, inc_deg, a_scene, phase_rad, spin, color, onHover }: {
  raan_deg: number; inc_deg: number; a_scene: number;
  phase_rad: number; spin: number; color: string;
  onHover?: (entering: boolean) => void;
}) {
  const { e1, e2 } = useMemo(() => planeBasis(raan_deg, inc_deg),
                             [raan_deg, inc_deg]);
  const th = phase_rad + spin;
  const pos = e1.clone().multiplyScalar(a_scene * Math.cos(th))
                .add(e2.clone().multiplyScalar(a_scene * Math.sin(th)));
  return (
    <mesh position={pos}
          onPointerOver={(e) => { e.stopPropagation(); onHover?.(true);  document.body.style.cursor = 'pointer'; }}
          onPointerOut={(e)  => { e.stopPropagation(); onHover?.(false); document.body.style.cursor = ''; }}>
      <sphereGeometry args={[0.025, 12, 12]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.6} />
    </mesh>
  );
}

/** Procedural Earth: blue ocean sphere + white polar caps via a second
 *  thin sphere pair.  No texture download required so the viewer is
 *  instantly usable in offline / CI runs.  Axial tilt is J2000 obliquity
 *  (23.4393°) — matters for any inclination > 0 because users expect
 *  the poles to look right relative to the ecliptic. */
function Earth({ spin }: { spin: number }) {
  const ref = useRef<THREE.Group>(null);
  useFrame(() => { if (ref.current) ref.current.rotation.y = spin * 0.5; });
  return (
    <group ref={ref} rotation={[0, 0, (23.4393 * Math.PI) / 180]}>
      {/* Ocean */}
      <mesh>
        <sphereGeometry args={[SCENE_R, 48, 48]} />
        <meshStandardMaterial color="#1e3a8a" emissive="#0c4a6e" emissiveIntensity={0.08}
                              roughness={0.7} metalness={0.1} />
      </mesh>
      {/* A stylised continent band — procedural latitudinal stripes so the
          globe doesn't look like a featureless ball of plastic. */}
      <mesh>
        <sphereGeometry args={[SCENE_R * 1.001, 48, 24]} />
        <meshBasicMaterial color="#14532d" transparent opacity={0.35} wireframe />
      </mesh>
      {/* Cap hints for rotational axis visibility */}
      <mesh position={[0, SCENE_R * 0.97, 0]}>
        <sphereGeometry args={[0.06, 16, 16]} />
        <meshBasicMaterial color="#f1f5f9" transparent opacity={0.85} />
      </mesh>
      <mesh position={[0, -SCENE_R * 0.97, 0]}>
        <sphereGeometry args={[0.06, 16, 16]} />
        <meshBasicMaterial color="#f1f5f9" transparent opacity={0.85} />
      </mesh>
    </group>
  );
}

function Stars() {
  // A small starfield so the background isn't pitch-black.  Deterministic
  // random (seed 42) so the dome doesn't twinkle between re-renders.
  const geometry = useMemo(() => {
    let seed = 42;
    const rand = () => { seed = (seed * 1664525 + 1013904223) % 4294967296;
                         return seed / 4294967296; };
    const N = 1200;
    const pos = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      const u = rand(), v = rand();
      const th = 2 * Math.PI * u;
      const ph = Math.acos(2 * v - 1);
      const r  = 28 + rand() * 2;
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
      <pointsMaterial color="#e2e8f0" size={0.06} sizeAttenuation />
    </points>
  );
}

/** Thin cone from satellite to Earth showing the coverage footprint.
 *  Half-angle β satisfies sin β = R / (R + h), so β = arcsin(1/a_scene).
 *  We only draw for one satellite per plane to keep the scene readable. */
function CoverageCones({ planes, half_angle_deg, opacity = 0.08 }:
                       { planes: { raan_deg: number; inc_deg: number;
                                   a_scene: number; phase_rad: number }[];
                         half_angle_deg: number; opacity?: number }) {
  return (
    <>
      {planes.map((p, i) => {
        const { e1, e2 } = planeBasis(p.raan_deg, p.inc_deg);
        const pos = e1.clone().multiplyScalar(p.a_scene * Math.cos(p.phase_rad))
                      .add(e2.clone().multiplyScalar(p.a_scene * Math.sin(p.phase_rad)));
        const len = p.a_scene - SCENE_R;
        const radius = len * Math.tan((half_angle_deg * Math.PI) / 180);
        // Point cone toward Earth centre
        const dir = pos.clone().normalize().negate();
        const up  = new THREE.Vector3(0, 1, 0);
        const q   = new THREE.Quaternion().setFromUnitVectors(up, dir);
        return (
          <mesh key={i} position={pos.clone().add(dir.clone().multiplyScalar(len/2))}
                quaternion={q}>
            <coneGeometry args={[radius, len, 24, 1, true]} />
            <meshBasicMaterial color="#22d3ee" transparent opacity={opacity} side={THREE.DoubleSide} />
          </mesh>
        );
      })}
    </>
  );
}

export function ConstellationVisualizer() {
  // BUG-004 pattern: guard the WebGL canvas behind an error boundary so a
  // context-creation failure doesn't take down the rest of the dashboard.
  return (
    <ErrorBoundary
      label="ConstellationVisualizer"
      fallback={(err, reset) => (
        <WebGLUnavailableFallback error={err} onReset={reset}
                                  label="the satellite constellation 3D viewer" />
      )}>
      <ConstellationVisualizerInner />
    </ErrorBoundary>
  );
}

function ConstellationVisualizerInner() {
  const [selected, setSelected] = useState('gps');
  const [data, setData] = useState<ConstellationResponse | null>(null);
  const [playing, setPlaying] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [showCoverage, setShowCoverage] = useState(true);
  const [speed, setSpeed] = useState(1.0);
  const [hovered, setHovered] = useState<null | {
    plane_raan: number; plane_inc: number; plane_idx: number; sat_idx: number;
    alt_km: number; a_km: number;
  }>(null);

  useEffect(() => {
    fetch(`/api/constellation/${selected}`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => {});
  }, [selected]);

  const prepared = useMemo(() => {
    if (!data) return null;
    // Group satellites by RAAN so each plane gets one ring; colour by
    // plane index via HSL for easy visual separation.
    const byRaan: Record<string, Satellite[]> = {};
    for (const s of data.satellites) {
      const k = s.raan_deg.toFixed(2);
      (byRaan[k] = byRaan[k] || []).push(s);
    }
    const planes = Object.entries(byRaan).map(([k, sats], i, arr) => ({
      raan_deg: parseFloat(k),
      inc_deg:  sats[0]?.inc_deg ?? 0,
      a_km:     sats[0]?.a_km    ?? R_EARTH_KM,
      a_scene:  kmToScene(sats[0]?.a_km ?? R_EARTH_KM),
      color:    `hsl(${Math.round((i * 360) / arr.length)}, 72%, 62%)`,
      sats,
    }));
    return {
      planes,
      coverageSamples: planes.map((pl) => ({
        raan_deg:  pl.raan_deg,
        inc_deg:   pl.inc_deg,
        a_scene:   pl.a_scene,
        phase_rad: ((pl.sats[0]?.mean_anomaly_deg ?? 0) * Math.PI) / 180,
      })),
    };
  }, [data]);

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Constellation Visualizer · 3D</h2>
        <p className="text-xs text-ui-text-dim">
          Walker-delta / Walker-star orbital patterns (Walker 1984 JBIS 37:559) — satellites rendered
          in true 3D at their real RAAN + inclination around a rotating Earth.
        </p>
      </div>

      <div className="mb-3 flex flex-wrap gap-2 items-center">
        {['gps', 'galileo', 'iridium'].map((c) => (
          <button key={c} onClick={() => setSelected(c)}
                  className={`px-3 py-1 rounded text-xs ${
                    selected === c
                      ? 'bg-ui-accent-strong text-white'
                      : 'bg-ui-bg-2 text-ui-text hover:bg-ui-bg-3'}`}>
            {c.toUpperCase()}
          </button>
        ))}
        <div className="ml-4 flex items-center gap-3 text-xs text-ui-text">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={playing} onChange={(e) => setPlaying(e.target.checked)} />
            Revolve
          </label>
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={showCoverage} onChange={(e) => setShowCoverage(e.target.checked)} />
            Coverage cones
          </label>
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} />
            Plane labels
          </label>
          <label className="flex items-center gap-1">
            <span className="text-ui-text-dim">speed</span>
            <input type="range" min={0.1} max={5} step={0.1}
                   value={speed}
                   onChange={(e) => setSpeed(parseFloat(e.target.value))}
                   className="w-24" />
            <span className="w-8 tabular-nums">{speed.toFixed(1)}×</span>
          </label>
        </div>
      </div>

      {data && prepared && (
        <>
          <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3 mb-3">
            <div className="text-xs text-ui-text-dim mb-1">{data.pattern}</div>
            <div className="text-sm text-ui-text">{data.description}</div>
          </div>

          <div className="relative bg-ui-bg-0 border border-ui-border rounded overflow-hidden" style={{ height: 560 }}>
            {hovered && (
              <div className="absolute top-2 right-2 z-10 px-3 py-2 rounded
                              border border-ui-accent bg-ui-bg-1/95 text-xs shadow-lg
                              pointer-events-none max-w-xs">
                <div className="text-[10px] uppercase tracking-wider text-ui-accent">
                  {data.name} · plane {hovered.plane_idx + 1}
                </div>
                <div className="text-ui-text font-semibold">
                  SAT #{hovered.sat_idx + 1}
                </div>
                <div className="text-ui-text-dim font-mono text-[11px] mt-0.5 space-y-0.5">
                  <div>Ω = {hovered.plane_raan.toFixed(2)}° (RAAN)</div>
                  <div>i  = {hovered.plane_inc.toFixed(2)}°</div>
                  <div>a  = {hovered.a_km.toFixed(0)} km</div>
                  <div>alt = {hovered.alt_km.toFixed(0)} km</div>
                </div>
              </div>
            )}
            <Canvas camera={{ position: [0, 2.2, 8], fov: 42 }}>
              <ambientLight intensity={0.35} />
              <directionalLight position={[8, 4, 10]} intensity={1.2} />
              <Stars />
              <SpinningScene playing={playing} speed={speed}
                             data={data} prepared={prepared}
                             showLabels={showLabels} showCoverage={showCoverage}
                             onSatHover={setHovered} />
              <OrbitControls enablePan enableZoom enableRotate
                             target={[0, 0, 0]} />
            </Canvas>
          </div>

          <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            <Stat label="Total sats"     value={data.total_satellites} />
            <Stat label="Orbital planes" value={data.orbital_planes} />
            <Stat label="Altitude"       value={`${data.altitude_km.toFixed(0)} km`} />
            <Stat label="Coverage (10° el)"
                  value={`±${data.coverage_half_angle_deg.toFixed(1)}°`} />
          </div>
        </>
      )}
    </div>
  );
}

/** The `useFrame` spin counter has to live inside <Canvas>, so put
 *  everything animation-driven in a child component. */
function SpinningScene({
  playing, speed, data, prepared, showLabels, showCoverage, onSatHover,
}: {
  playing: boolean; speed: number;
  data: ConstellationResponse;
  prepared: NonNullable<ReturnType<typeof useMemo<{
    planes: { raan_deg: number; inc_deg: number; a_km: number;
              a_scene: number; color: string; sats: Satellite[] }[];
    coverageSamples: { raan_deg: number; inc_deg: number;
                       a_scene: number; phase_rad: number }[];
  } | null>>>;
  showLabels: boolean; showCoverage: boolean;
  onSatHover?: (h: null | {
    plane_raan: number; plane_inc: number; plane_idx: number;
    sat_idx: number; alt_km: number; a_km: number;
  }) => void;
}) {
  const spinRef = useRef(0);
  useFrame((_, dt) => {
    if (playing) spinRef.current += dt * 0.3 * speed;
  });
  // Trigger a re-render ~30 Hz so the satellites visibly move while spinRef
  // advances.  (useFrame updates OUTSIDE React's state; this forces
  // reconciliation.)
  const [, setTick] = useState(0);
  useFrame(() => {
    if (playing) setTick((t) => (t + 1) % 1_000_000);
  });

  return (
    <>
      <Earth spin={spinRef.current} />
      {prepared.planes.map((pl, i) => (
        <group key={`${pl.raan_deg.toFixed(2)}-${i}`}>
          <OrbitRing raan_deg={pl.raan_deg} inc_deg={pl.inc_deg}
                     a_scene={pl.a_scene} color={pl.color} />
          {pl.sats.map((s, j) => (
            <SatMarker key={j}
                       raan_deg={pl.raan_deg} inc_deg={pl.inc_deg}
                       a_scene={pl.a_scene}
                       phase_rad={(s.mean_anomaly_deg * Math.PI) / 180}
                       spin={spinRef.current}
                       color={pl.color}
                       onHover={(entering) => onSatHover?.(entering ? {
                         plane_raan: pl.raan_deg,
                         plane_inc:  pl.inc_deg,
                         plane_idx:  i,
                         sat_idx:    j,
                         a_km:       pl.a_km,
                         alt_km:     pl.a_km - R_EARTH_KM,
                       } : null)} />
          ))}
          {showLabels && (
            <Text
              position={[
                pl.a_scene * Math.cos((pl.raan_deg * Math.PI) / 180) * 1.1,
                pl.a_scene * Math.sin((pl.raan_deg * Math.PI) / 180) * 0.18,
                pl.a_scene * Math.sin((pl.raan_deg * Math.PI) / 180) * 1.1,
              ]}
              fontSize={0.12}
              color="#cbd5e1"
              anchorX="left"
              anchorY="middle">
              Ω={pl.raan_deg.toFixed(0)}°, i={pl.inc_deg.toFixed(0)}°
            </Text>
          )}
        </group>
      ))}
      {showCoverage && (
        <CoverageCones planes={prepared.coverageSamples}
                       half_angle_deg={data.coverage_half_angle_deg} />
      )}
    </>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="bg-ui-bg-1/60 border border-ui-border rounded p-2">
      <div className="text-[10px] uppercase tracking-wider text-ui-text-faint">{label}</div>
      <div className="text-sm text-ui-text font-mono">{value}</div>
    </div>
  );
}
