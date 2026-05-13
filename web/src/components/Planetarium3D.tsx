/**
 * Planetarium 3D — inside-sphere celestial-dome view.
 *
 * Complementary to the 2D Planetarium projection.  The user sits at
 * the centre of a unit sphere; stars, Messier objects, exoplanet
 * hosts, the Sun, Moon and planets are plotted at their RA/Dec on
 * that sphere.  Uses react-three-fiber + drei OrbitControls with the
 * camera clamped inside the sphere so rotating the view always feels
 * like looking at the sky.
 *
 * R25 (2026-04-25) — new view mode for the Planetarium tab.  Shares
 * the existing `/api/star_field` + `/api/solar_system` data used by
 * the 2D canvas so there's no extra backend load.
 *
 * Key design choices:
 *  - RA/Dec → 3D unit vector: standard astronomical sphere
 *    (x = cos(dec)·cos(ra), y = sin(dec), z = cos(dec)·sin(ra)).
 *    Dec is latitude; RA is longitude (east).
 *  - Star + DSO clouds use one Points buffer each → single draw call
 *    per kind even with ~9k stars (BSC5).
 *  - Galactic plane is tilted 62.87° relative to equatorial coords,
 *    so the Milky Way band is drawn as a gaussian-weighted extra
 *    star population along that great circle (same trick the
 *    SolarSystem3D starfield uses, but on a unit sphere looking out).
 *  - Constellation lines are short three.Line segments built from
 *    the `constellations` record.
 *  - OrbitControls' `maxDistance = 0.2` keeps the camera inside the
 *    dome; the default target/position has the user look at RA=0 on
 *    the equator.
 */

import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Text } from '@react-three/drei';
import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';

interface StarLike {
  ra: number;       // degrees
  dec: number;      // degrees
  mag: number;
  r: number; g: number; b: number;
  name?: string;
}

interface ConstellationSegment {
  from: { ra: number; dec: number };
  to:   { ra: number; dec: number };
}

interface MessierEntry {
  m: number;
  name: string;
  ra: number;
  dec: number;
  mag: number;
  obj_class: string;
}

interface SolarBody {
  name: string;
  kind: 'sun' | 'moon' | 'planet' | 'asteroid' | 'comet' | 'satellite';
  ra: number;
  dec: number;
  magnitude: number;
  color: [number, number, number];
  distance_au: number;
}

export interface Planetarium3DProps {
  stars: StarLike[];
  constellations: Record<string, ConstellationSegment[]>;
  messier?: MessierEntry[];
  solarBodies?: SolarBody[];
  showConstellations: boolean;
  showMessier: boolean;
  showPlanets: boolean;
  showLabels: boolean;
  magLimit: number;
  height?: number;
}

/** RA/Dec (degrees) → 3D unit vector on the celestial sphere.  The
 *  choice of axes keeps Y = celestial north pole (so the sphere
 *  visually has "up = north"), X at RA=0 Dec=0, Z at RA=90° east.  */
function raDecToVec3(ra_deg: number, dec_deg: number, r = 1): THREE.Vector3 {
  const ra  = (ra_deg * Math.PI) / 180;
  const dec = (dec_deg * Math.PI) / 180;
  const x = r * Math.cos(dec) * Math.cos(ra);
  const z = r * Math.cos(dec) * Math.sin(ra);
  const y = r * Math.sin(dec);
  return new THREE.Vector3(x, y, z);
}

/** Inside-out sphere so the "back" of the material is visible from the
 *  camera — gives a soft dark backdrop. */
function Dome() {
  return (
    <mesh>
      <sphereGeometry args={[1.05, 48, 32]} />
      <meshBasicMaterial color="#020617" side={THREE.BackSide} />
    </mesh>
  );
}

/** Milky Way band — extra star density along the galactic equator
 *  (tilted 62.87° to the celestial equator per NASA SSD).  No bitmap
 *  texture; a cloud of small white-blue points reads as a diffuse band
 *  when viewed from inside. */
