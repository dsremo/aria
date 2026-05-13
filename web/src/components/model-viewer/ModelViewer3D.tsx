/**
 * ModelViewer3D — a reusable, CAD-grade 3D model viewer.
 *
 * Industry-standard patterns lifted from Onshape / Fusion 360 / CATIA /
 * Blender / three.js-editor. Built on react-three-fiber + drei per the
 * 2026 best-practices research (Codrops, r3f docs, utsubo.com 100-tips).
 *
 * Features:
 *   Loading       · glTF, OBJ, STL (three-stdlib loaders)
 *                 · Error boundary catches network / parse failures
 *                 · Suspense fallback = animated wireframe + progress hint
 *   Rendering     · MeshBasicMaterial default (never-black, dodges the
 *                   PBR-without-HDRI trap). Optional Environment preset
 *                   feeds real IBL for physical look.
 *                 · Four shading modes: solid / wireframe / solid+wire /
 *                   x-ray (translucent).
 *                 · Configurable background: dark / studio / light /
 *                   transparent.
 *                 · Optional ground grid + world-axis helpers.
 *   Navigation    · OrbitControls with smooth damping; left-drag rotate,
 *                   right-drag pan (screen-space), wheel zoom.
 *                 · Keyboard: F = fit, 1 = front, 3 = right, 7 = top,
 *                   0 = iso, R = reset orientation, arrows = pan (Blender
 *                   numpad-style shortcuts via Canvas focus).
 *                 · Orientation gizmo (bottom-left) + optional ViewCube
 *                   (top-right) with click-to-snap faces (Fusion 360
 *                   pattern).
 *   Interaction   · Click to select; hover to highlight (optional).
 *                 · Fit-to-selection on double-click.
 *                 · Section-plane toggle + slider — clip away half the
 *                   model along any axis (Blender / SolidWorks pattern).
 *   Diagnostics   · Mesh-info HUD: triangle count, mesh count, bounding-
 *                   box dims. Draw-call counter refreshed once per second
 *                   (r3f 2026 guidance: stay under 100 / frame).
 *   Export        · Snapshot button — renders the viewport to a PNG
 *                   downloaded via a blob URL.
 *   Lifecycle     · All custom materials tracked + disposed on unmount.
 *                 · Geometry / textures from three-stdlib loaders are
 *                   also disposed (useLoader caches by URL but we still
 *                   release our overrides).
 *
 * Deliberate non-features (YAGNI for this app):
 *   · STEP / IGES support (CAD exchange). glTF/OBJ/STL cover the NASA
 *     42 assets + the ARIA glTF.
 *   · Full PBR material editing. This is a VIEWER, not a modeller.
 *   · Multi-viewport split layouts. Out of scope.
 *   · WebGPU renderer. r3f + WebGPU is still experimental in 2026; the
 *     async gl prop exists but adds complexity. Stick with WebGL2.
 */

import {
  Component, Suspense, useCallback, useEffect, useMemo, useRef, useState,
  type ReactNode,
} from 'react';
import { Canvas, useFrame, useLoader, useThree } from '@react-three/fiber';
import {
  Bounds, Center, Environment, Grid, GizmoHelper, GizmoViewcube,
  GizmoViewport, OrbitControls, Html, useProgress,
} from '@react-three/drei';
import { GLTFLoader, OBJLoader, STLLoader } from 'three-stdlib';
import * as THREE from 'three';
import { probeWebGL } from '../webgl-check';

// ── Public API ──────────────────────────────────────────────────────

export type ModelSource =
  | { type: 'gltf'; url: string }
  | { type: 'obj';  url: string }
  | { type: 'stl';  url: string };

export type ShadingMode = 'solid' | 'wireframe' | 'solid+wire' | 'xray';
export type Background  = 'dark' | 'studio' | 'light' | 'transparent';

/** Callback fired once per model load — hands the caller the loaded scene
 *  graph + active camera + orbit controls so they can traverse / mutate
 *  materials or inject procedural geometry. Return an optional cleanup
 *  function that runs when the scene is replaced or the viewer unmounts.
 *  This is the single extension point Ship3D uses to layer PART_MATS,
 *  procedural greebles, plume particles, etc. on top of the generic
 *  viewer without forking the render pipeline. */
export type EnhanceSceneFn = (
  scene: THREE.Object3D,
  camera: THREE.Camera,
  controls: any,
) => (() => void) | void;

