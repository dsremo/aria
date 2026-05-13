/**
 * WebGL availability probe + diagnostic message.
 *
 * react-three-fiber's <Canvas> throws `Error creating WebGL context` at
 * render time when the browser cannot provide a WebGL context.  On a
 * real user's machine that almost always means one of:
 *
 *   1. Chrome hardware acceleration is off (Settings → System → "Use
 *      hardware acceleration when available").
 *   2. chrome://flags has `Override software rendering list` disabled
 *      and the user's GPU driver is blocklisted.
 *   3. Chrome was started with `--disable-gpu` / `--disable-webgl`.
 *   4. The GPU process crashed this session (visible at chrome://gpu).
 *
 * A bare "Error creating WebGL context" message is useless to the user.
 * This helper probes upfront and returns a structured diagnostic that
 * the UI can render with actionable fix instructions.
 */

export interface WebGLDiagnostic {
  available: boolean;
  version: 'webgl2' | 'webgl' | null;
  renderer: string | null;   // the underlying GPU string, if WebGL works
  reason: string | null;     // human-readable explanation when unavailable
  fix: string[];             // suggested operator steps
}

/**
 * Synchronously probe WebGL capability by trying to acquire a context on
 * an off-screen canvas.  Caches the result after first call — the answer
 * doesn't change within a page load.
 */
let _cached: WebGLDiagnostic | null = null;

export function probeWebGL(): WebGLDiagnostic {
  if (_cached !== null) return _cached;

  const diag: WebGLDiagnostic = {
    available: false,
    version: null,
    renderer: null,
    reason: null,
    fix: [],
  };

  if (typeof document === 'undefined') {
    diag.reason = 'No DOM (SSR?).';
    _cached = diag;
    return diag;
  }

  let canvas: HTMLCanvasElement;
  try {
    canvas = document.createElement('canvas');
  } catch (e) {
    diag.reason = `Unable to create <canvas>: ${String(e)}`;
    _cached = diag;
    return diag;
  }

  // Prefer WebGL2, fall back to WebGL1.  Three.js r160+ uses WebGL2 by
  // default so if only WebGL1 works we still report it — the Canvas will
  // downgrade internally.
  const opts: WebGLContextAttributes = {
    antialias: false,
    depth: false,
    stencil: false,
    alpha: false,
    failIfMajorPerformanceCaveat: false,
  };

  const ctx2 = canvas.getContext('webgl2', opts) as WebGL2RenderingContext | null;
  if (ctx2) {
    diag.available = true;
    diag.version = 'webgl2';
    diag.renderer = readRenderer(ctx2);
    _cached = diag;
    return diag;
  }
  const ctx1 =
    (canvas.getContext('webgl', opts) as WebGLRenderingContext | null) ||
    (canvas.getContext('experimental-webgl', opts) as WebGLRenderingContext | null);
  if (ctx1) {
    diag.available = true;
    diag.version = 'webgl';
    diag.renderer = readRenderer(ctx1);
    _cached = diag;
    return diag;
  }

  // Neither WebGL2 nor WebGL1 is available — figure out why.
  diag.reason = classify(canvas);
  diag.fix = [
    'Open chrome://gpu — the "Graphics Feature Status" section lists what is enabled.',
    'In Chrome: Settings → System → turn on "Use hardware acceleration when available", then relaunch Chrome.',
    'Try chrome://flags/#disable-webgl — make sure it is NOT set to Disabled.',
    'If you launched Chrome from a terminal, make sure there is no --disable-gpu / --disable-webgl flag.',
    'On Linux, verify your GPU driver (mesa/nvidia) is installed: `glxinfo -B | head`.',
  ];
  _cached = diag;
  return diag;
}

function readRenderer(gl: WebGLRenderingContext | WebGL2RenderingContext): string | null {
  try {
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    if (ext) {
      // UNMASKED_RENDERER_WEBGL is the real GPU string (behind a debug ext
      // for privacy).  Fall back to standard RENDERER if the ext is gone.
      const unmasked = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) as string | null;
      if (unmasked) return unmasked;
    }
    return (gl.getParameter(gl.RENDERER) as string | null) ?? null;
  } catch {
    return null;
  }
}

function classify(canvas: HTMLCanvasElement): string {
  // Chrome exposes a .getContextAttributes-like path that sometimes has
  // diagnostic info after a failed probe.  When probing fails completely,
  // best we can do is infer from the environment.
  const ua = navigator.userAgent;
  const isHeadless = /HeadlessChrome/i.test(ua);
  if (isHeadless) {
    return 'Headless Chrome: the GPU is disabled in this sandbox by default.';
  }
  // Hint: empty renderer + no context usually = hardware accel off.
  return 'Browser could not create a WebGL context. The GPU process may be disabled, crashed, or blocklisted.';
}