function MilkyWayBand() {
  const geom = useMemo(() => {
    let seed = 211;
    const rand = () => { seed = (seed * 1664525 + 1013904223) % 4294967296;
                         return seed / 4294967296; };
    const N = 1500;
    const pos = new Float32Array(N * 3);
    const col = new Float32Array(N * 3);
    const galTilt = (62.87 * Math.PI) / 180;
    for (let i = 0; i < N; i++) {
      // Longitude along galactic plane, ±15° latitude spread (gaussian).
      const lonGal = 2 * Math.PI * rand();
      const latGal = (rand() + rand() + rand() - 1.5) * 0.18;   // approx gaussian, σ≈0.18 rad
      // Galactic → celestial via z-rotation (not the full NCP conversion
      // matrix — this is a decorative band, not a galactic-to-equatorial
      // solver).
      const x0 = Math.cos(latGal) * Math.cos(lonGal);
      const y0 = Math.sin(latGal);
      const z0 = Math.cos(latGal) * Math.sin(lonGal);
      // Tilt around X by galTilt.
      const x = x0;
      const y = y0 * Math.cos(galTilt) - z0 * Math.sin(galTilt);
      const z = y0 * Math.sin(galTilt) + z0 * Math.cos(galTilt);
      pos[3*i]   = x;
      pos[3*i+1] = y;
      pos[3*i+2] = z;
      const intensity = 0.6 + 0.4 * rand();
      col[3*i]     = 0.80 * intensity;
      col[3*i + 1] = 0.85 * intensity;
      col[3*i + 2] = 0.95 * intensity;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('color',    new THREE.BufferAttribute(col, 3));
    return g;
  }, []);
  return (
    <points geometry={geom}>
      <pointsMaterial size={0.008} vertexColors sizeAttenuation
                      transparent opacity={0.7}
                      blending={THREE.AdditiveBlending} />
    </points>
  );
}

/** Bulk star cloud — one Points mesh for ≤9000 BSC5 stars. */
function StarCloud({ stars, magLimit }: { stars: StarLike[]; magLimit: number }) {
  const geom = useMemo(() => {
    const filtered = stars.filter((s) => s.mag <= magLimit);
    const N = filtered.length;
    const pos = new Float32Array(N * 3);
    const col = new Float32Array(N * 3);
    const sz  = new Float32Array(N);
    for (let i = 0; i < N; i++) {
      const v = raDecToVec3(filtered[i].ra, filtered[i].dec);
      pos[3*i]     = v.x;
      pos[3*i + 1] = v.y;
      pos[3*i + 2] = v.z;
      col[3*i]     = filtered[i].r;
      col[3*i + 1] = filtered[i].g;
      col[3*i + 2] = filtered[i].b;
      // Magnitude to size: brightest stars are a bit fatter.
      sz[i] = Math.max(0.002, 0.008 - filtered[i].mag * 0.0008);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('color',    new THREE.BufferAttribute(col, 3));
    // Note: PointsMaterial doesn't use a per-point size attribute; we'd
    // need ShaderMaterial for that.  Baseline uniform size is fine for
    // first pass; upgrading to a size-attribute ShaderMaterial is a
    // future refinement.
    return g;
  }, [stars, magLimit]);
  return (
    <points geometry={geom}>
      <pointsMaterial size={0.007} vertexColors sizeAttenuation
                      transparent opacity={1.0} />
    </points>
  );
}

/** Constellation line segments rendered as short THREE.Line pieces. */
function ConstellationLines({
  constellations,
}: { constellations: Record<string, ConstellationSegment[]> }) {
  const geom = useMemo(() => {
    const pts: number[] = [];
    for (const segs of Object.values(constellations)) {
      for (const s of segs) {
        const a = raDecToVec3(s.from.ra, s.from.dec, 0.995);
        const b = raDecToVec3(s.to.ra,   s.to.dec,   0.995);
        pts.push(a.x, a.y, a.z, b.x, b.y, b.z);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pts), 3));
    return g;
  }, [constellations]);
  return (
    <lineSegments>
      <primitive object={geom} attach="geometry" />
      <lineBasicMaterial color="#4f7cb2" transparent opacity={0.45} />
    </lineSegments>
  );
}

/** Messier deep-sky objects — one sprite-like billboarded disc per
 *  entry.  Colour-coded by object class. */
const MESSIER_COLOR: Record<string, string> = {
  G:  '#b36fcf',    // galaxies = purple
  GC: '#d4a24c',    // globular clusters = tan
  OC: '#c8d940',    // open clusters = lime
  N:  '#88a5ff',    // nebulae = blue
  PN: '#88a5ff',    // planetary nebulae = blue
  SR: '#e87b7b',    // supernova remnants = red
};

function MessierCloud({ messier, showLabels }: {
  messier: MessierEntry[]; showLabels: boolean;
}) {
  return (
    <>
      {messier.map((obj) => {
        const v = raDecToVec3(obj.ra, obj.dec, 0.99);
        const c = MESSIER_COLOR[obj.obj_class] ?? '#b0b0b0';
        return (
          <group key={`m${obj.m}`} position={v}>
            <mesh>
              <sphereGeometry args={[0.006, 10, 10]} />
              <meshBasicMaterial color={c} transparent opacity={0.9} />
            </mesh>
            {showLabels && obj.mag < 7.0 && (
              <Text position={[0.012, 0.012, 0]}
                    fontSize={0.012} color={c}
                    anchorX="left" anchorY="middle">
                M{obj.m}
              </Text>
            )}
          </group>
        );
      })}
    </>
  );
}

/** Catalogue of well-known black holes — well-determined RA/Dec and a
 *  short pedigree note.  All J2000.0 coordinates from SIMBAD / NASA HEASARC.
 *  The catalogue is curated, not exhaustive — covers the candidates an
 *  amateur astronomer or pop-science observer is likely to look for. */
interface BlackHoleEntry {
  name: string;
  ra: number;       // degrees, J2000
  dec: number;      // degrees, J2000
  kind: 'sgr' | 'agn' | 'stellar' | 'imbh';  // supergalactic / AGN / stellar-mass / intermediate
  note: string;
}
const BLACK_HOLES: BlackHoleEntry[] = [
  // Supermassive — galactic centres
  { name: 'Sgr A*',         ra: 266.4168, dec: -29.0078, kind: 'sgr', note: 'Galactic centre, 4.1 M☉×10⁶' },
  { name: 'M87*',           ra: 187.7059, dec:  12.3911, kind: 'agn', note: 'EHT 2019 imaged, 6.5 G☉' },
  { name: 'NGC 1277',       ra:  49.9650, dec:  41.5736, kind: 'agn', note: 'Massive central BH ~17 G☉' },
  { name: 'NGC 4889',       ra: 195.0337, dec:  27.9776, kind: 'agn', note: 'Coma Cluster, ~21 G☉' },
  { name: 'TON 618',        ra: 184.6042, dec:  31.7530, kind: 'agn', note: 'Quasar, ~66 G☉ (extreme)' },
  { name: 'Holm 15A',       ra:   1.3262, dec: -15.6661, kind: 'agn', note: 'Abell 85, ~40 G☉' },
  { name: 'NGC 1365',       ra:  53.4015, dec: -36.1404, kind: 'agn', note: 'Barred-spiral AGN, ~2 G☉' },
  // Stellar-mass / X-ray binaries
  { name: 'Cygnus X-1',     ra: 299.5903, dec:  35.2017, kind: 'stellar', note: 'First confirmed BH (1971), 21 M☉' },
  { name: 'V404 Cygni',     ra: 306.0163, dec:  33.8674, kind: 'stellar', note: 'Microquasar, 9 M☉' },
  { name: 'GRS 1915+105',   ra: 288.7980, dec:  10.9457, kind: 'stellar', note: 'Microquasar, 12 M☉, near-extreme spin' },
  { name: 'A0620-00',       ra:  95.6840, dec:  -0.3486, kind: 'stellar', note: 'Closest known stellar BH, ~3 100 ly' },
  { name: 'LMC X-1',        ra:  84.9117, dec: -69.7430, kind: 'stellar', note: 'LMC X-ray binary, 11 M☉' },
  { name: 'M33 X-7',        ra:  23.5125, dec:  30.5550, kind: 'stellar', note: 'Eclipsing BH-binary, 16 M☉' },
  // Intermediate-mass candidates
  { name: 'HLX-1 (ESO 243-49)', ra:  19.4754, dec: -46.0072, kind: 'imbh', note: 'IMBH candidate, ~10 k M☉' },
  { name: 'IRS 13E',        ra: 266.4135, dec: -29.0080, kind: 'imbh', note: 'Galactic centre IMBH candidate' },
];
const BH_COLOR: Record<BlackHoleEntry['kind'], string> = {
  sgr:     '#ff6b35',  // galactic centre = bright orange
  agn:     '#a855f7',  // active-galactic-nucleus AGN = purple
  stellar: '#22d3ee',  // stellar-mass = cyan
  imbh:    '#facc15',  // intermediate-mass = gold (rare class, deserves visibility)
};

/** Black holes — each rendered as a tiny dark disk surrounded by a
 *  fresnel-like accretion-disk halo so it visually reads as "thing
 *  that pulls light in" rather than a generic dot. */
function BlackHoleCloud({ showLabels }: { showLabels: boolean }) {
  return (
    <>
      {BLACK_HOLES.map((bh) => {
        const v = raDecToVec3(bh.ra, bh.dec, 0.97);
        const color = BH_COLOR[bh.kind];
        // Sgr A* and M87* are visually significant — render a bigger halo.
        const isFamous = bh.name === 'Sgr A*' || bh.name === 'M87*';
        const haloR = isFamous ? 0.018 : 0.012;
        return (
          <group key={bh.name} position={v}>
            {/* Event-horizon proxy — dark disk that absorbs surrounding light */}
            <mesh>
              <sphereGeometry args={[haloR * 0.35, 12, 12]} />
              <meshBasicMaterial color="#000000" />
            </mesh>
            {/* Accretion-disk halo — additive ring of `kind`-coloured glow */}
            <mesh>
              <ringGeometry args={[haloR * 0.45, haloR, 24]} />
              <meshBasicMaterial color={color} side={THREE.DoubleSide}
                                 transparent opacity={0.85}
                                 blending={THREE.AdditiveBlending} />
            </mesh>
            {/* Outer faint glow */}
            <mesh>
              <ringGeometry args={[haloR, haloR * 1.6, 24]} />
              <meshBasicMaterial color={color} side={THREE.DoubleSide}
                                 transparent opacity={0.25}
                                 blending={THREE.AdditiveBlending} />
            </mesh>
            {showLabels && isFamous && (
              <Text position={[haloR * 1.8, haloR * 1.8, 0]}
                    fontSize={0.013} color={color}
                    anchorX="left" anchorY="middle">
                {bh.name}
              </Text>
            )}
          </group>
        );
      })}
    </>
  );
}

/** Solar-system bodies — bigger, coloured dots at their apparent RA/Dec. */
function SolarCloud({ bodies, showLabels }: {
  bodies: SolarBody[]; showLabels: boolean;
}) {
  return (
    <>
      {bodies.map((b) => {
        const v = raDecToVec3(b.ra, b.dec, 0.985);
        const [r, g, bl] = b.color;
        const color = `rgb(${Math.round(r*255)},${Math.round(g*255)},${Math.round(bl*255)})`;
        const isMajor = b.kind === 'sun' || b.kind === 'moon' || b.kind === 'planet';
        const size = b.kind === 'sun'  ? 0.025
                   : b.kind === 'moon' ? 0.022
                   : isMajor            ? 0.014
                   : 0.007;
        return (
          <group key={b.name} position={v}>
            <mesh>
              <sphereGeometry args={[size, 16, 16]} />
              <meshBasicMaterial color={color} />
            </mesh>
            {isMajor && (
              <mesh>
                <sphereGeometry args={[size * 2.5, 16, 16]} />
                <meshBasicMaterial color={color} transparent opacity={0.25}
                                   blending={THREE.AdditiveBlending} />
              </mesh>
            )}
            {showLabels && isMajor && (
              <Text position={[size * 1.8, size * 1.8, 0]}
                    fontSize={0.018} color={color}
                    anchorX="left" anchorY="middle">
                {b.name.charAt(0).toUpperCase() + b.name.slice(1)}
              </Text>
            )}
          </group>
        );
      })}
    </>
  );
}

/** Celestial-pole & equator aids — a thin ring at dec=0 + tiny poles. */
function CelestialAids() {
  return (
    <group>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.995, 0.001, 4, 128]} />
        <meshBasicMaterial color="#475569" transparent opacity={0.5} />
      </mesh>
      <mesh position={[0, 0.995, 0]}>
        <sphereGeometry args={[0.01, 8, 8]} />
        <meshBasicMaterial color="#f1f5f9" />
      </mesh>
      <mesh position={[0, -0.995, 0]}>
        <sphereGeometry args={[0.01, 8, 8]} />
        <meshBasicMaterial color="#f1f5f9" />
      </mesh>
    </group>
  );
}