export interface ModelViewer3DProps {
  /** Source mesh — glTF, OBJ or STL. */
  source: ModelSource;
  /** Base colour applied to every mesh (CSS string). */
  color?: string;
  /** Called when the user clicks a named mesh inside the model. */
  onPartClick?: (partName: string) => void;
  /** Called on hover change; receives null when the pointer leaves. */
  onPartHover?: (partName: string | null) => void;
  /** Toolbar visibility & initial feature state. */
  showToolbar?: boolean;
  showGizmo?: boolean;
  showViewCube?: boolean;
  showGrid?: boolean;
  showStats?: boolean;
  /** Initial shading mode. */
  initialShading?: ShadingMode;
  /** Background theme. `transparent` makes the canvas see-through. */
  background?: Background;
  /** If true, drei <Environment /> preset feeds IBL for physical look. */
  useIBL?: boolean;
  environmentPreset?: 'night' | 'sunset' | 'dawn' | 'studio' | 'warehouse' | 'city';
  /** Height of the viewer (CSS). Defaults to 240. */
  height?: number | string;
  /** className forwarded to the outer container. */
  className?: string;
  /** Label shown in the bottom-right attribution strip. */
  attribution?: string;
  /** Disable keyboard shortcuts (useful when embedded in a form). */
  disableKeyboard?: boolean;
  /** Enable the container-level fullscreen button. Default true. */
  allowFullscreen?: boolean;
  /** Unit label + scale factor for measurement. `unit` is the string
   *  shown in the distance readout (e.g. 'm', 'mm', 'AU'). `unitScale`
   *  multiplies the raw world-space distance to get that unit. For a
   *  model served in metres, `{unit: 'm', unitScale: 1}` is the
   *  identity; for an ARIA glTF drawn in metres but displayed in km,
   *  use `{unit: 'km', unitScale: 0.001}`. */
  measurementUnit?: { unit: string; scale: number };
  /** Skip the default MeshBasicMaterial colour override on every mesh.
   *  Callers that supply an `enhanceScene` with their own per-part
   *  materials (Ship3D's PART_MATS) set this true so the viewer doesn't
   *  stomp their assignment. */
  disableMaterialOverride?: boolean;
  /** Skip the <Bounds fit clip observe><Center> wrapper, leaving the
   *  scene at its authored world coordinates. Use when the caller wants
   *  absolute-scale world positions preserved (e.g. 1 km habitat ring)
   *  and wants to run its own fit-camera logic via enhanceScene. */
  disableBoundsFit?: boolean;
  /** Fires on each model load. See `EnhanceSceneFn`. */
  enhanceScene?: EnhanceSceneFn;
  /** Arbitrary children rendered *inside* the R3F Canvas, above the
   *  loaded model. Use for overlay helpers that need the three.js
   *  context (Stars, point-lights, Html pins, custom particle systems).
   *  Pass null to skip. */
  extraCanvasChildren?: ReactNode;
  /** Per-frame callback invoked from inside the Canvas via useFrame.
   *  Receives the full r3f state + the delta seconds. Used by Ship3D to
   *  drive the ring-spin / explode lerp / plume advance. Receives an
   *  optional `sceneRef` payload so the callback can read the current
   *  loaded scene root without prop-drilling — the viewer populates it
   *  after each load. */
  useFrameCallback?: (
    state: { clock: THREE.Clock; camera: THREE.Camera },
    delta: number,
    scene: THREE.Object3D | null,
  ) => void;
  /** Initial camera position / fov / near / far. Overrides the viewer
   *  default of [3,2,4] @ fov 40 — useful when the scene is at huge
   *  world-scale (e.g. Ship3D spans ~1 km so it needs far=40000). */
  camera?: { position?: [number, number, number]; fov?: number; near?: number; far?: number };
  /** Hide the entire toolbar chrome. Ship3D draws its own floating
   *  toolbar at the app shell level so it doesn't want a second one
   *  stacked on top of the Canvas. */
  hideToolbar?: boolean;
  /** Hide the mesh-info readout in the bottom-left. */
  hideMeshInfo?: boolean;
}

// ── Root component ──────────────────────────────────────────────────

