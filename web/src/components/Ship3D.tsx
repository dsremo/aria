/**
 * 3D ship viewer — ARIA-specific decoration layer on top of the
 * reusable {@link ModelViewer3D} primitive.
 *
 * ModelViewer3D provides the generic Canvas + OrbitControls + lighting +
 * shading modes + gizmo + error-boundary + glTF loader. Ship3D extends
 * it via the `enhanceScene` / `useFrameCallback` / `extraCanvasChildren`
 * hooks with every ARIA-specific visual treatment:
 *
 *   · Per-part PBR overrides (PART_MATS)
 *   · Procedural additions (ring braces, dorsal mast + dish, keel rails,
 *     hull greeble rings, radiator hot-edges, lit-window hab modules,
 *     nav beacons, plasma plume, endpoint glow shells, reactor+nozzle
 *     point lights)
 *   · Hover labels with part-info metadata
 *   · Emissive pulsing (reactor + nozzle + engine bells + beacons)
 *   · Explode-view, isolate mode, wireframe, clean-view, showFx toggles
 *   · Camera presets (fore / aft / port / starboard / top / 3⁄4)
 *   · Zoom-in / zoom-out / fit-to-ship actions
 *   · Deployment slider (stowed ↔ cruise) animating radiator+mast+dish
 *   · Starfield backdrop
 *
 * The raw glTF is fetched from /api/ship.gltf (64 parts: hull, 7-layer
 * shield, habitat ring, 24 hab modules, 6 spokes, 4 engine bells,
 * radiators, fuel tanks, docking ports, antennas).
 */

import { Html } from '@react-three/drei';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';

import { ModelViewer3D, type EnhanceSceneFn } from './model-viewer/ModelViewer3D';

// ── Part metadata (shown in the hover-tooltip) ───────────────────────
// Maps every part-id the user might hover to a short human title +
// single-line subtitle. Non-listed ids fall back to the raw id.
const PART_INFO: Record<string, { name: string; subtitle: string; color: string }> = {
  hull_main:        { name: 'Pressure Hull',        subtitle: 'Ti-6Al-4V · 712 m · 80 mm',         color: 'text-ui-text' },
  reactor_engine:   { name: 'Fusion Reactor',       subtitle: 'D/He-3 · 100 MWt',                  color: 'text-sev-crit' },
  habitat_ring:     { name: 'Habitat Ring',         subtitle: "O'Neill · ⌀1000 m · 0.56 g",         color: 'text-sev-warn' },
  magnetic_nozzle:  { name: 'Magnetic Nozzle',      subtitle: 'Plasma exit · 10 kN/s',             color: 'text-ui-accent' },
  bow_sensor_ring:  { name: 'Bow Sensor Array',     subtitle: 'LIDAR · Optical · IR',              color: 'text-sky-300' },
  shield_layer_0:   { name: 'Shield L0 · LIDAR',    subtitle: 'Detection layer',                   color: 'text-sev-ok' },
  shield_layer_1:   { name: 'Shield L1 · Plasma',   subtitle: 'Active plasma deflector',           color: 'text-sev-ok' },
  shield_layer_2:   { name: 'Shield L2 · Magnetic', subtitle: 'Superconducting coil',              color: 'text-sev-ok' },
  shield_layer_3:   { name: 'Shield L3 · Grid',     subtitle: 'Electrostatic tungsten mesh',       color: 'text-sev-ok' },
  shield_layer_4:   { name: 'Shield L4 · Ice',      subtitle: 'Ablation water ice · 5.45 m',       color: 'text-sev-ok' },
  shield_layer_5:   { name: 'Shield L5 · Whipple',  subtitle: 'SiC-Kevlar-Al bumper',              color: 'text-sev-ok' },
  shield_layer_6:   { name: 'Shield L6 · Hull',     subtitle: 'Structural Ti-HealTech',            color: 'text-sev-ok' },
  radiator_array_0: { name: 'Heat Wing +Y',         subtitle: 'NaK loop · 50 k m²',                color: 'text-sev-warn' },
  radiator_array_1: { name: 'Heat Wing −Y',         subtitle: 'NaK loop · 50 k m²',                color: 'text-sev-warn' },
  fuel_tank_0:      { name: 'Cryo Tank A',          subtitle: 'D/He-3 · 28 kt',                       color: 'text-ui-text' },
  fuel_tank_1:      { name: 'Cryo Tank B',          subtitle: 'D/He-3 · 28 kt',                       color: 'text-ui-text' },
  fuel_tank_2:      { name: 'Cryo Tank C',          subtitle: 'D/He-3 · 28 kt',                       color: 'text-ui-text' },
};
function partInfoFor(id: string): { name: string; subtitle: string; color: string } {
  if (PART_INFO[id]) return PART_INFO[id];
  if (id.startsWith('engine_bell_'))  return { name: `Engine Bell ${id.slice(-1)}`,  subtitle: 'Plasma nozzle',               color: 'text-sev-warn' };
  if (id.startsWith('spoke_'))         return { name: `Spoke ${id.slice(-1)}`,         subtitle: 'Ring tension member',         color: 'text-ui-text' };
  if (id.startsWith('hab_module_'))    return { name: `Hab Module ${id.slice(-2).replace('_','')}`, subtitle: 'Lit quarters · ~42 crew', color: 'text-sev-warn' };
  if (id.startsWith('hull_stiffener_')) return { name: `Ring Frame ${id.slice(-1)}`,   subtitle: 'Hull stiffener',              color: 'text-ui-text' };
  if (id.startsWith('docking_port_'))  return { name: `Docking Port ${id.slice(-1)}`,  subtitle: 'IDSS-compatible',             color: 'text-ui-text' };
  if (id.startsWith('comm_antenna_'))  return { name: `Ka-Band Array ${id.slice(-1)}`, subtitle: 'Long-haul comms',             color: 'text-sky-300' };
  return { name: id.replace(/_/g, ' '), subtitle: 'part', color: 'text-ui-text' };
}

export type CameraPreset = 'fore' | 'aft' | 'port' | 'starboard' | 'top' | 'threequarter';
export type ZoomAction = 'in' | 'out' | 'fit';

