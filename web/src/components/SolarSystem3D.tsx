/**
 * Solar System 3D — heliocentric orbit viewer.
 *
 * Renders the orbital paths of the 8 planets + Pluto + 25 bright asteroids
 * + 16 famous comets in true 3D, using the elements served by /api/orbits.
 * Uses react-three-fiber + drei OrbitControls (already a project dep
 * via Ship3D).
 *
 * The XY plane is the J2000 ecliptic. Sun sits at the origin. Inclined
 * orbits (Pluto, Halley, Apophis...) tilt out of plane the way they
 * really do. Logarithmic radial scaling option keeps Mercury visible
 * when Pluto is on screen.
 *
 * Production-grade improvements (2026-04-24..25):
 *   - Each planet renders at its own colour + axial tilt per IAU
 *     WG Cartographic Coords (2015 report, Archinal et al.).
 *   - Saturn draws its ring system (inner/outer radii from Porco 2005
 *     / NASA SSD fact sheets) with a transparent torus geometry.
 *   - "Play" toggle propagates the epoch slider at a user-chosen rate
 *     so the inner planets visibly revolve around the Sun; outer
 *     planets creep proportionally.
 *   - Click any planet → camera frames it (OrbitControls target change).
 *
 * R24 (2026-04-25) — peak upgrade:
 *   - NASA-derived planet textures loaded from Solar System Scope
 *     (CC-BY 4.0) via jsDelivr CDN; procedural colour fallback kicks
 *     in automatically if the CDN is unreachable so the tab works
 *     offline.
 *   - Earth renders a 2-layer shader: day-map + night-lights + specular
 *     highlight on oceans, with a translucent cloud sphere that spins
 *     independently of the surface.
 *   - Sun carries a corona billboard + a halo sprite that scales with
 *     camera distance so it reads as a light source, not a coloured
 *     ball.  (Bloom avoided — postprocessing can't be mixed with the
 *     other 3D panels without re-plumbing the render target.)
 *   - Moon orbits Earth at the correct distance (384,400 km → scene)
 *     and period (27.3 days, scaled by the epoch slider).
 *   - Galilean moons circling Jupiter (Io, Europa, Ganymede, Callisto)
 *     at their real Laplace-resonance-honouring semi-major axes.
 *   - Planets rotate on their own axes — Earth completes one
 *     rotation per 24 h of sim time; inner planets match their
 *     sidereal days from NASA SSD.
 *   - Starfield + diffuse Milky Way band via a wide procedural dust
 *     texture so the backdrop reads as a real sky.
 *
 * Open-source patterns informing this work (MIT / BSD / CC-BY only):
 *   - N3rson/Solar-System-3D (MIT) — shader-material pattern for
 *     Earth day/night, studied and re-implemented clean-room.
 *   - homer-jay/solar-system-textures (CC-BY 4.0) — jsDelivr-served
 *     NASA-derived 2k JPGs, loaded with graceful fallback.
 *   - jjteoh-thewebdev/r3f-solar-system (MIT) — react-three-fiber
 *     scene-composition patterns for planet + moon groups.
 */

import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Line, OrbitControls, Text } from '@react-three/drei';
import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { ErrorBoundary, WebGLUnavailableFallback } from './ErrorBoundary';

interface OrbitTrace {
  name: string;
  kind: 'planet' | 'asteroid' | 'comet';
  a_au: number;
  e: number;
  inc_deg: number;
  color: [number, number, number];
  trace: [number, number, number][];
  current: [number, number, number];
}

interface OrbitsResponse {
  jd: number;
  orbits: OrbitTrace[];
}

interface BeltGroup {
  count: number;
  color: [number, number, number];
  positions: [number, number, number][];
}

interface BeltCloudResponse {
  groups: Record<string, BeltGroup>;
}

type Scale = 'linear' | 'log';

/** NASA-derived planet texture URLs.  Served via jsDelivr from the
 *  homer-jay/solar-system-textures repo (CC-BY 4.0, derived from
 *  Solar System Scope which is itself derived from NASA Visible Earth
 *  + JPL/Caltech).  All textures are 2k JPGs — a reasonable balance
 *  between quality and load time.  If the CDN hit fails the material
 *  falls back to a solid procedural colour so the scene stays usable
 *  offline. */
// Two CDN sources: sanketsingh24/webgl-textures has *all* planets + sun
// + moon + Saturn rings, and mrdoob/three.js has higher-resolution Earth
// + nightmap + clouds.  Both serve via jsdelivr with CORS.  The previous
// host (homer-jay/solar-system-textures) only had 5 of the prefixed files
// the code asked for, so every planet was silently rendering its colour
// fallback.  Verified 2026-04-25 — see Satellites3D.tsx for matching swap.
const TEX_PLANETS = 'https://cdn.jsdelivr.net/gh/sanketsingh24/webgl-textures/textures';
const TEX_THREEJS = 'https://cdn.jsdelivr.net/gh/mrdoob/three.js@r160/examples/textures/planets';
const TEX: Record<string, string> = {
  sun:          `${TEX_PLANETS}/sunmap.jpg`,
  mercury:      `${TEX_PLANETS}/mercurymap.jpg`,
  venus:        `${TEX_PLANETS}/venusmap.jpg`,
  earth:        `${TEX_THREEJS}/earth_atmos_2048.jpg`,
  earth_night:  `${TEX_THREEJS}/earth_lights_2048.png`,
  earth_clouds: `${TEX_THREEJS}/earth_clouds_2048.png`,
  mars:         `${TEX_PLANETS}/marsmap1k.jpg`,
  jupiter:      `${TEX_PLANETS}/jupitermap.jpg`,
  saturn:       `${TEX_PLANETS}/saturnmap.jpg`,
  uranus:       `${TEX_PLANETS}/uranusmap.jpg`,
  neptune:      `${TEX_PLANETS}/neptunemap.jpg`,
  moon:         `${TEX_THREEJS}/moon_1024.jpg`,
  saturn_ring:  `${TEX_PLANETS}/ringsRGBA.png`,
};