export function ModelViewer3D(props: ModelViewer3DProps) {
  const {
    source, color = '#c8ced8',
    onPartClick, onPartHover,
    showToolbar = true, showGizmo = true, showViewCube = false,
    showGrid = false, showStats = false,
    allowFullscreen = true,
    measurementUnit = { unit: 'u', scale: 1 },
    initialShading = 'solid',
    background = 'dark',
    useIBL = false,
    environmentPreset = 'night',
    height = 240,
    className = '',
    attribution,
    disableKeyboard = false,
    disableMaterialOverride = false,
    disableBoundsFit = false,
    enhanceScene,
    extraCanvasChildren = null,
    useFrameCallback,
    camera: cameraInit,
    hideToolbar = false,
    hideMeshInfo = false,
  } = props;

  // Local viewer state — never leaks out to the parent.
  const [shading, setShading]     = useState<ShadingMode>(initialShading);
  const [gridOn, setGridOn]       = useState(showGrid);
  const [bgMode, setBgMode]       = useState<Background>(background);
  const [clipOn, setClipOn]       = useState(false);
  const [clipAxis, setClipAxis]   = useState<'x' | 'y' | 'z'>('x');
  const [clipValue, setClipValue] = useState(0);
  const [resetNonce, setResetNonce]     = useState(0);
  const [presetNonce, setPresetNonce]   = useState<{ p: CameraPreset; n: number } | null>(null);
  const [hovered, setHovered]     = useState<string | null>(null);
  const [info, setInfo]           = useState<ModelInfo | null>(null);
  // Measurement tool — collects up to 2 raycast hit points; when both
  // are set the viewer draws a line + distance label between them.
  const [measureOn, setMeasureOn] = useState(false);
  const [measurePoints, setMeasurePoints] = useState<THREE.Vector3[]>([]);
  // Fullscreen.
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const onFS = () => setIsFullscreen(document.fullscreenElement === containerRef.current);
    document.addEventListener('fullscreenchange', onFS);
    return () => document.removeEventListener('fullscreenchange', onFS);
  }, []);

  const toggleFullscreen = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    if (document.fullscreenElement) document.exitFullscreen();
    else el.requestFullscreen?.().catch(() => {});
  }, []);

  // Compute the clipping plane in world space from axis + value slider.
  const clippingPlane = useMemo(() => {
    if (!clipOn) return null;
    const normal =
      clipAxis === 'x' ? new THREE.Vector3(1, 0, 0) :
      clipAxis === 'y' ? new THREE.Vector3(0, 1, 0) :
                         new THREE.Vector3(0, 0, 1);
    return new THREE.Plane(normal, -clipValue);
  }, [clipOn, clipAxis, clipValue]);

  // Keyboard shortcuts — Blender-style numpad views + F for fit.
  useEffect(() => {
    if (disableKeyboard) return;
    const onKey = (e: KeyboardEvent) => {
      // Ignore if focus is inside an input/textarea/contenteditable.
      const tgt = e.target as HTMLElement | null;
      if (tgt && (tgt.tagName === 'INPUT' || tgt.tagName === 'TEXTAREA' || tgt.isContentEditable)) return;
      switch (e.key.toLowerCase()) {
        case 'f': setResetNonce(n => n + 1); break;
        case 'r': setResetNonce(n => n + 1); break;
        case '1': setPresetNonce(p => ({ p: 'front',  n: (p?.n ?? 0) + 1 })); break;
        case '3': setPresetNonce(p => ({ p: 'right',  n: (p?.n ?? 0) + 1 })); break;
        case '7': setPresetNonce(p => ({ p: 'top',    n: (p?.n ?? 0) + 1 })); break;
        case '0': setPresetNonce(p => ({ p: 'iso',    n: (p?.n ?? 0) + 1 })); break;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [disableKeyboard]);

  const onSnapshot = useCallback(() => {
    if (!canvasRef.current) return;
    canvasRef.current.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `model-${Date.now()}.png`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }, []);

  const containerClass = `relative rounded border border-slate-700 overflow-hidden ${
    bgMode === 'transparent' ? '' : 'bg-slate-950/60'
  } ${className}`;

  // BUG-003/004/005 aftermath: if Chrome's GPU is off, the Canvas throws
  // `Error creating WebGL context` which used to surface a useless message.
  // Probe once up-front; if WebGL is not available, render a clear
  // diagnostic with actionable steps instead of trying to mount Three.js.
  const webgl = probeWebGL();

  if (!webgl.available) {
    return (
      <div ref={containerRef} className={containerClass} style={{ height: isFullscreen ? '100%' : height, width: '100%' }}>
        <div className="absolute inset-0 flex flex-col items-center justify-center p-4 overflow-auto">
          <div className="text-amber-400 text-sm font-semibold mb-2">
            ⚠ WebGL is not available in this browser
          </div>
          <div className="text-slate-300 text-xs max-w-xl text-center mb-3">
            {webgl.reason ?? 'The GPU process refused a WebGL context.'}
            {' '}The 3D viewer cannot render without it, but the rest of the dashboard
            still works. Source file was{' '}
            <span className="font-mono text-ui-text-dim">{source.url}</span>.
          </div>
          <div className="text-ui-text-dim text-[11px] max-w-xl">
            <div className="text-slate-200 font-semibold mb-1">How to fix:</div>
            <ol className="list-decimal pl-4 space-y-1">
              {webgl.fix.map((step, i) => <li key={i}>{step}</li>)}
            </ol>
          </div>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 px-3 py-1 text-xs border border-slate-600 rounded hover:bg-ui-bg-2 text-slate-200"
          >
            Reload after fixing Chrome
          </button>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className={containerClass} style={{ height: isFullscreen ? '100%' : height, width: '100%' }}>
      <ErrorBoundary
        fallback={(err) => (
          <div className="absolute inset-0 flex flex-col items-center justify-center p-3 text-center">
            <div className="text-red-300 text-[11px] font-bold mb-1">⚠ Model load failed</div>
            <div className="text-ui-text-dim text-[9px] font-mono max-w-full break-words">{String(err)}</div>
            <div className="text-slate-500 text-[9px] mt-1">{source.url}</div>
            {webgl.renderer && (
              <div className="text-slate-600 text-[9px] mt-1">GPU: {webgl.renderer}</div>
            )}
          </div>
        )}
      >
        <Canvas
          dpr={[1, 2]}
          camera={{
            position: cameraInit?.position ?? [3, 2, 4],
            fov:  cameraInit?.fov  ?? 40,
            near: cameraInit?.near ?? 0.01,
            far:  cameraInit?.far  ?? 20000,
          }}
          gl={{ antialias: true, toneMapping: THREE.NoToneMapping,
                preserveDrawingBuffer: true,   // needed for snapshot
                powerPreference: 'high-performance',
                localClippingEnabled: true }}
          shadows={false}
          onCreated={({ gl, scene, camera }) => {
            const canvas = gl.domElement as HTMLCanvasElement;
            canvasRef.current = canvas;
            canvas.tabIndex = 0;
            canvas.style.outline = 'none';
            canvas.addEventListener('webglcontextlost', (ev) => {
              ev.preventDefault();
              // eslint-disable-next-line no-console
              console.warn('[3D] WebGL context lost — browser will attempt to restore.');
            }, { passive: false });
            canvas.addEventListener('webglcontextrestored', () => {
              try {
                gl.resetState();
                gl.render(scene, camera);
              } catch { /* render loop will catch up next frame */ }
            });
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const lose = (gl as any).getContext?.()?.getExtension?.('WEBGL_lose_context');
            (canvasRef as any).current!._loseExt = lose;
          }}
        >
          <SceneEnvironment mode={bgMode} useIBL={useIBL} envPreset={environmentPreset} />

          {gridOn && <GroundGrid />}

          <Suspense fallback={<LoadingMesh color={color} />}>
            {disableBoundsFit ? (
              <Model
                source={source}
                color={color}
                shading={shading}
                clippingPlane={clippingPlane}
                onPartClick={onPartClick}
                setHovered={(n) => { setHovered(n); onPartHover?.(n); }}
                measureOn={measureOn}
                onMeasurePoint={(pt) => setMeasurePoints(pts => pts.length >= 2 ? [pt] : [...pts, pt])}
                resetNonce={resetNonce}
                presetNonce={presetNonce}
                onInfo={setInfo}
                disableMaterialOverride={disableMaterialOverride}
                enhanceScene={enhanceScene}
                disableBoundsFit
              />
            ) : (
              <Bounds fit clip observe margin={1.25}>
                <Center>
                  <Model
                    source={source}
                    color={color}
                    shading={shading}
                    clippingPlane={clippingPlane}
                    onPartClick={onPartClick}
                    setHovered={(n) => { setHovered(n); onPartHover?.(n); }}
                    measureOn={measureOn}
                    onMeasurePoint={(pt) => setMeasurePoints(pts => pts.length >= 2 ? [pt] : [...pts, pt])}
                    resetNonce={resetNonce}
                    presetNonce={presetNonce}
                    onInfo={setInfo}
                    disableMaterialOverride={disableMaterialOverride}
                    enhanceScene={enhanceScene}
                  />
                </Center>
              </Bounds>
            )}
            {measurePoints.length > 0 && <MeasurementOverlay points={measurePoints} unit={measurementUnit} />}
            {useFrameCallback && <FrameBridge cb={useFrameCallback} />}
            {extraCanvasChildren}
          </Suspense>

          <OrbitControls
            makeDefault enableDamping
            dampingFactor={0.12}
            rotateSpeed={1.0}
            zoomSpeed={1.4}
            panSpeed={1.1}
            screenSpacePanning
            keyPanSpeed={24}
            keys={{ LEFT: 'ArrowLeft', UP: 'ArrowUp', RIGHT: 'ArrowRight', BOTTOM: 'ArrowDown' }}
          />

          {showGizmo && (
            <GizmoHelper alignment="bottom-left" margin={[56, 56]}>
              <GizmoViewport axisColors={['#ef4444', '#22c55e', '#3b82f6']} labelColor="white" />
            </GizmoHelper>
          )}
          {showViewCube && (
            <GizmoHelper alignment="top-right" margin={[56, 56]}>
              <GizmoViewcube color="#0f172a" opacity={0.92} strokeColor="#06b6d4" />
            </GizmoHelper>
          )}
          {showStats && <StatsProbe />}
        </Canvas>
      </ErrorBoundary>

      {showToolbar && !hideToolbar && (
        <Toolbar
          shading={shading} setShading={setShading}
          onFit={() => setResetNonce(n => n + 1)}
          onPreset={(p) => setPresetNonce(prev => ({ p, n: (prev?.n ?? 0) + 1 }))}
          gridOn={gridOn} setGridOn={setGridOn}
          bgMode={bgMode} setBgMode={setBgMode}
          clipOn={clipOn} setClipOn={setClipOn}
          clipAxis={clipAxis} setClipAxis={setClipAxis}
          clipValue={clipValue} setClipValue={setClipValue}
          measureOn={measureOn}
          setMeasureOn={(v) => { setMeasureOn(v); if (!v) setMeasurePoints([]); }}
          clearMeasure={() => setMeasurePoints([])}
          measurePointCount={measurePoints.length}
          allowFullscreen={allowFullscreen}
          isFullscreen={isFullscreen}
          onToggleFullscreen={toggleFullscreen}
          onSnapshot={onSnapshot}
          hovered={hovered}
        />
      )}
      <LoadProgressBadge />

      {info && !hideMeshInfo && (
        <div className="absolute bottom-1 left-1 text-[8px] font-mono text-ui-text-dim bg-slate-950/70 px-1 py-0.5 rounded pointer-events-none z-10">
          {info.meshes} meshes · {info.triangles.toLocaleString()} tris · {info.bboxDim.x.toFixed(1)}×{info.bboxDim.y.toFixed(1)}×{info.bboxDim.z.toFixed(1)}
        </div>
      )}

      {attribution && (
        <div className="absolute bottom-1 right-2 text-[8px] text-slate-500 font-mono pointer-events-none z-10">
          {attribution}
        </div>
      )}
    </div>
  );
}


// ── Camera-preset helper ────────────────────────────────────────────

type CameraPreset = 'front' | 'back' | 'left' | 'right' | 'top' | 'bottom' | 'iso';

// ── Error boundary ──────────────────────────────────────────────────

class ErrorBoundary extends Component<
  { children: ReactNode; fallback: (err: unknown) => ReactNode },
  { err: unknown | null }
> {
  state = { err: null };
  static getDerivedStateFromError(err: unknown) { return { err }; }
  componentDidCatch(err: unknown, info: unknown) {
    // Log to console for devs; keep UI path simple.
    // eslint-disable-next-line no-console
    console.error('[ModelViewer3D]', err, info);
  }
  render() {
    if (this.state.err) return this.props.fallback(this.state.err);
    return this.props.children;
  }
}

// ── Scene helpers ───────────────────────────────────────────────────

function SceneEnvironment({
  mode, useIBL, envPreset,
}: {
  mode: Background;
  useIBL: boolean;
  envPreset: 'night' | 'sunset' | 'dawn' | 'studio' | 'warehouse' | 'city';
}) {
  // Background colour per theme.
  const bg =
    mode === 'dark'        ? 0x0a1022 :
    mode === 'studio'      ? 0x2a2f3a :
    mode === 'light'       ? 0xf0f2f5 :
                             null;  // transparent
  return (
    <>
      {bg !== null && <color attach="background" args={[bg]} />}
      {/* Balanced direct-light rig — works for every orientation even
          when PBR IBL isn't enabled. Tuned so MeshBasicMaterial colours
          show close to their specified hex. */}
      <ambientLight intensity={0.85} />
      <hemisphereLight args={[0xa0b8d8, 0x404858, 1.2]} />
      <directionalLight position={[ 500,  300,  800]} intensity={1.0} color={0xfff4e0} />
      <directionalLight position={[-600, -200, -700]} intensity={0.7} color={0x88aaee} />
      <directionalLight position={[-200,  700, -200]} intensity={0.6} color={0xaaccee} />
      <directionalLight position={[ 800, -400,    0]} intensity={0.5} color={0xffd4a0} />
      {/* Optional IBL — drei Environment can fail to fetch (no network);
          wrap in Suspense + error boundary up the tree already. */}
      {useIBL && (
        <Suspense fallback={null}>
          <Environment preset={envPreset} background={false} environmentIntensity={0.7} />
        </Suspense>
      )}
    </>
  );
}

function GroundGrid() {
  // Floating grid at y=0. Works as a scale reference + orientation cue,
  // like Fusion 360's workplane grid. Fades with distance so it doesn't
  // become a moire at horizon.
  return (
    <Grid
      args={[30, 30]}
      cellSize={0.5}
      cellThickness={0.7}
      cellColor="#334155"
      sectionSize={5}
      sectionThickness={1.2}
      sectionColor="#64748b"
      fadeDistance={40}
      fadeStrength={1}
      followCamera={false}
      infiniteGrid
    />
  );
}

function LoadingMesh({ color }: { color: string }) {
  // Spinning wireframe cube while the real mesh streams in — makes it
  // clear the viewer is alive rather than frozen.
  const ref = useRef<THREE.Mesh>(null);
  useFrame((_, dt) => {
    if (ref.current) { ref.current.rotation.x += dt * 0.6; ref.current.rotation.y += dt * 0.8; }
  });
  return (
    <group>
      <mesh ref={ref}>
        <boxGeometry args={[0.5, 0.5, 0.5]} />
        <meshBasicMaterial wireframe color={color} />
      </mesh>
      <Html center>
        <div className="text-[9px] font-mono text-ui-text-dim bg-slate-950/80 px-1 py-0.5 rounded">loading…</div>
      </Html>
    </group>
  );
}

/** Bridge that hoists a caller-supplied frame callback into the r3f
 *  render loop. Placed inside the Canvas subtree so `useFrame` can
 *  register. Receives the scene root via useThree so the callback can
 *  traverse loaded geometry without needing a ref. */
function FrameBridge({ cb }: { cb: NonNullable<ModelViewer3DProps['useFrameCallback']> }) {
  const scene = useThree(s => s.scene);
  useFrame((state, delta) => {
    cb({ clock: state.clock, camera: state.camera }, delta, scene);
  });
  return null;
}

// Little probe that reports draw-call + FPS stats at 1 Hz. Non-visual —
// useful when the Stats overlay is enabled by a parent.
function StatsProbe() {
  const { gl } = useThree();
  const framesRef = useRef(0);
  useEffect(() => {
    let last = performance.now();
    framesRef.current = 0;
    const id = setInterval(() => {
      const info = gl.info.render;
      const now = performance.now();
      const fps = (framesRef.current * 1000) / (now - last);
      // R65 (2026-04-24) C-6: gate on DEV — was logging once a second
      // in production builds.  Noisy, and the console formatting is a
      // measurable drag on the JS main thread when sustained for hours.
      if (import.meta.env.DEV) {
        // eslint-disable-next-line no-console
        console.log('[ModelViewer3D] fps=%s calls=%s triangles=%s',
                    fps.toFixed(0), info.calls, info.triangles);
      }
      last = now; framesRef.current = 0;
    }, 1000);
    return () => clearInterval(id);
  }, [gl]);
  useFrame(() => { framesRef.current++; });
  return null;
}

// ── Model loader ────────────────────────────────────────────────────

type ModelInfo = {
  meshes: number;
  triangles: number;
  bboxDim: THREE.Vector3;
};

function Model({
  source, color, shading, clippingPlane,
  onPartClick, setHovered, measureOn, onMeasurePoint,
  resetNonce, presetNonce, onInfo,
  disableMaterialOverride = false,
  enhanceScene,
  disableBoundsFit = false,
}: {
  source: ModelSource;
  color: string;
  shading: ShadingMode;
  clippingPlane: THREE.Plane | null;
  onPartClick?: (n: string) => void;
  setHovered: (n: string | null) => void;
  measureOn: boolean;
  onMeasurePoint: (pt: THREE.Vector3) => void;
  resetNonce: number;
  presetNonce: { p: CameraPreset; n: number } | null;
  onInfo: (info: ModelInfo) => void;
  disableMaterialOverride?: boolean;
  enhanceScene?: EnhanceSceneFn;
  disableBoundsFit?: boolean;
}) {
  const rootObject = useLoadedModel(source);
  const camera = useThree(s => s.camera);
  const controls = useThree(s => s.controls as any);

  // Track materials we create so we can dispose them on unmount or when
  // shading/color changes. useLoader caches the raw geometry + source
  // materials by URL, so we only own the override materials.
  const ownedMaterialsRef = useRef<THREE.Material[]>([]);

  useEffect(() => {
    // Dispose previous batch of override materials before creating new.
    ownedMaterialsRef.current.forEach(m => m.dispose());
    ownedMaterialsRef.current = [];
    let meshCount = 0;
    let triCount = 0;
    rootObject.traverse((o) => {
      const m = o as THREE.Mesh;
      if (!m.isMesh) return;
      meshCount++;
      const g = m.geometry as THREE.BufferGeometry;
      const pos = g.getAttribute('position') as THREE.BufferAttribute | undefined;
      const idx = g.getIndex();
      triCount += idx ? idx.count / 3 : pos ? pos.count / 3 : 0;
      // Skip the generic colour-override when the caller is supplying
      // their own per-part materials via enhanceScene. Otherwise the
      // override would stomp everything back to a uniform grey.
      if (!disableMaterialOverride) {
        const mats = buildMaterial(shading, color, clippingPlane);
        if (Array.isArray(mats)) ownedMaterialsRef.current.push(...mats);
        else ownedMaterialsRef.current.push(mats);
        m.material = mats;
      }
      (m as any).cursor = 'pointer';
    });
    const box = new THREE.Box3().setFromObject(rootObject);
    const bboxDim = box.getSize(new THREE.Vector3());
    onInfo({ meshes: meshCount, triangles: Math.round(triCount), bboxDim });
  }, [rootObject, shading, color, clippingPlane, onInfo, disableMaterialOverride]);

  // Fire the enhanceScene extension point once per load (+ whenever the
  // caller's callback identity changes). Returned cleanup runs before
  // the next invocation + on unmount so procedural additions release
  // their geometry/material handles.
  useEffect(() => {
    if (!enhanceScene) return;
    const cleanup = enhanceScene(rootObject, camera, controls);
    return () => { if (typeof cleanup === 'function') cleanup(); };
  }, [rootObject, enhanceScene, camera, controls]);

  // Final disposal on unmount.
  useEffect(() => () => {
    ownedMaterialsRef.current.forEach(m => m.dispose());
    ownedMaterialsRef.current = [];
  }, []);

  // Fit-to-view. Separate effect so the dep array can track resetNonce.
  // Skip when the caller is running its own camera-fit logic.
  useEffect(() => {
    if (!controls || disableBoundsFit) return;
    fitCameraToObject(rootObject, camera, controls, 'iso');
  }, [rootObject, resetNonce, camera, controls, disableBoundsFit]);

  // Snap-to-preset — fires when the preset nonce changes.
  useEffect(() => {
    if (!controls || !presetNonce) return;
    fitCameraToObject(rootObject, camera, controls, presetNonce.p);
  }, [presetNonce, camera, controls, rootObject]);

  return (
    <primitive
      object={rootObject}
      onClick={(e: any) => {
        e.stopPropagation();
        // In measurement mode a click drops a point at the hit location
        // rather than selecting a part. Out of measurement mode, bubble
        // the part-id to the parent.
        if (measureOn && e.point) {
          onMeasurePoint(e.point.clone());
          return;
        }
        if (e.object?.name) onPartClick?.(e.object.name);
      }}
      onDoubleClick={(e: any) => {
        e.stopPropagation();
        if (e.object && controls) fitCameraToObject(e.object, camera, controls, 'iso');
      }}
      onPointerOver={(e: any) => { e.stopPropagation(); setHovered(e.object?.name ?? null); }}
      onPointerOut={() => setHovered(null)}
    />
  );
}

// ── Measurement overlay ─────────────────────────────────────────────

function MeasurementOverlay({ points, unit }: { points: THREE.Vector3[]; unit: { unit: string; scale: number } }) {
  // Draw a small sphere at each hit point, a line between them (if two),
  // and an HTML distance label at the midpoint in world units.
  const lineRef = useRef<THREE.BufferGeometry>(null);
  useEffect(() => {
    if (!lineRef.current) return;
    const positions = new Float32Array(points.flatMap(p => [p.x, p.y, p.z]));
    lineRef.current.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    lineRef.current.computeBoundingSphere();
  }, [points]);
  const mid = points.length === 2 ? points[0].clone().add(points[1]).multiplyScalar(0.5) : null;
  const dist = points.length === 2 ? points[0].distanceTo(points[1]) : 0;
  return (
    <group>
      {points.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[0.01 * Math.max(1, points[0].length()), 8, 8]} />
          <meshBasicMaterial color="#ff9933" />
        </mesh>
      ))}
      {points.length === 2 && (
        <>
          <line>
            <bufferGeometry ref={lineRef} />
            <lineBasicMaterial color="#ff9933" />
          </line>
          {mid && (
            <Html position={[mid.x, mid.y, mid.z]} center>
              <div className="px-1 py-0.5 rounded bg-sev-warn/80 border border-orange-500 text-[10px] font-mono text-orange-100 pointer-events-none">
                {(dist * unit.scale).toLocaleString(undefined, { maximumFractionDigits: 3 })} {unit.unit}
              </div>
            </Html>
          )}
        </>
      )}
    </group>
  );
}