interface ShipProps {
  onPartClick: (partId: string) => void;
  hoveredPartId: string | null;
  setHoveredPart: (id: string | null) => void;
  showStats: boolean;
  // ── Viewer controls (driven from the floating toolbar in App.tsx) ──
  explodeAmount?: number;          // 0 = assembled, 1 = parts pushed out by 1× their distance from center
  isolatePartId?: string | null;   // when set, fade all other meshes to ~8 % opacity
  wireframe?: boolean;             // toggle all PBR materials to wireframe
  reloadKey?: number;              // bump to force re-fetch of /api/ship.gltf after a rebuild
  showLabels?: boolean;            // overlay part-name pills at major subsystems
  cameraPreset?: CameraPreset | null;  // when it flips, viewer slams camera to that angle
  cameraPresetNonce?: number;          // re-trigger presets when the user re-clicks
  cleanView?: boolean;             // hide minor detail parts for a clean primitive silhouette
  showFx?: boolean;                // enable additive glows / plume / strobe sprites (off → solid primitives only)
  zoomAction?: ZoomAction | null;  // toolbar click target
  zoomActionNonce?: number;        // re-trigger on repeat clicks
  deployment?: number;             // 0 = stowed (launch config) → 1 = fully deployed (cruise config)
}

// ── Per-part PBR overrides — mirrors engineering_lab.html PART_MATS ───
// Each major subsystem uses a visibly distinct hue so the ship reads as
// colour-coded primitives rather than a uniform grey mass.
const PART_MATS: Record<string, {
  color?: number; metalness?: number; roughness?: number;
  emissive?: number; emissiveIntensity?: number;
}> = {
  hull_main:        { color: 0xe4ebf5, metalness: 0.30, roughness: 0.50 },
  reactor_engine:   { color: 0xff6644, metalness: 0.20, roughness: 0.35, emissive: 0xff3300, emissiveIntensity: 0.9 },
  habitat_ring:     { color: 0xffc84a, metalness: 0.20, roughness: 0.45, emissive: 0x554422, emissiveIntensity: 0.28 },
  magnetic_nozzle:  { color: 0x66aaff, metalness: 0.30, roughness: 0.35, emissive: 0x3377ff, emissiveIntensity: 1.30 },
  bow_sensor_ring:  { color: 0xe8eef8, metalness: 0.35, roughness: 0.35, emissive: 0x4488ff, emissiveIntensity: 0.45 },
  shield_layer_0:   { color: 0x88d0ff, metalness: 0.40, roughness: 0.35, emissive: 0x66aaff, emissiveIntensity: 0.55 },
  shield_layer_1:   { color: 0xb088ff, metalness: 0.25, roughness: 0.45, emissive: 0x5533aa, emissiveIntensity: 0.30 },
  shield_layer_2:   { color: 0xffe044, metalness: 0.55, roughness: 0.25, emissive: 0x775522, emissiveIntensity: 0.35 },
  shield_layer_3:   { color: 0xff9944, metalness: 0.40, roughness: 0.40, emissive: 0x662200, emissiveIntensity: 0.15 },
  shield_layer_4:   { color: 0xc8e8ff, metalness: 0.05, roughness: 0.35, emissive: 0x1a3c66, emissiveIntensity: 0.12 },
  shield_layer_5:   { color: 0x909aae, metalness: 0.55, roughness: 0.55 },
  shield_layer_6:   { color: 0xd4d8dc, metalness: 0.50, roughness: 0.45 },
};

for (let i = 0; i < 5; i++)  PART_MATS[`hull_stiffener_${i}`] = { color: 0x98a0b0, metalness: 0.35, roughness: 0.45 };
for (let i = 0; i < 3; i++)  PART_MATS[`fuel_tank_${i}`]      = { color: 0xf0f4fa, metalness: 0.15, roughness: 0.55, emissive: 0x114466, emissiveIntensity: 0.20 };
for (let i = 0; i < 2; i++)  PART_MATS[`radiator_array_${i}`] = { color: 0x6fb5ff, metalness: 0.20, roughness: 0.40, emissive: 0xff6622, emissiveIntensity: 0.85 };
for (let i = 0; i < 6; i++)  PART_MATS[`spoke_${i}`]          = { color: 0xb0bac8, metalness: 0.40, roughness: 0.40 };
for (let i = 0; i < 4; i++)  PART_MATS[`engine_bell_${i}`]    = { color: 0xff9933, metalness: 0.25, roughness: 0.45, emissive: 0xff5500, emissiveIntensity: 0.65 };
for (let i = 0; i < 24; i++) PART_MATS[`hab_module_${i}`]     = { color: 0xffdf88, metalness: 0.15, roughness: 0.45, emissive: 0xffc066, emissiveIntensity: 0.85 };
for (let i = 0; i < 4; i++)  PART_MATS[`docking_port_${i}`]   = { color: 0xc6d2e0, metalness: 0.30, roughness: 0.40, emissive: 0x3355aa, emissiveIntensity: 0.40 };
for (let i = 0; i < 4; i++)  PART_MATS[`comm_antenna_${i}`]   = { color: 0xe6ecf8, metalness: 0.35, roughness: 0.35, emissive: 0x4488ff, emissiveIntensity: 0.50 };


// ── Endpoint glows — per engineering_lab.html addEndpointGlows() ─────
const GLOW_DEFS: { name: string; color: number; opacity: number; scale: number }[] = [
  { name: 'magnetic_nozzle', color: 0x3377ff, opacity: 0.32, scale: 3.5 },
  { name: 'reactor_engine',  color: 0xff4400, opacity: 0.22, scale: 4.0 },
  { name: 'shield_layer_0',  color: 0x66ddff, opacity: 0.18, scale: 0.7 },
  { name: 'bow_sensor_ring', color: 0x66aaff, opacity: 0.20, scale: 0.6 },
];