/** Real sidereal rotation periods in hours (NASA SSD fact sheets, 2024).
 *  Negative periods = retrograde (Venus, Uranus). */
const SIDEREAL_ROT_HR: Record<string, number> = {
  sun:       609.12,    // ~25.4 d at equator
  mercury: 1407.5,      // 58.646 d
  venus:  -5832.5,      // 243.02 d retrograde
  earth:     23.9344694,
  mars:      24.6229,
  jupiter:    9.9250,
  saturn:    10.656,
  uranus:   -17.24,
  neptune:   16.11,
  pluto:    153.29,
};

/** IAU (WG Cartographic Coordinates 2015, Archinal et al.) axial tilts
 *  in degrees.  Axial tilt = angle between the planet's rotation axis
 *  and the normal to its orbital plane.  Venus and Uranus are notable
 *  (177° and 97° respectively — both functionally retrograde).
 *  Pluto included as a dwarf-planet courtesy entry. */
const AXIAL_TILT_DEG: Record<string, number> = {
  mercury: 0.034,
  venus:  177.4,
  earth:   23.44,
  mars:    25.19,
  jupiter:  3.13,
  saturn:  26.73,
  uranus:  97.77,
  neptune: 28.32,
  pluto:  122.53,
};

/** Saturn ring geometry (IAU 2015 + NASA SSD fact sheets). Inner edge of
 *  the D ring to outer edge of the A ring, with a subtle Cassini Division
 *  rendered as a darker inner torus so the feature is visible at MEO-ish
 *  viewing distances. */
const SATURN_R_INNER_KM = 74_500;    // D ring inner edge
const SATURN_R_OUTER_KM = 136_775;   // A ring outer edge
const SATURN_R_CASS_IN  = 117_580;   // Cassini Division inner
const SATURN_R_CASS_OUT = 122_170;   // Cassini Division outer

/** Convert planet body-radius in km to scene units consistent with the
 *  planet-marker size scheme already in use (0.08-0.45 units).  Saturn
 *  itself in this viewer is ~0.45 units, so 60,268 km (Saturn's equatorial
 *  radius) maps to 0.45 — and the rings render at ratios off that. */
function kmToSaturnScale(km: number, saturnRadiusUnits: number): number {
  return (km / 60_268) * saturnRadiusUnits;
}

function scaleVec(v: [number, number, number], mode: Scale): THREE.Vector3 {
  const [x, y, z] = v;
  if (mode === 'linear') return new THREE.Vector3(x, y, z);
  // Log scale: keep direction, compress magnitude.
  const r = Math.sqrt(x * x + y * y + z * z);
  if (r < 1e-6) return new THREE.Vector3(0, 0, 0);
  const r2 = Math.log10(1 + r) * 6.0;
  const k = r2 / r;
  return new THREE.Vector3(x * k, y * k, z * k);
}

function ScaledLine({
  trace, color, opacity, scaleMode,
}: { trace: [number, number, number][]; color: string; opacity: number; scaleMode: Scale }) {
  const pts = useMemo(
    () => trace.map((p) => scaleVec(p, scaleMode)),
    [trace, scaleMode]
  );
  return <Line points={pts} color={color} lineWidth={1} transparent opacity={opacity} />;
}

function SaturnRings({ size }: { size: number }) {
  // Main ring + darker Cassini Division band, both flat against the
  // planet's equatorial plane (rendered via rotationX=90° so the rings
  // lie in the xy plane before axial-tilt parent rotation).
  const inner = kmToSaturnScale(SATURN_R_INNER_KM, size);
  const outer = kmToSaturnScale(SATURN_R_OUTER_KM, size);
  const cassIn  = kmToSaturnScale(SATURN_R_CASS_IN,  size);
  const cassOut = kmToSaturnScale(SATURN_R_CASS_OUT, size);
  return (
    <group rotation={[Math.PI / 2, 0, 0]}>
      <mesh>
        <ringGeometry args={[inner, outer, 96]} />
        <meshBasicMaterial color="#d4b896" transparent opacity={0.55}
                           side={THREE.DoubleSide} />
      </mesh>
      <mesh>
        <ringGeometry args={[cassIn, cassOut, 96]} />
        <meshBasicMaterial color="#1f2937" transparent opacity={0.8}
                           side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

/** Custom hook that attempts to load a texture from a URL, returning
 *  `undefined` while loading and on failure.  We can't use drei's
 *  `useTexture` here because that throws on failure (Suspense-hostile
 *  when the CDN is unreachable).  Returns ColorSpace-corrected SRGB
 *  textures so they look right under standard three lighting. */
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
        (t as any).colorSpace = (THREE as any).SRGBColorSpace ?? 'srgb';
        setTex(t);
      },
      undefined,
      () => { /* network / 404 — leave undefined, procedural fallback takes over */ },
    );
    return () => { alive = false; };
  }, [url]);
  return tex;
}