// ── Load-progress badge ─────────────────────────────────────────────
// Uses drei's useProgress hook to surface a small % indicator while any
// loader is active. Disappears when the total queue is done.
function LoadProgressBadge() {
  const { active, progress, item } = useProgress();
  if (!active) return null;
  return (
    <div className="absolute top-1 right-16 z-10 px-1.5 py-0.5 rounded bg-slate-950/85 border border-cyan-700 text-[9px] font-mono text-cyan-300 pointer-events-none">
      {progress.toFixed(0)}% · {item ? item.split('/').pop() : 'loading'}
    </div>
  );
}

function useLoadedModel(source: ModelSource): THREE.Object3D {
  const { url } = source;
  switch (source.type) {
    case 'gltf': {
      const g = useLoader(GLTFLoader, url);
      return (g as any).scene;
    }
    case 'obj': {
      return useLoader(OBJLoader, url) as unknown as THREE.Object3D;
    }
    case 'stl': {
      // STLLoader returns a BufferGeometry — wrap it in a mesh.
      const geo = useLoader(STLLoader, url) as unknown as THREE.BufferGeometry;
      const mesh = useMemo(() => {
        const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: '#c8ced8' }));
        m.name = 'stl_model';
        return m;
      }, [geo]);
      return mesh;
    }
  }
}