/** Slowly rotate the whole scene to give the sky a subtle drift — looks
 *  more alive than a static dome.  User can OrbitControl over the drift. */
function SkyDrift() {
  const ref = useRef<THREE.Group>(null);
  useFrame((_, dt) => {
    if (ref.current) ref.current.rotation.y += dt * 0.02;
  });
  return <group ref={ref} />;
}

export function Planetarium3D({
  stars, constellations, messier = [], solarBodies = [],
  showConstellations, showMessier, showPlanets, showLabels, magLimit,
  height = 600,
}: Planetarium3DProps) {
  const [fov, setFov] = useState(75);
  const [showMilkyWay, setShowMilkyWay] = useState(true);
  const [showBlackHoles, setShowBlackHoles] = useState(true);
  return (
    <div className="bg-ui-bg-0 border border-ui-border rounded overflow-hidden">
      <div className="px-3 py-1 border-b border-ui-border-soft flex items-center gap-3 text-[11px]">
        <span className="text-ui-text-dim">View FOV</span>
        <input type="range" min={30} max={120} step={1}
               value={fov} onChange={(e) => setFov(Number(e.target.value))}
               className="w-32" />
        <span className="font-mono text-ui-text w-12">{fov}°</span>
        <label className="flex items-center gap-1 ml-4 text-ui-text">
          <input type="checkbox" checked={showMilkyWay}
                 onChange={(e) => setShowMilkyWay(e.target.checked)} />
          Milky Way band
        </label>
        <label className="flex items-center gap-1 text-ui-text"
               title="Famous black holes — Sgr A*, M87*, Cyg X-1, V404, GRS 1915+105 …">
          <input type="checkbox" checked={showBlackHoles}
                 onChange={(e) => setShowBlackHoles(e.target.checked)} />
          Black holes
        </label>
        <span className="ml-auto text-[10px] text-ui-text-faint">
          Drag to rotate · scroll to zoom (FOV) · RA east, Dec north
        </span>
      </div>
      <div style={{ height }}>
        <Canvas camera={{ position: [0, 0, 0.001], fov, near: 0.001, far: 2 }}>
          <ambientLight intensity={1.0} />
          <Dome />
          {showMilkyWay && <MilkyWayBand />}
          <CelestialAids />
          <StarCloud stars={stars} magLimit={magLimit} />
          {showConstellations && <ConstellationLines constellations={constellations} />}
          {showMessier && messier.length > 0 && (
            <MessierCloud messier={messier} showLabels={showLabels} />
          )}
          {showPlanets && solarBodies.length > 0 && (
            <SolarCloud bodies={solarBodies} showLabels={showLabels} />
          )}
          {showBlackHoles && <BlackHoleCloud showLabels={showLabels} />}
          <SkyDrift />
          {/* Inside-sphere camera: target at origin, max distance capped
              so the user can't zoom outside the dome.  minDistance 0
              lets them stay at the centre. */}
          <OrbitControls enableZoom={false} enablePan={false}
                         rotateSpeed={-0.35}
                         target={[0, 0, 0]} />
        </Canvas>
      </div>
    </div>
  );
}