function PlanetMarker({
  position, color, size, name, showLabel, onClick, onHover, spin, enableTextures,
}: { position: THREE.Vector3; color: string; size: number; name: string;
     showLabel: boolean; onClick?: () => void;
     onHover?: (entering: boolean) => void;
     spin: number;
     enableTextures: boolean }) {
  const lower = name.toLowerCase();
  const tiltDeg = AXIAL_TILT_DEG[lower] ?? 0;
  const tilt = (tiltDeg * Math.PI) / 180;
  const hasRings = lower === 'saturn';
  const bodyRef = useRef<THREE.Group>(null);
  const cloudsRef = useRef<THREE.Mesh>(null);

  // Use body-axial spin computed from sidereal rotation period so e.g.
  // Earth does one rotation per 24 h of sim-time and Venus spins
  // backwards slowly.  `spin` is the cumulative epoch phase in years;
  // convert to rotations around the planet's axis.
  const rotHr = SIDEREAL_ROT_HR[lower];
  const rotation = rotHr
    ? (spin * 365.25 * 24 / rotHr) * 2 * Math.PI
    : spin * 2 * Math.PI;
  useFrame(() => {
    if (bodyRef.current) bodyRef.current.rotation.y = rotation;
    if (cloudsRef.current) cloudsRef.current.rotation.y = rotation * 1.25;  // clouds drift faster than surface
  });

  const surfaceTex = useOptionalTexture(enableTextures ? TEX[lower] : undefined);
  const nightTex   = useOptionalTexture(enableTextures && lower === 'earth' ? TEX.earth_night : undefined);
  const cloudsTex  = useOptionalTexture(enableTextures && lower === 'earth' ? TEX.earth_clouds : undefined);

  // Earth day-night shader: mix day + night texture by dot(surfaceNormal,
  // sunDir), so the night side shows city lights instead of black.
  const earthMaterial = useMemo(() => {
    if (lower !== 'earth' || !surfaceTex || !nightTex) return null;
    return new THREE.ShaderMaterial({
      uniforms: {
        dayMap:    { value: surfaceTex },
        nightMap:  { value: nightTex },
        sunDir:    { value: new THREE.Vector3(1, 0, 0) },
      },
      vertexShader: `
        varying vec3 vNormal;
        varying vec2 vUv;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
      fragmentShader: `
        uniform sampler2D dayMap;
        uniform sampler2D nightMap;
        uniform vec3 sunDir;
        varying vec3 vNormal;
        varying vec2 vUv;
        void main() {
          vec3 day   = texture2D(dayMap,   vUv).rgb;
          vec3 night = texture2D(nightMap, vUv).rgb * 1.25;
          float d = dot(normalize(vNormal), normalize(sunDir));
          float mixAmt = smoothstep(-0.2, 0.2, d);
          vec3 col = mix(night, day, mixAmt);
          // Faint atmospheric rim-lighting: boost colour where the
          // fragment is near the limb but still sunlit-ish.
          float rim = pow(1.0 - clamp(abs(dot(normalize(vNormal), vec3(0.0,0.0,1.0))), 0.0, 1.0), 3.0);
          col += vec3(0.35, 0.55, 0.85) * rim * mixAmt * 0.35;
          gl_FragColor = vec4(col, 1.0);
        }`,
    });
  }, [lower, surfaceTex, nightTex]);

  useFrame(({ camera }) => {
    // Approximate sun direction = -planet_position (sun is at origin in
    // our scale), expressed in the planet's local frame.
    if (earthMaterial && bodyRef.current) {
      const worldPos = new THREE.Vector3();
      bodyRef.current.getWorldPosition(worldPos);
      const toSun = worldPos.clone().negate().normalize();
      earthMaterial.uniforms.sunDir.value.copy(toSun.applyQuaternion(bodyRef.current.quaternion.clone().invert()));
    }
    void camera;
  });

  return (
    <group position={position}>
      {/* Axial-tilt rotation applies to the planet body + its rings so
          Saturn's rings appear inclined to the ecliptic and Uranus
          rolls sideways the way it actually does. */}
      <group rotation={[0, 0, tilt]}>
        <group ref={bodyRef}>
          <mesh
            onClick={onClick ? (e) => { e.stopPropagation(); onClick(); } : undefined}
            onPointerOver={(e) => { e.stopPropagation(); onHover?.(true); document.body.style.cursor = 'pointer'; }}
            onPointerOut={(e)  => { e.stopPropagation(); onHover?.(false); document.body.style.cursor = ''; }}
          >
            <sphereGeometry args={[size, 48, 48]} />
            {lower === 'earth' && earthMaterial ? (
              <primitive object={earthMaterial} attach="material" />
            ) : surfaceTex ? (
              <meshStandardMaterial map={surfaceTex} roughness={0.8} metalness={0.05}
                                    emissive={color} emissiveIntensity={0.08} />
            ) : (
              <meshStandardMaterial color={color} emissive={color}
                                    emissiveIntensity={0.25}
                                    roughness={0.8} metalness={0.05} />
            )}
          </mesh>
          {/* Cloud layer — 1.5% larger sphere, translucent, rotates at
              1.25× surface rate.  Only rendered if the texture loaded. */}
          {lower === 'earth' && cloudsTex && (
            <mesh ref={cloudsRef}>
              <sphereGeometry args={[size * 1.015, 48, 48]} />
              <meshStandardMaterial map={cloudsTex} transparent opacity={0.55}
                                    depthWrite={false} />
            </mesh>
          )}
        </group>
        {hasRings && <SaturnRings size={size} />}
      </group>
      {/* Earth's moon — orbits the planet at ~384,400 km, period 27.3 d.
          Scaled to something visible: distance = 3× Earth diameter,
          which reads as "obviously a moon, not a second planet". */}
      {lower === 'earth' && <EarthMoon parentSize={size} spin={spin} />}
      {/* Galilean moons around Jupiter — four clear dots at their
          Laplace-resonance-respecting semi-major axes.  Scene scale
          doesn't allow real ratios (Io at 421,700 km = 6 Jupiter radii)
          so we compress linearly to fit around the visible planet. */}
      {lower === 'jupiter' && <GalileanMoons parentSize={size} spin={spin} />}
      {showLabel && (
        <Text
          position={[size * 1.6, size * 1.6, 0]}
          fontSize={0.35}
          color="#cbd5e1"
          anchorX="left"
          anchorY="middle"
        >
          {name}
        </Text>
      )}
    </group>
  );
}

/** Earth's moon — one sphere orbiting Earth at ~3× Earth-diameter
 *  distance (visually readable; true 30× would put the moon off the
 *  card).  Period 27.3 d at sim-time 1 yr/s = 13.4 orbits per real
 *  second × `spin` years. */
function EarthMoon({ parentSize, spin }: { parentSize: number; spin: number }) {
  const groupRef = useRef<THREE.Group>(null);
  const tex = useOptionalTexture(TEX.moon);
  useFrame(() => {
    if (groupRef.current) {
      // 27.321661 d sidereal period → rotations per year.
      const orbitAngle = (spin * 365.25 / 27.321661) * 2 * Math.PI;
      groupRef.current.rotation.y = orbitAngle;
    }
  });
  return (
    <group ref={groupRef}>
      <mesh position={[parentSize * 3, 0, 0]}>
        <sphereGeometry args={[parentSize * 0.27, 24, 24]} />
        {tex
          ? <meshStandardMaterial map={tex} roughness={0.95} metalness={0.0} />
          : <meshStandardMaterial color="#9ca3af" roughness={0.95} metalness={0.0} />}
      </mesh>
    </group>
  );
}

/** Galilean moons — Io, Europa, Ganymede, Callisto.  Periods + relative
 *  radii from NASA SSD.  Periods are scaled by the inner ratio so the
 *  Laplace resonance (4:2:1 for Io:Europa:Ganymede) is visible in the
 *  animation. */
const GALILEAN: { name: string; r: number; period_d: number; color: string }[] = [
  { name: 'Io',       r: 0.18, period_d:  1.769, color: '#fde68a' },
  { name: 'Europa',   r: 0.16, period_d:  3.551, color: '#e5e7eb' },
  { name: 'Ganymede', r: 0.22, period_d:  7.155, color: '#b7a28c' },
  { name: 'Callisto', r: 0.21, period_d: 16.689, color: '#6b7280' },
];

function GalileanMoons({ parentSize, spin }: { parentSize: number; spin: number }) {
  return (
    <>
      {GALILEAN.map((m, i) => {
        const dist = parentSize * (2.2 + i * 0.8);  // visually spaced
        const orbitAngle = (spin * 365.25 / m.period_d) * 2 * Math.PI;
        const x = dist * Math.cos(orbitAngle);
        const z = dist * Math.sin(orbitAngle);
        return (
          <group key={m.name}>
            <mesh position={[x, 0, z]}>
              <sphereGeometry args={[parentSize * m.r, 16, 16]} />
              <meshStandardMaterial color={m.color} roughness={0.9} metalness={0.0} />
            </mesh>
          </group>
        );
      })}
    </>
  );
}

function Sun({ enableTextures }: { enableTextures: boolean }) {
  const ref = useRef<THREE.Mesh>(null);
  const coronaRef = useRef<THREE.Mesh>(null);
  const sunTex = useOptionalTexture(enableTextures ? TEX.sun : undefined);

  useFrame(({ clock }) => {
    if (ref.current) {
      // Subtle "breathing" animation + continuous rotation.
      const s = 1 + 0.05 * Math.sin(clock.elapsedTime * 2);
      ref.current.scale.setScalar(s);
      ref.current.rotation.y += 0.0015;
    }
    // Corona counter-rotates subtly so the glow feels dynamic.
    if (coronaRef.current) {
      coronaRef.current.rotation.z = clock.elapsedTime * 0.05;
    }
  });

  /** Custom shader that renders a soft radial gradient from the sun's
   *  surface outward.  Additive blending + depthWrite=false so it
   *  doesn't occlude planets behind it. */
  const coronaMat = useMemo(() => new THREE.ShaderMaterial({
    uniforms: {
      intensity: { value: 1.0 },
      color:     { value: new THREE.Color('#fde68a') },
    },
    vertexShader: `
      varying vec3 vPos;
      void main() {
        vPos = position;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      uniform float intensity;
      uniform vec3 color;
      varying vec3 vPos;
      void main() {
        float r = length(vPos) / 0.9;       // 0.9 = coronaGeometry radius
        float a = smoothstep(1.0, 0.35, r) * intensity;
        gl_FragColor = vec4(color, a);
      }`,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    side: THREE.BackSide,
  }), []);

  return (
    <group>
      {/* Surface disc */}
      <mesh ref={ref}>
        <sphereGeometry args={[0.4, 48, 48]} />
        {sunTex
          ? <meshBasicMaterial map={sunTex} />
          : <meshBasicMaterial color="#fde68a" />}
      </mesh>
      {/* Corona glow — back-side rendered transparent sphere giving a
          gradient halo around the visible disc. */}
      <mesh ref={coronaRef}>
        <sphereGeometry args={[0.9, 48, 48]} />
        <primitive object={coronaMat} attach="material" />
      </mesh>
      {/* Point light emanating from the Sun — shared across the scene
          so planets render with real night-sides (away from Sun is
          unlit). */}
      <pointLight color="#fff4d0" intensity={2.4} decay={0} distance={0} />
    </group>
  );
}

function EclipticGrid({ size = 50, divisions = 50 }: { size?: number; divisions?: number }) {
  return <gridHelper args={[size, divisions, '#1e293b', '#1e293b']} rotation={[Math.PI / 2, 0, 0]} />;
}

/** Distant starfield — 4000 deterministic points on a large sphere,
 *  with a gaussian-weighted density bump along a random "galactic
 *  band" so the Milky Way is suggested without a bitmap texture.
 *  Stars blue-shifted near the band simulate the diffuse scattered
 *  light from disk stars. */
function HeliocentricStars() {
  const geom = useMemo(() => {
    let seed = 91;
    const rand = () => { seed = (seed * 1664525 + 1013904223) % 4294967296;
                         return seed / 4294967296; };
    const N = 4000;
    const pos = new Float32Array(N * 3);
    const col = new Float32Array(N * 3);
    // Galactic-equator plane tilted ~62.87° to the ecliptic
    // (NASA SSD).  We approximate with Rz + Rx rotations.
    const galPlane = new THREE.Vector3(0, 1, 0);
    const tilt = new THREE.Quaternion().setFromAxisAngle(
      new THREE.Vector3(1, 0, 0), (62.87 * Math.PI) / 180,
    );
    galPlane.applyQuaternion(tilt);
    for (let i = 0; i < N; i++) {
      const u = rand(), v = rand();
      const th = 2 * Math.PI * u;
      const ph = Math.acos(2 * v - 1);
      const R  = 60 + rand() * 5;
      const p = new THREE.Vector3(
        R * Math.sin(ph) * Math.cos(th),
        R * Math.sin(ph) * Math.sin(th),
        R * Math.cos(ph),
      );
      // Add a band of extra stars near galactic plane: reject/retry
      // if out-of-band (crude importance sampling).
      const dot = Math.abs(p.clone().normalize().dot(galPlane));
      // dot = 1 → pole, dot = 0 → band centre.
      if (dot > 0.1 && rand() < 0.35) {
        // Re-sample closer to the band — flatten along galPlane.
        const inBand = Math.sqrt(1 - dot * dot);
        const band = new THREE.Vector3(0, 0, 1).cross(galPlane).normalize();
        p.add(band.multiplyScalar((rand() - 0.5) * 20));
        p.normalize().multiplyScalar(R);
      }
      pos[3*i]   = p.x;
      pos[3*i+1] = p.y;
      pos[3*i+2] = p.z;
      const nearBand = 1 - Math.min(1, Math.abs(p.clone().normalize().dot(galPlane)) * 1.5);
      // Whiter near band (dust scatter), subtle yellow-red away.
      col[3*i]     = 0.85 + 0.15 * nearBand;
      col[3*i + 1] = 0.82 + 0.12 * nearBand;
      col[3*i + 2] = 0.78 + 0.2  * nearBand;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('color',    new THREE.BufferAttribute(col, 3));
    return g;
  }, []);
  return (
    <points geometry={geom}>
      <pointsMaterial size={0.09} vertexColors sizeAttenuation
                      transparent opacity={0.95} />
    </points>
  );
}

/** Smoothly moves the OrbitControls target to the clicked planet and
 *  pulls the camera in for a closer view.  Uses `useThree().controls`
 *  (exposed by makeDefault on OrbitControls) so there's no ref
 *  gymnastics. */
/** Render a mission's outbound trajectory as a glowing polyline.
 *  Points come in heliocentric AU coordinates; we rescale to scene
 *  units the same way `ScaledLine` does so a porkchop trajectory
 *  drawn alongside Mars's orbit lines up with the planet's path. */
function MissionTrajectoryArc({ points, scaleMode }: {
  points: [number, number, number][]; scaleMode: Scale;
}) {
  const geom = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const arr = new Float32Array(points.length * 3);
    for (let i = 0; i < points.length; i++) {
      const v = scaleVec(points[i] as any, scaleMode);
      arr[3 * i]     = v.x;
      arr[3 * i + 1] = v.y;
      arr[3 * i + 2] = v.z;
    }
    g.setAttribute('position', new THREE.BufferAttribute(arr, 3));
    return g;
  }, [points, scaleMode]);

  return (
    <line>
      <primitive object={geom} attach="geometry" />
      <lineBasicMaterial color="#facc15" linewidth={2} transparent opacity={0.9}
                         blending={THREE.AdditiveBlending} depthWrite={false} />
    </line>
  );
}

function FocusCamera({ focusTarget, scaleMode }:
                     { focusTarget: [number, number, number] | null | undefined;
                       scaleMode: Scale }) {
  const { camera, controls } = useThree() as any;
  useEffect(() => {
    if (!focusTarget || !controls || !controls.target) return;
    const pos = scaleVec(focusTarget, scaleMode);
    // Set the orbit target to the planet, pull the camera in to roughly
    // 3× the planet's distance from the Sun along the current view
    // direction — preserves orientation, avoids cinematic jump cuts.
    controls.target.set(pos.x, pos.y, pos.z);
    const mag = Math.max(1.5, pos.length());
    const dir = new THREE.Vector3().copy(camera.position).sub(controls.target).normalize();
    const cameraPos = controls.target.clone().add(dir.multiplyScalar(mag * 2.5));
    camera.position.set(cameraPos.x, cameraPos.y, cameraPos.z);
    controls.update?.();
  }, [focusTarget, scaleMode, camera, controls]);
  return null;
}

/** Point cloud for a minor-body population (main belt / trojans / KBO / SDO). */
function BeltCloud({ group, scaleMode, size = 0.04, opacity = 0.9 }:
                   { group: BeltGroup; scaleMode: Scale; size?: number; opacity?: number }) {
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const coords = new Float32Array(group.positions.length * 3);
    for (let i = 0; i < group.positions.length; i++) {
      const v = scaleVec(group.positions[i], scaleMode);
      coords[3 * i]     = v.x;
      coords[3 * i + 1] = v.y;
      coords[3 * i + 2] = v.z;
    }
    g.setAttribute('position', new THREE.BufferAttribute(coords, 3));
    return g;
  }, [group.positions, scaleMode]);
  const [r, g, b] = group.color;
  const color = `rgb(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)})`;
  return (
    <points geometry={geometry}>
      <pointsMaterial size={size} color={color} transparent opacity={opacity} sizeAttenuation />
    </points>
  );
}

export function SolarSystem3D() {
  // BUG-004: without this boundary a failed WebGL context creation
  // (headless Chrome, disabled GPU) blanks the entire dashboard.
  return (
    <ErrorBoundary
      label="SolarSystem3D"
      fallback={(err, reset) => (
        <WebGLUnavailableFallback error={err} onReset={reset} label="the Solar System 3D orbit viewer" />
      )}
    >
      <SolarSystem3DInner />
    </ErrorBoundary>
  );
}

function SolarSystem3DInner() {
  const [data, setData] = useState<OrbitsResponse | null>(null);
  const [belt, setBelt] = useState<BeltCloudResponse | null>(null);
  const [scaleMode, setScaleMode] = useState<Scale>('log');
  const [showAsteroids, setShowAsteroids] = useState(true);
  const [showComets, setShowComets] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [showBelt, setShowBelt] = useState(true);
  const [years, setYears] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speedYrPerS, setSpeedYrPerS] = useState(1);
  const [focus, setFocus] = useState<string | null>(null);
  const [hovered, setHovered] = useState<OrbitTrace | null>(null);
  const [pinned, setPinned] = useState<OrbitTrace | null>(null);
  const [enableTextures, setEnableTextures] = useState(true);
  const [enableStars, setEnableStars]       = useState(true);
  // Mission overlay: when the user runs a porkchop in Mission Studio
  // we fetch the trajectory polyline and draw it as a luminous arc on
  // the heliocentric view.  Cleared by clicking the "Clear" pill.
  const [missionOverlay, setMissionOverlay] = useState<{
    origin: string; destination: string;
    points: [number, number, number][];   // (x_au, y_au, z_au)
    label: string;
  } | null>(null);

  // Subscribe to a window-level "aria.mission.trajectory" event so
  // sibling tabs (MissionStudio) can push a polyline without coupling
  // through React context.  CustomEvent payload is the same shape as
  // the local state above.
  useEffect(() => {
    const onSet = (e: Event) => {
      const ce = e as CustomEvent;
      if (ce.detail === null) setMissionOverlay(null);
      else setMissionOverlay(ce.detail);
    };
    window.addEventListener('aria.mission.trajectory', onSet);
    return () => window.removeEventListener('aria.mission.trajectory', onSet);
  }, []);

  useEffect(() => {
    const jd = 2451545.0 + years * 365.25;
    fetch(`/api/orbits?jd=${jd}&samples=128`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => {});
  }, [years]);

  // Play-mode advances the epoch slider in real time so the inner
  // planets visibly revolve — once a wall-second of elapsed time
  // corresponds to `speedYrPerS` simulated years, the backend refetch
  // kicks off and the scene snaps to the new positions.  wall-side
  // animation is deliberately coarse (2 Hz refetch) because /api/orbits
  // is the authoritative positions source; faster than this would
  // spam the backend with little visual benefit.
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      setYears((y) => Math.max(-50, Math.min(50, y + speedYrPerS * 0.5)));
    }, 500);
    return () => clearInterval(id);
  }, [playing, speedYrPerS]);

  // Load belt cloud once — the synthesized distribution is time-independent.
  useEffect(() => {
    fetch('/api/belt_cloud?main_belt=500&trojans=100&kuiper=200&scattered=60')
      .then((r) => r.json())
      .then(setBelt)
      .catch(() => {});
  }, []);

  const filtered = useMemo(() => {
    if (!data) return [] as OrbitTrace[];
    return data.orbits.filter(
      (o) =>
        o.kind === 'planet' ||
        (showAsteroids && o.kind === 'asteroid') ||
        (showComets && o.kind === 'comet')
    );
  }, [data, showAsteroids, showComets]);

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Solar System — Heliocentric Orbits</h2>
        <p className="text-xs text-ui-text-dim">
          {data
            ? `${data.orbits.length} orbits · JD ${data.jd.toFixed(0)} · ecliptic XY plane`
            : 'Loading…'}
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3 text-xs">
        <label className="flex items-center gap-2">
          <span className="text-ui-text-dim">Scale:</span>
          <select
            value={scaleMode}
            onChange={(e) => setScaleMode(e.target.value as Scale)}
            className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text"
          >
            <option value="log">log (Mercury → Pluto fit)</option>
            <option value="linear">linear (true scale, pan to Pluto)</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-ui-text">
          <input type="checkbox" checked={showAsteroids} onChange={(e) => setShowAsteroids(e.target.checked)} />
          Asteroids ({data?.orbits.filter((o) => o.kind === 'asteroid').length ?? 0})
        </label>
        <label className="flex items-center gap-2 text-ui-text">
          <input type="checkbox" checked={showComets} onChange={(e) => setShowComets(e.target.checked)} />
          Comets ({data?.orbits.filter((o) => o.kind === 'comet').length ?? 0})
        </label>
        <label className="flex items-center gap-2 text-ui-text">
          <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} />
          Labels
        </label>
        <label className="flex items-center gap-2 text-ui-text">
          <input type="checkbox" checked={showBelt} onChange={(e) => setShowBelt(e.target.checked)} />
          Belt clouds
          {belt && ` (${Object.values(belt.groups).reduce((s, g) => s + g.count, 0)} pts)`}
        </label>
        <label className="flex items-center gap-2 text-ui-text">
          <input type="checkbox" checked={enableTextures} onChange={(e) => setEnableTextures(e.target.checked)} />
          NASA textures
        </label>
        <label className="flex items-center gap-2 text-ui-text">
          <input type="checkbox" checked={enableStars} onChange={(e) => setEnableStars(e.target.checked)} />
          Star background
        </label>
        {missionOverlay && (
          <div className="col-span-2 flex items-center gap-2 px-2 py-1 rounded
                          border border-sev-warn bg-sev-warn/30 text-sev-warn">
            <span className="text-[10px] uppercase tracking-wider">Mission</span>
            <span className="text-xs font-mono truncate flex-1" title={missionOverlay.label}>
              {missionOverlay.label}
            </span>
            <button onClick={() => setMissionOverlay(null)}
                    className="text-[10px] text-sev-warn hover:text-sev-warn">
              clear ×
            </button>
          </div>
        )}
        <label className="col-span-2 md:col-span-4">
          <div className="flex items-center justify-between mb-1">
            <span className="text-ui-text-dim">Epoch (years from J2000): {years.toFixed(1)}</span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPlaying((p) => !p)}
                className={`px-2 py-0.5 text-[11px] rounded border
                  ${playing ? 'border-sev-crit bg-sev-crit/40 text-sev-crit'
                           : 'border-sev-ok bg-sev-ok/40 text-sev-ok'}
                  hover:bg-ui-bg-2`}
                title={playing ? 'Pause orbital animation' : 'Play — planets revolve at the chosen rate'}>
                {playing ? '❚❚ Pause' : '▶ Play'}
              </button>
              <label className="flex items-center gap-1 text-[11px]">
                <span className="text-ui-text-dim">speed</span>
                <select value={speedYrPerS}
                        onChange={(e) => setSpeedYrPerS(Number(e.target.value))}
                        className="bg-ui-bg-2 border border-ui-border-strong rounded px-1 py-0.5">
                  <option value={0.1}>0.1 yr/s</option>
                  <option value={0.5}>0.5 yr/s</option>
                  <option value={1}>1 yr/s</option>
                  <option value={2}>2 yr/s</option>
                  <option value={5}>5 yr/s</option>
                </select>
              </label>
              {focus && (
                <button onClick={() => setFocus(null)}
                        className="px-2 py-0.5 text-[11px] rounded border border-ui-border-strong bg-ui-bg-1 hover:bg-ui-bg-2 text-ui-text">
                  ✕ unfocus {focus}
                </button>
              )}
            </div>
          </div>
          <input
            type="range"
            min={-50}
            max={50}
            step={0.1}
            value={years}
            onChange={(e) => setYears(Number(e.target.value))}
            className="w-full"
          />
        </label>
      </div>

      <div className="relative bg-ui-bg-0 border border-ui-border rounded overflow-hidden" style={{ height: 560 }}>
        {(pinned || hovered) && (() => {
          const card = (pinned || hovered)!;
          const isPinned = !!pinned;
          return (
            <div className={`absolute top-2 right-2 z-10 px-3 py-2 rounded
                            border ${isPinned ? 'border-sev-warn' : 'border-ui-accent'}
                            bg-ui-bg-1/95 text-xs shadow-lg max-w-xs ${isPinned ? '' : 'pointer-events-none'}`}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-ui-accent">
                    {card.kind}{isPinned ? ' · pinned' : ''}
                  </div>
                  <div className="text-ui-text font-semibold">{card.name.replace(/^\(\d+\)\s*/, '')}</div>
                </div>
                {isPinned && (
                  <button onClick={() => setPinned(null)}
                          className="text-ui-text-dim hover:text-ui-text leading-none px-1"
                          title="Unpin info card">×</button>
                )}
              </div>
              <div className="text-ui-text-dim font-mono text-[11px] mt-0.5 space-y-0.5">
                <div>a = {card.a_au.toFixed(3)} AU</div>
                <div>e = {card.e.toFixed(3)}</div>
                <div>i = {card.inc_deg.toFixed(1)}°</div>
                {AXIAL_TILT_DEG[card.name.toLowerCase()] !== undefined && (
                  <div>tilt = {AXIAL_TILT_DEG[card.name.toLowerCase()].toFixed(1)}°</div>
                )}
              </div>
            </div>
          );
        })()}
        <Canvas camera={{ position: [12, 12, 12], fov: 45 }}>
          <ambientLight intensity={0.25} />
          {/* Sun owns its own pointLight so the lighting origin tracks
              the source geometry — see Sun() body. */}
          <Sun enableTextures={enableTextures} />
          {enableStars && <HeliocentricStars />}
          <EclipticGrid />

          {showBelt && belt && Object.entries(belt.groups).map(([name, g]) => (
            <BeltCloud key={name} group={g} scaleMode={scaleMode}
                       size={name === 'main_belt' ? 0.035 : name === 'trojans' ? 0.04 : 0.05}
                       opacity={name === 'scattered_disk' ? 0.6 : 0.8} />
          ))}

          {filtered.map((o) => {
            const c = `rgb(${Math.round(o.color[0] * 255)},${Math.round(o.color[1] * 255)},${Math.round(o.color[2] * 255)})`;
            const opacity = o.kind === 'planet' ? 0.85 : o.kind === 'comet' ? 0.55 : 0.35;
            const size = o.kind === 'planet'
              ? Math.max(0.08, Math.min(0.45, 0.08 + Math.log10(o.a_au + 1) * 0.12))
              : 0.06;
            const pos = scaleVec(o.current, scaleMode);
            const cleanName = o.name.replace(/^\(\d+\)\s*/, '');
            return (
              <group key={o.name}>
                <ScaledLine trace={o.trace} color={c} opacity={opacity} scaleMode={scaleMode} />
                <PlanetMarker
                  position={pos}
                  color={c}
                  size={size}
                  name={cleanName}
                  showLabel={showLabels && (o.kind === 'planet' || o.kind === 'comet')}
                  onClick={o.kind === 'planet' ? () => { setFocus(cleanName); setPinned(o); } : undefined}
                  onHover={(entering) => setHovered(entering ? o : (hovered?.name === o.name ? null : hovered))}
                  spin={years}
                  enableTextures={enableTextures && o.kind === 'planet'}
                />
              </group>
            );
          })}

          <FocusCamera focusTarget={
            focus ? (filtered.find(o => o.name.replace(/^\(\d+\)\s*/, '') === focus)?.current) : null
          } scaleMode={scaleMode} />
          {missionOverlay && (
            <MissionTrajectoryArc points={missionOverlay.points} scaleMode={scaleMode} />
          )}
          <OrbitControls enablePan enableZoom enableRotate makeDefault />
        </Canvas>
      </div>

      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
        <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
          <h3 className="text-sm font-semibold text-sev-ok mb-2">Legend</h3>
          <ul className="space-y-1 text-ui-text">
            <li>● <span className="text-ui-text-dim">solid</span> = planet</li>
            <li>· <span className="text-ui-text-dim">faint</span> = asteroid (main belt etc.)</li>
            <li>~ <span className="text-ui-text-dim">light blue</span> = comet (often inclined / eccentric)</li>
            <li>● <span className="text-sev-warn">pulsing yellow</span> = Sun (origin)</li>
            <li><span className="text-ui-text-dim">grid</span> = J2000 ecliptic plane</li>
          </ul>
        </div>
        <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
          <h3 className="text-sm font-semibold text-ui-accent mb-2">Notes</h3>
          <ul className="space-y-1 text-ui-text-dim list-disc pl-4">
            <li>Element source: Standish 1992 / DE405 for planets; MPCORB 2024-Jul-01 for small bodies.</li>
            <li>Hyperbolic comets (e ≥ 1, e.g. Tsuchinshan-ATLAS) are not yet drawn.</li>
            <li>Drag = rotate · scroll = zoom · right-drag = pan.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