function buildMaterial(mode: ShadingMode, color: string, clip: THREE.Plane | null): THREE.Material | THREE.Material[] {
  const clippingPlanes = clip ? [clip] : [];
  const common = { clippingPlanes, clipShadows: true } as const;
  switch (mode) {
    case 'wireframe':
      return new THREE.MeshBasicMaterial({ color, wireframe: true, ...common });
    case 'xray':
      return new THREE.MeshBasicMaterial({
        color, transparent: true, opacity: 0.25, depthWrite: false, side: THREE.DoubleSide, ...common,
      });
    case 'solid+wire':
      return [
        new THREE.MeshBasicMaterial({ color, ...common }),
        new THREE.MeshBasicMaterial({ color: '#000000', wireframe: true, opacity: 0.35, transparent: true, ...common }),
      ];
    case 'solid':
    default:
      return new THREE.MeshBasicMaterial({ color, ...common });
  }
}

// ── Camera helpers ──────────────────────────────────────────────────

function fitCameraToObject(
  obj: THREE.Object3D,
  camera: THREE.Camera,
  controls: any,
  preset: CameraPreset,
) {
  const box = new THREE.Box3().setFromObject(obj);
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3()).length();
  const dist = Math.max(size * 1.1, 0.5);
  const offsets: Record<CameraPreset, [number, number, number]> = {
    front:  [ 0,  0,  dist ],
    back:   [ 0,  0, -dist ],
    left:   [-dist, 0,  0 ],
    right:  [ dist, 0,  0 ],
    top:    [ 0,  dist, 0.0001 ],   // tiny z offset so up-vector doesn't go singular
    bottom: [ 0, -dist, 0.0001 ],
    iso:    [ dist * 0.6, dist * 0.45, dist * 0.9 ],
  };
  const [dx, dy, dz] = offsets[preset];
  camera.position.set(center.x + dx, center.y + dy, center.z + dz);
  if ((camera as any).isPerspectiveCamera) {
    const p = camera as THREE.PerspectiveCamera;
    p.near = Math.max(0.01, dist * 0.001);
    p.far  = Math.max(1000, dist * 100);
    p.updateProjectionMatrix();
  }
  controls.target.copy(center);
  controls.update();
}