// ── Radial-gradient sprite used by the plume particles ──────────────
function makeRadialSprite(inner: string, outer: string, size = 64): THREE.Texture {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const g = c.getContext('2d')!;
  const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grad.addColorStop(0.0, inner);
  grad.addColorStop(0.4, outer);
  grad.addColorStop(1.0, 'rgba(0,0,0,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, size, size);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}


// ── Lit-window emissiveMap for hab modules ──────────────────────────
function makeHabWindowTexture(): THREE.Texture {
  const size = 256;
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const g = c.getContext('2d')!;
  g.fillStyle = '#1a1812';
  g.fillRect(0, 0, size, size);
  g.strokeStyle = '#332820';
  g.lineWidth = 1;
  for (let i = 1; i < 6; i++) { const x = (i * size) / 6; g.beginPath(); g.moveTo(x, 0); g.lineTo(x, size); g.stroke(); }
  for (let i = 1; i < 8; i++) { const y = (i * size) / 8; g.beginPath(); g.moveTo(0, y); g.lineTo(size, y); g.stroke(); }
  const cw = size / 6, ch = size / 8;
  for (let i = 0; i < 6; i++) {
    for (let j = 0; j < 8; j++) {
      if (Math.random() > 0.28) {
        const x = i * cw + cw * 0.25;
        const y = j * ch + ch * 0.25;
        const w = cw * 0.50;
        const h = ch * 0.45;
        const warmth = 0.85 + Math.random() * 0.15;
        const r = Math.floor(255 * warmth);
        const grn = Math.floor(205 * warmth);
        const b = Math.floor(100 * warmth);
        g.fillStyle = `rgb(${r},${grn},${b})`;
        g.fillRect(x, y, w, h);
      }
    }
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(2, 1);
  return tex;
}

// ── Scene-side ref payload ──────────────────────────────────────────
// Everything the prop-driven effects need to touch on the loaded glTF
// scene graph. Populated by enhanceScene and read by the hover /
// wireframe / isolate / clean-view / FX / camera-preset / zoom effects.
type ShipSceneCache = {
  scene: THREE.Object3D;
  allMeshes: THREE.Mesh[];
  rotating: THREE.Object3D[];
  glows: THREE.Mesh[];
  pulsing: { mesh: THREE.Mesh; base: number; amp: number; phase: number; rate: number }[];
  plume: { points: THREE.Points; velocities: Float32Array; count: number; origin: THREE.Vector3; exitRadius: number } | null;
  assembly: { obj: THREE.Object3D; basePos: THREE.Vector3; outDir: THREE.Vector3; distFromCenter: number }[];
  shipCenter: THREE.Vector3;
  deployables: { obj: THREE.Object3D; baseScale: THREE.Vector3; stowedScale: THREE.Vector3; axis: 'x' | 'y' | 'z' }[];
  // Refs to the reactor + nozzle point-lights that live in extraCanvasChildren.
  reactorLight: THREE.PointLight | null;
  nozzleLight: THREE.PointLight | null;
};


export function Ship3D({
  onPartClick, hoveredPartId, setHoveredPart, showStats,
  explodeAmount = 0, isolatePartId = null, wireframe = false, reloadKey = 0,
  showLabels = false, cameraPreset = null, cameraPresetNonce = 0, cleanView = false,
  showFx = false, zoomAction = null, zoomActionNonce = 0, deployment = 1,
}: ShipProps) {
  // Shared scene-side cache + camera/controls handles. enhanceScene
  // populates; prop-driven effects below mutate via this ref.
  const cacheRef = useRef<ShipSceneCache | null>(null);
  const cameraRef = useRef<THREE.Camera | null>(null);
  const controlsRef = useRef<any>(null);
  const reactorLightRef = useRef<THREE.PointLight>(null);
  const nozzleLightRef  = useRef<THREE.PointLight>(null);

  // Re-render whenever reactor/nozzle refs latch — used so enhanceScene
  // can link them into the cache the first time it runs.
  // Bumped when enhanceScene sets up a fresh cache so prop-driven
  // effects re-run against the new scene.
  const cacheVersionRef = useRef(0);
  const reloadTickRef = useRef(0);

  // ── enhanceScene: the single ARIA decoration pipeline. ──
  // Callback identity MUST be stable across renders (we don't want
  // ModelViewer3D to tear down + re-run it every time a prop flips),
  // so all volatile state (hover id, explode amount, etc.) is read
  // from refs rather than closed-over values.
  const hoveredPartIdRef = useRef<string | null>(hoveredPartId);
  const explodeAmountRef = useRef(explodeAmount);
  const deploymentRef = useRef(deployment);
  const showFxRef = useRef(showFx);
  hoveredPartIdRef.current = hoveredPartId;
  explodeAmountRef.current = explodeAmount;
  deploymentRef.current = deployment;
  showFxRef.current = showFx;

  const enhanceScene: EnhanceSceneFn = useCallback((scene, camera, controls) => {
    cameraRef.current = camera;
    controlsRef.current = controls;
    const allMeshes: THREE.Mesh[] = [];
    const rotating: THREE.Object3D[] = [];

    const habWindowTex = makeHabWindowTexture();
    let plumeSpriteTex: THREE.Texture | null = null; // tracked for disposal

    scene.traverse((c) => {
      if (c.name && (c.name === 'habitat_ring' ||
                     c.name.startsWith('spoke_') ||
                     c.name.startsWith('hab_module_'))) {
        rotating.push(c);
      }
      if (!(c as THREE.Mesh).isMesh) return;
      const mesh = c as THREE.Mesh;
      allMeshes.push(mesh);
      (mesh as any).cursor = 'pointer';
      const pm = PART_MATS[mesh.name] ?? { color: 0xb0b8c4, metalness: 0.35, roughness: 0.45 };
      const isHab = mesh.name.startsWith('hab_module_');
      const baseColorHex = pm.color ?? 0xb0b8c4;
      // UNLIT MeshBasicMaterial — renders the part's colour directly
      // without sampling the lighting environment. Critical: with
      // MeshStandardMaterial the non-sun-facing surfaces all read
      // near-black in the absence of an HDRI env map.
      const m = new THREE.MeshBasicMaterial({
        color: baseColorHex,
        map: isHab ? habWindowTex : null,
        transparent: false,
        opacity: 1.0,
      });
      (m as any)._origColorHex = baseColorHex;
      (m as any)._origEmissiveI = pm.emissiveIntensity ?? 0;
      const prev = mesh.material as THREE.Material | THREE.Material[];
      if (Array.isArray(prev)) prev.forEach(p => p.dispose());
      else prev?.dispose?.();
      mesh.material = m;
      (mesh as any)._origEmissiveIntensity = 0;
    });

    // ── Build endpoint glow shells ──
    const glows: THREE.Mesh[] = [];
    const tmpBox = new THREE.Box3();
    const tmpCenter = new THREE.Vector3();
    const tmpSize = new THREE.Vector3();
    const addGlow = (target: THREE.Object3D, color: number, opacity: number, scale: number) => {
      tmpBox.setFromObject(target);
      if (!isFinite(tmpBox.min.x)) return;
      tmpBox.getCenter(tmpCenter);
      const diag = tmpBox.getSize(tmpSize).length();
      {
        const geo = new THREE.SphereGeometry(diag * scale, 24, 24);
        const mat = new THREE.MeshBasicMaterial({
          color, transparent: true, opacity, side: THREE.BackSide, depthWrite: false,
          blending: THREE.AdditiveBlending,
        });
        const glow = new THREE.Mesh(geo, mat);
        glow.position.copy(tmpCenter);
        glow.name = target.name + '_glow_outer';
        glow.raycast = () => {};
        scene.add(glow);
        glows.push(glow);
      }
      {
        const geo = new THREE.SphereGeometry(diag * scale * 0.35, 16, 16);
        const mat = new THREE.MeshBasicMaterial({
          color, transparent: true, opacity: Math.min(1.0, opacity * 2.2),
          side: THREE.BackSide, depthWrite: false, blending: THREE.AdditiveBlending,
        });
        const core = new THREE.Mesh(geo, mat);
        core.position.copy(tmpCenter);
        core.name = target.name + '_glow_inner';
        core.raycast = () => {};
        scene.add(core);
        glows.push(core);
      }
    };
    for (const def of GLOW_DEFS) {
      const t = scene.getObjectByName(def.name);
      if (t) addGlow(t, def.color, def.opacity, def.scale);
    }
    scene.traverse((c) => {
      if (!(c as THREE.Mesh).isMesh) return;
      if (c.name?.startsWith('engine_bell_')) {
        addGlow(c, 0xff7722, 0.30, 2.8);
      }
    });

    // ── Pulsing emissives ──
    const pulsing: ShipSceneCache['pulsing'] = [];
    const pushPulse = (name: string, base: number, amp: number, rate: number) => {
      const m = scene.getObjectByName(name) as THREE.Mesh | undefined;
      if (!m || !(m.material as THREE.MeshStandardMaterial)?.emissive) return;
      pulsing.push({ mesh: m, base, amp, rate, phase: Math.random() * Math.PI * 2 });
      (m as any)._origEmissiveIntensity = base;
    };
    pushPulse('reactor_engine',  1.3, 0.35, 2.2);
    pushPulse('magnetic_nozzle', 1.8, 0.45, 3.0);
    scene.traverse(c => {
      if (!(c as THREE.Mesh).isMesh) return;
      if (c.name?.startsWith('engine_bell_')) {
        pushPulse(c.name, 0.85, 0.25, 2.6 + Math.random());
      }
    });

    // ── Nozzle plume particle system ──
    let plume: ShipSceneCache['plume'] = null;
    const nozzle = scene.getObjectByName('magnetic_nozzle') as THREE.Mesh | undefined;
    if (nozzle) {
      tmpBox.setFromObject(nozzle);
      tmpBox.getCenter(tmpCenter);
      const nozzleSize = tmpBox.getSize(tmpSize).length();
      const count = 400;
      const positions  = new Float32Array(count * 3);
      const colors     = new Float32Array(count * 3);
      const velocities = new Float32Array(count);
      for (let i = 0; i < count; i++) {
        positions[i * 3]     = tmpCenter.x - Math.random() * nozzleSize * 4;
        positions[i * 3 + 1] = tmpCenter.y + (Math.random() - 0.5) * nozzleSize * 0.3;
        positions[i * 3 + 2] = tmpCenter.z + (Math.random() - 0.5) * nozzleSize * 0.3;
        colors[i * 3]     = 0.3 + Math.random() * 0.4;
        colors[i * 3 + 1] = 0.6 + Math.random() * 0.3;
        colors[i * 3 + 2] = 1.0;
        velocities[i] = nozzleSize * (0.8 + Math.random() * 1.4);
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      geo.setAttribute('color',    new THREE.BufferAttribute(colors, 3));
      plumeSpriteTex = makeRadialSprite('rgba(200,230,255,1)', 'rgba(60,140,255,0.55)');
      const plumeSprite = plumeSpriteTex;
      const mat = new THREE.PointsMaterial({
        size: nozzleSize * 0.22,
        map: plumeSprite,
        alphaTest: 0.01,
        vertexColors: true,
        transparent: true,
        opacity: 0.95,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        sizeAttenuation: true,
      });
      const pts = new THREE.Points(geo, mat);
      pts.name = 'nozzle_plume';
      pts.raycast = () => {};
      scene.add(pts);
      plume = { points: pts, velocities, count, origin: tmpCenter.clone(), exitRadius: nozzleSize * 0.5 };
    }

    // ── Habitat-ring cross-brace struts ──
    (() => {
      const ring = scene.getObjectByName('habitat_ring') as THREE.Mesh | undefined;
      if (!ring) return;
      const rbox = new THREE.Box3().setFromObject(ring);
      const rcenter = rbox.getCenter(new THREE.Vector3());
      const rradius = Math.max(rbox.max.y - rbox.min.y, rbox.max.z - rbox.min.z) / 2;
      const braceCount = 6;
      for (let i = 0; i < braceCount; i++) {
        const a = (i / braceCount) * Math.PI;
        const p1 = new THREE.Vector3(rcenter.x, rcenter.y + Math.sin(a) * rradius, rcenter.z + Math.cos(a) * rradius);
        const p2 = new THREE.Vector3(rcenter.x, rcenter.y - Math.sin(a) * rradius, rcenter.z - Math.cos(a) * rradius);
        const len = p1.distanceTo(p2);
        const geo = new THREE.CylinderGeometry(rradius * 0.025, rradius * 0.025, len, 12);
        const mat = new THREE.MeshBasicMaterial({ color: 0xc8ced8 });
        const brace = new THREE.Mesh(geo, mat);
        brace.position.copy(rcenter);
        const axis = p2.clone().sub(p1).normalize();
        const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), axis);
        brace.quaternion.copy(q);
        brace.name = 'ring_brace_' + i;
        brace.raycast = () => {};
        scene.add(brace);
        glows.push(brace);
        rotating.push(brace);
      }
    })();

    // ── Dorsal antenna mast + dish ──
    (() => {
      const hull = scene.getObjectByName('hull_main') as THREE.Mesh | undefined;
      if (!hull) return;
      const hbox = new THREE.Box3().setFromObject(hull);
      const hrad = Math.max(hbox.max.y - hbox.min.y, hbox.max.z - hbox.min.z) / 2;
      const mastHeight = hrad * 2.5;
      {
        const geo = new THREE.CylinderGeometry(hrad * 0.035, hrad * 0.055, mastHeight, 8);
        const mat = new THREE.MeshStandardMaterial({ color: 0xaab0bc, metalness: 0.7, roughness: 0.3 });
        const mast = new THREE.Mesh(geo, mat);
        mast.position.set(hbox.max.x - hrad * 1.5, hbox.max.y + mastHeight / 2, 0);
        mast.rotation.z = -0.15;
        mast.name = 'dorsal_mast';
        mast.raycast = () => {};
        scene.add(mast);
        glows.push(mast);
      }
      {
        const dish = new THREE.Mesh(
          new THREE.SphereGeometry(hrad * 0.45, 16, 12, 0, Math.PI * 2, 0, Math.PI / 2),
          new THREE.MeshStandardMaterial({
            color: 0xe6e9f0, metalness: 0.4, roughness: 0.35,
            emissive: 0x223344, emissiveIntensity: 0.08, side: THREE.DoubleSide,
          }),
        );
        dish.position.set(hbox.max.x - hrad * 1.5 - Math.sin(-0.15) * mastHeight,
                          hbox.max.y + mastHeight, 0);
        dish.rotation.x = -Math.PI / 2;
        dish.name = 'comm_dish';
        dish.raycast = () => {};
        scene.add(dish);
        glows.push(dish);
      }
    })();

    // ── Longitudinal keel-truss rails ──
    (() => {
      const hull = scene.getObjectByName('hull_main') as THREE.Mesh | undefined;
      if (!hull) return;
      const hbox = new THREE.Box3().setFromObject(hull);
      const hlen = hbox.max.x - hbox.min.x;
      const hrad = Math.max(hbox.max.y - hbox.min.y, hbox.max.z - hbox.min.z) / 2;
      for (const zSign of [1, -1]) {
        const geo = new THREE.BoxGeometry(hlen * 0.85, hrad * 0.03, hrad * 0.03);
        const mat = new THREE.MeshStandardMaterial({
          color: 0x8a94a8, metalness: 0.55, roughness: 0.4,
          emissive: 0x112233, emissiveIntensity: 0.10,
        });
        const rail = new THREE.Mesh(geo, mat);
        rail.position.set((hbox.min.x + hbox.max.x) / 2, hbox.min.y - hrad * 0.08, zSign * hrad * 0.6);
        rail.name = 'keel_rail_' + (zSign > 0 ? 'stbd' : 'port');
        rail.raycast = () => {};
        scene.add(rail);
        glows.push(rail);
      }
    })();

    // ── Greebles: panel-band stripes on the hull ──
    (() => {
      const hull = scene.getObjectByName('hull_main') as THREE.Mesh | undefined;
      if (!hull) return;
      const hbox = new THREE.Box3().setFromObject(hull);
      const hcenter = hbox.getCenter(new THREE.Vector3());
      const hlen  = hbox.max.x - hbox.min.x;
      const hrad  = Math.max(hbox.max.y - hbox.min.y, hbox.max.z - hbox.min.z) / 2;
      const stripeCount = 14;
      for (let i = 1; i < stripeCount; i++) {
        const x = hbox.min.x + (hlen * i) / stripeCount;
        const geo = new THREE.TorusGeometry(hrad * 1.015, hrad * 0.012, 6, 64);
        const mat = new THREE.MeshStandardMaterial({
          color: 0x6a7790, metalness: 0.6, roughness: 0.35,
          emissive: 0x223344, emissiveIntensity: 0.25,
        });
        const ring = new THREE.Mesh(geo, mat);
        ring.rotation.y = Math.PI / 2;
        ring.position.set(x, hcenter.y, hcenter.z);
        ring.name = 'hull_greeble_' + i;
        ring.raycast = () => {};
        scene.add(ring);
        glows.push(ring);
      }
    })();

    // ── Radiator hot-edge strips ──
    scene.traverse(c => {
      if (!(c as THREE.Mesh).isMesh) return;
      if (!c.name?.startsWith('radiator_array_')) return;
      const box = new THREE.Box3().setFromObject(c);
      const size = box.getSize(new THREE.Vector3());
      const center = box.getCenter(new THREE.Vector3());
      const longest = Math.max(size.x, size.y, size.z);
      const geo = new THREE.BoxGeometry(longest * 0.98, longest * 0.015, longest * 0.015);
      const mat = new THREE.MeshStandardMaterial({
        color: 0xff7733, metalness: 0.0, roughness: 0.8,
        emissive: 0xff5522, emissiveIntensity: 1.6,
      });
      const strip = new THREE.Mesh(geo, mat);
      strip.position.copy(center);
      strip.name = c.name + '_hot_edge';
      strip.raycast = () => {};
      scene.add(strip);
      glows.push(strip);
    });

    // ── Navigation beacon lights ──
    scene.traverse(c => {
      if (!(c as THREE.Mesh).isMesh) return;
      if (!c.name || !(c.name.startsWith('docking_port_') || c.name === 'bow_sensor_ring')) return;
      const box = new THREE.Box3().setFromObject(c);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3()).length();
      const isBow = c.name === 'bow_sensor_ring';
      const color = isBow ? 0xffffff : 0xff3333;
      const geo = new THREE.SphereGeometry(size * 0.08, 10, 10);
      const mat = new THREE.MeshStandardMaterial({
        color,
        emissive: new THREE.Color(color),
        emissiveIntensity: 2.0,
        metalness: 0.0,
        roughness: 0.35,
      });
      const beacon = new THREE.Mesh(geo, mat);
      beacon.position.copy(center);
      beacon.name = c.name + '_beacon';
      (beacon as any)._pulsePhase = Math.random() * Math.PI * 2;
      (beacon as any)._pulseRate  = 1.8 + Math.random() * 0.8;
      beacon.raycast = () => {};
      scene.add(beacon);
      glows.push(beacon);
    });

    // ── Capture assembly offsets for explode-view ──
    const shipBox = new THREE.Box3().setFromObject(scene);
    const shipCenter = shipBox.getCenter(new THREE.Vector3());
    const assembly: ShipSceneCache['assembly'] = [];
    const seen = new Set<THREE.Object3D>();
    scene.traverse(c => {
      if (seen.has(c)) return;
      if (!(c as THREE.Mesh).isMesh) return;
      if (c.name.endsWith('_glow_outer') || c.name.endsWith('_glow_inner') ||
          c.name === 'nozzle_plume') return;
      // Habitat ring + its children (spokes, hab modules, cross-braces) rotate
      // as a unit — exclude from explode-view so they stay assembled.
      if (c.name === 'habitat_ring' || c.name.startsWith('spoke_') ||
          c.name.startsWith('hab_module_') || c.name.startsWith('ring_brace_')) return;
      const box = new THREE.Box3().setFromObject(c);
      const partCenter = box.getCenter(new THREE.Vector3());
      const out = partCenter.clone().sub(shipCenter);
      const dist = out.length();
      if (dist > 1e-3) out.divideScalar(dist);
      assembly.push({
        obj: c,
        basePos: c.position.clone(),
        outDir: out,
        distFromCenter: dist,
      });
      seen.add(c);
    });

    // ── Capture deployable-part baselines ──
    const deployables: ShipSceneCache['deployables'] = [];
    const registerDeployable = (name: string, axis: 'x' | 'y' | 'z', stowedFactor: number) => {
      const obj = scene.getObjectByName(name);
      if (!obj) return;
      const baseScale = obj.scale.clone();
      const stowedScale = baseScale.clone();
      stowedScale[axis] = baseScale[axis] * stowedFactor;
      deployables.push({ obj, baseScale, stowedScale, axis });
    };
    registerDeployable('radiator_array_0', 'z', 0.02);
    registerDeployable('radiator_array_1', 'z', 0.02);
    registerDeployable('dorsal_mast', 'y', 0.05);
    registerDeployable('comm_dish',  'x', 0.1);
    for (let i = 0; i < 4; i++) registerDeployable(`comm_antenna_${i}`, 'y', 0.1);

    cacheRef.current = {
      scene, allMeshes, rotating, glows, pulsing, plume, assembly, shipCenter, deployables,
      reactorLight: reactorLightRef.current,
      nozzleLight: nozzleLightRef.current,
    };
    cacheVersionRef.current += 1;
    reloadTickRef.current += 1;

    // ── Auto-fit camera to ship bounds ──
    const box = new THREE.Box3().setFromObject(scene);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3()).length();
    if (size > 0 && isFinite(size)) {
      const dist = Math.max(size * 0.55, 50);
      (camera as THREE.PerspectiveCamera).near = Math.max(1.0, dist * 0.005);
      (camera as THREE.PerspectiveCamera).far  = dist * 15;
      (camera as THREE.PerspectiveCamera).updateProjectionMatrix();
      camera.position.copy(center).add(new THREE.Vector3(dist * 0.38, dist * 0.26, dist * 0.92));
      if (controls) {
        controls.minDistance = Math.max(20, size * 0.03);
        controls.maxDistance = size * 2.5;
        controls.target.copy(center);
        controls.update();
      }
      if (reactorLightRef.current) {
        reactorLightRef.current.position.set(box.min.x + size * 0.04, center.y, center.z);
        reactorLightRef.current.distance = size * 0.5;
      }
      if (nozzleLightRef.current) {
        nozzleLightRef.current.position.set(box.min.x + size * 0.005, center.y, center.z);
        nozzleLightRef.current.distance = size * 0.4;
      }
    }

    // Return disposer — runs on next load (or unmount) to release all
    // procedural geometry. The parts that came straight from the glTF
    // loader are left to react-three-fiber's caching layer.
    return () => {
      for (const g of glows) {
        scene.remove(g);
        g.geometry.dispose();
        (g.material as THREE.Material).dispose();
      }
      if (plume) {
        scene.remove(plume.points);
        plume.points.geometry.dispose();
        (plume.points.material as THREE.Material).dispose();
      }
      // Dispose canvas textures to prevent GPU memory leak on reload
      habWindowTex.dispose();
      plumeSpriteTex?.dispose();
      if (cacheRef.current?.scene === scene) cacheRef.current = null;
    };
    // Intentionally stable — prop-driven state flows through refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Hover highlight ──
  useEffect(() => {
    const cache = cacheRef.current;
    if (!cache) return;
    for (const mesh of cache.allMeshes) {
      const mat = mesh.material as THREE.MeshStandardMaterial | THREE.MeshBasicMaterial;
      if (!mat?.color) continue;
      const hovered = mesh.name === hoveredPartId;
      const origColor = (mat as any)._origColorHex;
      if (origColor === undefined) {
        (mat as any)._origColorHex = mat.color.getHex();
      }
      const base = (mat as any)._origColorHex ?? mat.color.getHex();
      if (hovered) {
        const c = new THREE.Color(base).lerp(new THREE.Color(0x33ccff), 0.5);
        mat.color.copy(c);
      } else {
        mat.color.setHex(base);
      }
    }
  }, [hoveredPartId, reloadKey]);

  // ── FX toggle: point-light intensity ──
  useEffect(() => {
    if (reactorLightRef.current) reactorLightRef.current.intensity = showFx ? 3.2 : 0.0;
    if (nozzleLightRef.current)  nozzleLightRef.current.intensity  = showFx ? 2.8 : 0.0;
  }, [showFx]);

  // ── Isolate ──
  useEffect(() => {
    const cache = cacheRef.current;
    if (!cache) return;
    for (const mesh of cache.allMeshes) {
      const mat = mesh.material as THREE.MeshStandardMaterial;
      if (!mat) continue;
      const belongs = !isolatePartId || mesh.name === isolatePartId ||
        (isolatePartId === 'habitat_ring' &&
          (mesh.name.startsWith('spoke_') || mesh.name.startsWith('hab_module_')));
      if (belongs) {
        mat.transparent = false;
        mat.opacity = 1.0;
        mat.depthWrite = true;
      } else {
        mat.transparent = true;
        mat.opacity = 0.08;
        mat.depthWrite = false;
      }
    }
    for (const g of cache.glows) {
      const target = isolatePartId && (g.name.startsWith(isolatePartId) ||
        (isolatePartId === 'habitat_ring' && (g.name.startsWith('engine_bell_') || g.name.startsWith('magnetic_nozzle'))));
      const mat = g.material as THREE.MeshBasicMaterial;
      if (!isolatePartId) { mat.visible = true; continue; }
      mat.visible = !!target;
    }
    if (cache.plume) {
      const vis = !isolatePartId || isolatePartId === 'magnetic_nozzle';
      cache.plume.points.visible = vis;
    }
  }, [isolatePartId, reloadKey]);

  // ── Wireframe ──
  useEffect(() => {
    const cache = cacheRef.current;
    if (!cache) return;
    const apply = (obj: THREE.Object3D) => {
      const m = (obj as THREE.Mesh).material;
      if (!m) return;
      if (Array.isArray(m)) m.forEach(x => { if ('wireframe' in x) (x as any).wireframe = wireframe; });
      else if ('wireframe' in m) (m as any).wireframe = wireframe;
    };
    for (const mesh of cache.allMeshes) apply(mesh);
    for (const g of cache.glows)       apply(g);
  }, [wireframe, reloadKey]);

  // ── Clean-view + FX visibility pass ──
  useEffect(() => {
    const cache = cacheRef.current;
    if (!cache) return;
    const isFx = (name: string): boolean =>
      name.endsWith('_glow_outer') || name.endsWith('_glow_inner');
    const hideInClean = (name: string): boolean =>
      cleanView && (
        name.startsWith('hull_stiffener_') ||
        name.startsWith('docking_port_') ||
        name.startsWith('comm_antenna_') ||
        name.startsWith('hull_greeble_') ||
        name.endsWith('_hot_edge') ||
        name === 'dorsal_mast' || name === 'comm_dish' ||
        name.startsWith('keel_rail_')
      );
    for (const mesh of cache.allMeshes) {
      mesh.visible = !hideInClean(mesh.name);
    }
    for (const g of cache.glows) {
      if (isFx(g.name)) {
        g.visible = showFx;
      } else {
        g.visible = !hideInClean(g.name);
      }
    }
    if (cache.plume) cache.plume.points.visible = showFx;
  }, [cleanView, showFx, reloadKey]);

  // ── Camera presets ──
  useEffect(() => {
    const cache = cacheRef.current;
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!cameraPreset || !cache || !camera) return;
    const box = new THREE.Box3().setFromObject(cache.scene);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3()).length();
    if (!size || !isFinite(size)) return;
    const dist = size * 0.75;
    const offsets: Record<CameraPreset, [number, number, number]> = {
      fore:        [ dist * 1.05,     0,     0 ],
      aft:         [-dist * 1.05,     0,     0 ],
      port:        [ 0, dist * 0.20,  dist * 1.05],
      starboard:   [ 0, dist * 0.20, -dist * 1.05],
      top:         [ 0, dist * 1.05,  0 ],
      threequarter:[ dist * 0.38, dist * 0.26, dist * 0.92 ],
    };
    const [dx, dy, dz] = offsets[cameraPreset];
    camera.position.set(center.x + dx, center.y + dy, center.z + dz);
    if (controls) {
      controls.target.copy(center);
      controls.update();
    }
  }, [cameraPreset, cameraPresetNonce, reloadKey]);

  // ── Zoom actions ──
  useEffect(() => {
    const cache = cacheRef.current;
    const camera = cameraRef.current as THREE.PerspectiveCamera | null;
    const controls = controlsRef.current;
    if (!zoomAction || !cache || !camera) return;
    if (zoomAction === 'fit') {
      const box = new THREE.Box3().setFromObject(cache.scene);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3()).length();
      if (!size || !isFinite(size)) return;
      const dist = size * 0.55;
      camera.position.copy(center).add(new THREE.Vector3(dist * 0.38, dist * 0.26, dist * 0.92));
      camera.near = Math.max(1.0, dist * 0.005);
      camera.far  = dist * 15;
      camera.updateProjectionMatrix();
      if (controls) {
        controls.target.copy(center);
        controls.minDistance = Math.max(20, size * 0.03);
        controls.maxDistance = size * 2.5;
        controls.update();
      }
      return;
    }
    if (!controls) return;
    const factor = zoomAction === 'in' ? 0.78 : 1.28;
    const target = controls.target as THREE.Vector3;
    const offset = camera.position.clone().sub(target);
    const nextLen = Math.min(Math.max(offset.length() * factor, controls.minDistance ?? 0.01),
                             controls.maxDistance ?? 1e9);
    offset.setLength(nextLen);
    camera.position.copy(target).add(offset);
    controls.update();
  }, [zoomAction, zoomActionNonce, reloadKey]);

  // ── Per-frame animation ──
  // Uses refs for any prop-driven quantity so the callback identity
  // stays stable and ModelViewer3D doesn't re-register every tick.
  const hoveredRefLocal = hoveredPartIdRef;
  const frameCb = useCallback((state: { clock: THREE.Clock; camera: THREE.Camera }, delta: number) => {
    const cache = cacheRef.current;
    if (!cache) return;
    for (const c of cache.rotating) {
      c.rotation.x += delta * 0.15;
    }
    if (cache.assembly.length) {
      const blend = Math.min(1, delta * 4);
      const eA = explodeAmountRef.current;
      for (const a of cache.assembly) {
        const targetX = a.basePos.x + a.outDir.x * a.distFromCenter * eA * 1.2;
        const targetY = a.basePos.y + a.outDir.y * a.distFromCenter * eA * 1.2;
        const targetZ = a.basePos.z + a.outDir.z * a.distFromCenter * eA * 1.2;
        a.obj.position.x += (targetX - a.obj.position.x) * blend;
        a.obj.position.y += (targetY - a.obj.position.y) * blend;
        a.obj.position.z += (targetZ - a.obj.position.z) * blend;
      }
    }
    if (cache.deployables.length) {
      const blend = Math.min(1, delta * 3);
      const d = Math.max(0, Math.min(1, deploymentRef.current));
      for (const dep of cache.deployables) {
        const tx = dep.stowedScale.x + (dep.baseScale.x - dep.stowedScale.x) * d;
        const ty = dep.stowedScale.y + (dep.baseScale.y - dep.stowedScale.y) * d;
        const tz = dep.stowedScale.z + (dep.baseScale.z - dep.stowedScale.z) * d;
        dep.obj.scale.x += (tx - dep.obj.scale.x) * blend;
        dep.obj.scale.y += (ty - dep.obj.scale.y) * blend;
        dep.obj.scale.z += (tz - dep.obj.scale.z) * blend;
      }
    }
    const t = state.clock.elapsedTime;
    const hovered = hoveredRefLocal.current;
    if (showFxRef.current) {
      for (const p of cache.pulsing) {
        if (p.mesh.name === hovered) continue;
        const mat = p.mesh.material as THREE.MeshStandardMaterial;
        if (!mat?.emissive) continue;
        mat.emissiveIntensity = p.base + p.amp * Math.sin(t * p.rate + p.phase);
      }
      for (const g of cache.glows) {
        const phase = (g as any)._pulsePhase;
        const rate  = (g as any)._pulseRate;
        if (phase === undefined || !g.name.endsWith('_beacon')) continue;
        const mat = (g as THREE.Mesh).material as THREE.MeshStandardMaterial;
        if (!mat?.emissive) continue;
        const s = Math.sin(t * rate + phase);
        mat.emissiveIntensity = s > 0.3 ? 3.0 : 0.4;
      }
    }
    const plume = cache.plume;
    if (plume) {
      const attr = plume.points.geometry.getAttribute('position') as THREE.BufferAttribute;
      const pos = attr.array as Float32Array;
      const recycleDist = plume.exitRadius * 12;
      for (let i = 0; i < plume.count; i++) {
        const idx = i * 3;
        pos[idx] -= plume.velocities[i] * delta;
        if (plume.origin.x - pos[idx] > recycleDist) {
          pos[idx]     = plume.origin.x + (Math.random() - 0.4) * plume.exitRadius;
          pos[idx + 1] = plume.origin.y + (Math.random() - 0.5) * plume.exitRadius * 0.6;
          pos[idx + 2] = plume.origin.z + (Math.random() - 0.5) * plume.exitRadius * 0.6;
        }
      }
      attr.needsUpdate = true;
    }
  }, [hoveredRefLocal]);

  // Memo the source so flipping reloadKey forces a fresh fetch.
  const source = useMemo(
    () => ({
      type: 'gltf' as const,
      url: `/api/ship.gltf${reloadKey ? `?v=${reloadKey}` : ''}`,
    }),
    [reloadKey],
  );

  // Stars + point-lights + hover label are injected as extra children
  // inside ModelViewer3D's Canvas. They need the r3f context for
  // useFrame / <primitive> / <Html>.
  const extraCanvasChildren = (
    <>
      <pointLight ref={reactorLightRef} color={0xff5522} intensity={3.2} distance={800} decay={1.8} />
      <pointLight ref={nozzleLightRef}  color={0x3388ff} intensity={2.8} distance={600} decay={1.8} />
      <Stars count={3000} radius={8000} />
      {showLabels && hoveredPartId && (
        <HoverLabelBridge partId={hoveredPartId} sceneFinder={() => cacheRef.current?.scene ?? null} />
      )}
    </>
  );

  return (
    <ModelViewer3D
      source={source}
      disableMaterialOverride
      disableBoundsFit
      enhanceScene={enhanceScene}
      extraCanvasChildren={extraCanvasChildren}
      useFrameCallback={frameCb}
      onPartClick={onPartClick}
      onPartHover={setHoveredPart}
      hideToolbar
      hideMeshInfo
      showGizmo
      showStats={showStats}
      showGrid={false}
      background="dark"
      height="100%"
      camera={{ position: [600, 280, 1100], fov: 50, near: 1, far: 40000 }}
      disableKeyboard
      allowFullscreen={false}
    />
  );
}