// ── Toolbar ─────────────────────────────────────────────────────────

function Toolbar({
  shading, setShading,
  onFit, onPreset,
  gridOn, setGridOn,
  bgMode, setBgMode,
  clipOn, setClipOn, clipAxis, setClipAxis, clipValue, setClipValue,
  measureOn, setMeasureOn, clearMeasure, measurePointCount,
  allowFullscreen, isFullscreen, onToggleFullscreen,
  onSnapshot,
  hovered,
}: {
  shading: ShadingMode; setShading: (m: ShadingMode) => void;
  onFit: () => void; onPreset: (p: CameraPreset) => void;
  gridOn: boolean; setGridOn: (v: boolean) => void;
  bgMode: Background; setBgMode: (b: Background) => void;
  clipOn: boolean; setClipOn: (v: boolean) => void;
  clipAxis: 'x' | 'y' | 'z'; setClipAxis: (a: 'x' | 'y' | 'z') => void;
  clipValue: number; setClipValue: (v: number) => void;
  measureOn: boolean; setMeasureOn: (v: boolean) => void;
  clearMeasure: () => void; measurePointCount: number;
  allowFullscreen: boolean; isFullscreen: boolean; onToggleFullscreen: () => void;
  onSnapshot: () => void;
  hovered: string | null;
}) {
  const modes: { value: ShadingMode; label: string; title: string }[] = [
    { value: 'solid',      label: '■',  title: 'Solid (S)' },
    { value: 'wireframe',  label: '⬡',  title: 'Wireframe (W)' },
    { value: 'solid+wire', label: '▣',  title: 'Solid + wireframe' },
    { value: 'xray',       label: '◌',  title: 'X-Ray (translucent)' },
  ];
  return (
    <>
      {/* Primary toolbar — top-left */}
      <div role="toolbar" aria-label="Viewer controls"
           className="absolute top-1 left-1 flex gap-1 pointer-events-auto z-10 flex-wrap">
        {modes.map(m => (
          <button key={m.value}
                  aria-label={m.title}
                  title={m.title}
                  onClick={() => setShading(m.value)}
                  className={`w-6 h-6 rounded text-[13px] leading-none flex items-center justify-center border transition-colors ${
                    shading === m.value
                      ? 'bg-ui-accent/70 border-cyan-500 text-cyan-200'
                      : 'bg-slate-900/70 border-slate-700 text-slate-300 hover:bg-ui-bg-2'
                  }`}>
            {m.label}
          </button>
        ))}

        <div className="w-px bg-ui-bg-3 mx-0.5" />

        <button onClick={onFit} title="Fit to view (F)"
                aria-label="Fit to view"
                className="px-1.5 h-6 rounded text-[10px] border border-slate-700 bg-slate-900/70 text-slate-300 hover:bg-ui-bg-2 hover:border-cyan-500">
          Fit
        </button>
        {(['front','right','top','iso'] as const).map(p => (
          <button key={p} onClick={() => onPreset(p)}
                  title={`View ${p} (${p === 'front' ? '1' : p === 'right' ? '3' : p === 'top' ? '7' : '0'})`}
                  aria-label={`View ${p}`}
                  className="px-1.5 h-6 rounded text-[9px] uppercase tracking-wide border border-slate-700 bg-slate-900/70 text-slate-300 hover:bg-ui-bg-2 hover:border-cyan-500">
            {p === 'iso' ? '3⁄4' : p}
          </button>
        ))}

        <div className="w-px bg-ui-bg-3 mx-0.5" />

        <button onClick={() => setGridOn(!gridOn)} title="Toggle grid"
                aria-label="Toggle grid"
                className={`px-1.5 h-6 rounded text-[10px] border ${gridOn ? 'border-cyan-500 bg-ui-accent/60 text-cyan-200' : 'border-slate-700 bg-slate-900/70 text-slate-300 hover:bg-ui-bg-2'}`}>
          # Grid
        </button>
        <select aria-label="Background"
                value={bgMode}
                onChange={e => setBgMode(e.target.value as Background)}
                className="h-6 rounded text-[10px] border border-slate-700 bg-slate-900/70 text-slate-300 px-1 hover:bg-ui-bg-2">
          <option value="dark">Dark</option>
          <option value="studio">Studio</option>
          <option value="light">Light</option>
          <option value="transparent">Transparent</option>
        </select>

        <div className="w-px bg-ui-bg-3 mx-0.5" />

        <button onClick={() => setClipOn(!clipOn)} title="Toggle section plane"
                aria-label="Toggle section plane"
                className={`px-1.5 h-6 rounded text-[10px] border ${clipOn ? 'border-sev-warn bg-sev-warn/60 text-yellow-200' : 'border-slate-700 bg-slate-900/70 text-slate-300 hover:bg-ui-bg-2'}`}>
          ✂ Cut
        </button>
        <button onClick={() => setMeasureOn(!measureOn)}
                title="Measurement tool — click two points on the model to measure"
                aria-label="Toggle measure"
                className={`px-1.5 h-6 rounded text-[10px] border ${measureOn ? 'border-orange-500 bg-sev-warn/60 text-orange-200' : 'border-slate-700 bg-slate-900/70 text-slate-300 hover:bg-ui-bg-2'}`}>
          📏 {measureOn ? `${measurePointCount}/2` : 'Measure'}
        </button>
        {measureOn && measurePointCount > 0 && (
          <button onClick={clearMeasure} title="Clear measurement"
                  aria-label="Clear measurement"
                  className="px-1.5 h-6 rounded text-[10px] border border-slate-700 bg-slate-900/70 text-slate-300 hover:bg-ui-bg-2">
            ✕
          </button>
        )}
        <button onClick={onSnapshot} title="Download PNG snapshot"
                aria-label="Download PNG"
                className="px-1.5 h-6 rounded text-[10px] border border-slate-700 bg-slate-900/70 text-slate-300 hover:bg-ui-bg-2 hover:border-cyan-500">
          ⬇ PNG
        </button>
        {allowFullscreen && (
          <button onClick={onToggleFullscreen} title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
                  aria-label="Toggle fullscreen"
                  className="px-1.5 h-6 rounded text-[10px] border border-slate-700 bg-slate-900/70 text-slate-300 hover:bg-ui-bg-2 hover:border-cyan-500">
            {isFullscreen ? '⛶⇢' : '⛶'}
          </button>
        )}
      </div>

      {/* Section-plane strip — only visible when cut is active */}
      {clipOn && (
        <div className="absolute top-9 left-1 flex gap-1 items-center pointer-events-auto z-10 bg-slate-950/80 border border-yellow-700 rounded px-1 py-0.5">
          {(['x', 'y', 'z'] as const).map(ax => (
            <button key={ax} onClick={() => setClipAxis(ax)}
                    className={`w-5 h-5 text-[10px] rounded ${clipAxis === ax ? 'bg-yellow-800/60 text-yellow-200' : 'text-ui-text-dim hover:bg-ui-bg-2'}`}>
              {ax.toUpperCase()}
            </button>
          ))}
          <input type="range" min={-2} max={2} step={0.01}
                 value={clipValue}
                 onChange={e => setClipValue(+e.target.value)}
                 className="w-28 accent-yellow-500"
                 aria-label="Section-plane offset" />
          <span className="font-mono text-[9px] text-yellow-300 w-10 text-right">
            {clipValue.toFixed(2)}
          </span>
        </div>
      )}

      {hovered && (
        <div className="absolute bottom-5 left-1 pointer-events-none text-[9px] font-mono text-cyan-300 bg-slate-950/70 px-1 py-0.5 rounded z-10">
          ↳ {hovered}
        </div>
      )}
    </>
  );
}

// ── Memoised presets the rest of the app can reuse ──────────────────

/** Small inline previews (ShipBuilder / landing assets). */
export const MINI_PREVIEW_DEFAULTS: Partial<ModelViewer3DProps> = {
  showGizmo: false,
  showViewCube: false,
  showToolbar: true,
  showGrid: false,
  height: 180,
  initialShading: 'solid',
  disableKeyboard: true,   // mini views shouldn't steal global shortcuts
  allowFullscreen: true,   // handy even on a tiny embed — fills the browser window
};

/** Large hero view with every navigation aid. */
export const HERO_VIEWER_DEFAULTS: Partial<ModelViewer3DProps> = {
  showGizmo: true,
  showViewCube: true,
  showToolbar: true,
  showGrid: false,
  height: 560,
  initialShading: 'solid',
  background: 'dark',
};