// ── Hover-only label ─────────────────────────────────────────────────
// Finds the named mesh on demand (scene ref comes from enhanceScene
// cache). Re-computes anchor every render — cheap since it only runs
// when hoveredPartId changes.
function HoverLabelBridge({ partId, sceneFinder }: { partId: string | null; sceneFinder: () => THREE.Object3D | null }) {
  const scene = sceneFinder();
  const anchor = useMemo(() => {
    if (!partId || !scene) return null;
    const o = scene.getObjectByName(partId);
    if (!o) return null;
    const box = new THREE.Box3().setFromObject(o);
    const c = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3()).length();
    return new THREE.Vector3(c.x, box.max.y + size * 0.05 + 8, c.z);
  }, [scene, partId]);
  if (!partId || !anchor) return null;
  const info = partInfoFor(partId);
  return (
    <Html position={[anchor.x, anchor.y, anchor.z]} center occlude={false} zIndexRange={[100, 0]}>
      <div className="pointer-events-none px-2 py-1 rounded bg-ui-bg-0/95 border border-ui-accent backdrop-blur-sm shadow-xl whitespace-nowrap">
        <div className={`text-[11px] font-bold ${info.color}`} style={{ textShadow: '0 0 6px rgba(0,0,0,0.9)' }}>
          {info.name}
        </div>
        <div className="text-[9px] text-ui-text font-mono" style={{ textShadow: '0 0 4px rgba(0,0,0,0.9)' }}>
          {info.subtitle}
        </div>
        <div className="text-[8px] text-ui-text-dim font-mono">{partId}</div>
      </div>
    </Html>
  );
}

// Starfield with per-vertex colour + brightness scatter — a handful of
// red giants, blue-white B/A stars, and a majority of warm-white mains
// make the sky feel like a real night sky rather than a uniform grid.
function Stars({ count, radius }: { count: number; radius: number }) {
  const geom = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);
    const colors    = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const u = Math.random(), v = Math.random();
      const th = 2 * Math.PI * u, ph = Math.acos(2 * v - 1);
      const r = radius + Math.random() * 4000;
      positions[i * 3]     = r * Math.sin(ph) * Math.cos(th);
      positions[i * 3 + 1] = r * Math.sin(ph) * Math.sin(th);
      positions[i * 3 + 2] = r * Math.cos(ph);
      const roll = Math.random();
      let cr = 1, cg = 1, cb = 1;
      if (roll < 0.05)      { cr = 1.00; cg = 0.72; cb = 0.55; }
      else if (roll < 0.15) { cr = 0.78; cg = 0.86; cb = 1.00; }
      else                  { cr = 0.95 + Math.random() * 0.05;
                              cg = 0.92 + Math.random() * 0.05;
                              cb = 0.88 + Math.random() * 0.05; }
      const lum = 0.35 + Math.random() * Math.random() * 0.85;
      colors[i * 3]     = cr * lum;
      colors[i * 3 + 1] = cg * lum;
      colors[i * 3 + 2] = cb * lum;
    }
    g.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    g.setAttribute('color',    new THREE.BufferAttribute(colors, 3));
    return g;
  }, [count, radius]);
  const mat = useMemo(() => new THREE.PointsMaterial({
    vertexColors: true, size: 1.8, sizeAttenuation: false, transparent: true, opacity: 0.95,
  }), []);
  useEffect(() => () => { geom.dispose(); mat.dispose(); }, [geom, mat]);
  return <points geometry={geom} material={mat} />;
}
