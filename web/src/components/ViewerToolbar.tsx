/**
 * Floating toolbar for the 3D viewport: exploded view, part isolation,
 * wireframe, reset, and a HUD badge for the hovered part.
 *
 * Overlays the Canvas in the top-right. All controls mutate lifted state
 * in App.tsx so Ship3D picks them up as props. No viewer state lives
 * inside this component, EXCEPT the collapsed/expanded flag — which is
 * purely visual and doesn't need to leak to the rest of the app.
 */

import { useState } from 'react';

export type CameraPreset = 'fore' | 'aft' | 'port' | 'starboard' | 'top' | 'threequarter';
export type ZoomAction = 'in' | 'out' | 'fit';

interface ViewerToolbarProps {
  explode: number;
  setExplode: (v: number) => void;
  isolate: string | null;
  setIsolate: (v: string | null) => void;
  wireframe: boolean;
  setWireframe: (v: boolean) => void;
  showLabels: boolean;
  setShowLabels: (v: boolean) => void;
  cleanView: boolean;
  setCleanView: (v: boolean) => void;
  showFx: boolean;
  setShowFx: (v: boolean) => void;
  deployment: number;
  setDeployment: (v: number) => void;
  hoveredPartId: string | null;
  onReset: () => void;
  onPreset: (preset: CameraPreset) => void;
  onZoom: (action: ZoomAction) => void;
}

export function ViewerToolbar({
  explode, setExplode,
  isolate, setIsolate,
  wireframe, setWireframe,
  showLabels, setShowLabels,
  cleanView, setCleanView,
  showFx, setShowFx,
  deployment, setDeployment,
  hoveredPartId,
  onReset,
  onPreset,
  onZoom,
}: ViewerToolbarProps) {
  // Collapsed = only a tiny toggle tab on the right edge. Expanded = the
  // full panel. Defaults collapsed on small viewports so the 3D view
  // gets the full width.
  const [collapsed, setCollapsed] = useState(
    typeof window !== 'undefined' && window.innerWidth < 1200,
  );

  if (collapsed) {
    return (
      <button onClick={() => setCollapsed(false)}
              title="Show viewer controls"
              className="absolute top-3 right-3 z-10 pointer-events-auto px-2 py-1.5 rounded-l-lg border border-ui-accent bg-ui-bg-1/85 backdrop-blur text-[10px] text-ui-accent hover:bg-ui-bg-2 shadow-lg">
        ◀ Controls
      </button>
    );
  }

  return (
    <div className="absolute top-3 right-3 bottom-3 z-10 w-60 space-y-2 pointer-events-auto overflow-y-auto pr-1">
      <div className="bg-ui-bg-1/85 backdrop-blur border border-ui-accent/50 rounded-lg p-2.5 shadow-2xl">
        <div className="text-[10px] uppercase tracking-widest text-ui-accent font-bold mb-2 flex justify-between items-center gap-2">
          <span>Viewer Controls</span>
          <div className="flex gap-2">
            <button onClick={onReset}
                    className="text-[9px] text-ui-text-dim hover:text-ui-accent normal-case font-normal">
              ↺ reset
            </button>
            <button onClick={() => setCollapsed(true)}
                    title="Hide controls"
                    className="text-[11px] text-ui-text-dim hover:text-ui-accent normal-case font-normal leading-none">
              ▶
            </button>
          </div>
        </div>

        {/* Exploded-view slider */}
        <label className="block text-[10px] text-ui-text mb-1">
          Explode <span className="text-ui-accent font-mono float-right">{(explode * 100).toFixed(0)}%</span>
        </label>
        <input type="range" min={0} max={1} step={0.02} value={explode}
               onChange={e => setExplode(+e.target.value)}
               className="w-full accent-cyan-500 mb-2" />

        {/* Deployment slider — fold/unfurl radiators, comms mast, HGA */}
        <label className="block text-[10px] text-ui-text mb-1">
          Deployment
          <span className="text-ui-accent font-mono float-right">
            {deployment <= 0.02 ? 'stowed' : deployment >= 0.98 ? 'deployed' : `${(deployment * 100).toFixed(0)}%`}
          </span>
        </label>
        <input type="range" min={0} max={1} step={0.02} value={deployment}
               onChange={e => setDeployment(+e.target.value)}
               className="w-full accent-amber-500 mb-2"
               title="Origami: fold radiators + comms mast for launch, unfurl for cruise" />

        {/* Toggle grid */}
        <div className="grid grid-cols-2 gap-1.5">
          <button onClick={() => setIsolate(isolate ? null : hoveredPartId)}
                  disabled={!isolate && !hoveredPartId}
                  className={`px-2 py-1 text-[10px] rounded border transition-colors ${
                    isolate
                      ? 'bg-sev-warn/60 border-sev-warn text-sev-warn'
                      : hoveredPartId
                      ? 'bg-ui-bg-2 border-ui-border-strong text-ui-text hover:bg-ui-bg-3'
                      : 'bg-ui-bg-1 border-ui-border-soft text-ui-text-faint cursor-not-allowed'
                  }`}>
            {isolate ? '★ Isolated' : 'Isolate hover'}
          </button>
          <button onClick={() => setWireframe(!wireframe)}
                  className={`px-2 py-1 text-[10px] rounded border transition-colors ${
                    wireframe
                      ? 'bg-ui-accent/60 border-ui-accent text-ui-accent'
                      : 'bg-ui-bg-2 border-ui-border-strong text-ui-text hover:bg-ui-bg-3'
                  }`}>
            {wireframe ? '◇ Wireframe' : 'Wireframe'}
          </button>
          <button onClick={() => setShowLabels(!showLabels)}
                  className={`px-2 py-1 text-[10px] rounded border transition-colors ${
                    showLabels
                      ? 'bg-ui-accent/60 border-ui-accent text-ui-accent'
                      : 'bg-ui-bg-2 border-ui-border-strong text-ui-text hover:bg-ui-bg-3'
                  }`}>
            {showLabels ? '◉ Hover tips' : '○ Hover tips'}
          </button>
          <button onClick={() => setCleanView(!cleanView)}
                  title="Hide minor detail — reads as clean primitives"
                  className={`px-2 py-1 text-[10px] rounded border transition-colors ${
                    cleanView
                      ? 'bg-sev-ok/60 border-sev-ok text-sev-ok'
                      : 'bg-ui-bg-2 border-ui-border-strong text-ui-text hover:bg-ui-bg-3'
                  }`}>
            {cleanView ? '✦ Clean view' : 'Clean view'}
          </button>
          <button onClick={() => setShowFx(!showFx)}
                  title="Additive glows + plasma plume + strobe sprites"
                  className={`col-span-2 px-2 py-1 text-[10px] rounded border transition-colors ${
                    showFx
                      ? 'bg-ui-accent/60 border-ui-accent text-ui-accent'
                      : 'bg-ui-bg-2 border-ui-border-strong text-ui-text hover:bg-ui-bg-3'
                  }`}>
            {showFx ? '⟢ Effects on' : '○ Effects off (solid primitives)'}
          </button>
        </div>

        {/* Isolated-part badge — click to clear */}
        {isolate && (
          <button onClick={() => setIsolate(null)}
                  className="mt-2 w-full text-left px-2 py-1 rounded bg-sev-warn/40 border border-sev-warn text-[10px] text-sev-warn hover:bg-sev-warn/60">
            <span className="opacity-60">showing only</span>{' '}
            <span className="font-mono">{isolate}</span>{' '}
            <span className="opacity-60">(× clear)</span>
          </button>
        )}

        {/* Hover HUD — part id of whatever the cursor is over */}
        {hoveredPartId && (
          <div className="mt-2 px-2 py-1 rounded bg-ui-bg-2/70 border border-ui-border text-[10px] font-mono text-ui-accent truncate">
            ↳ {hoveredPartId}
          </div>
        )}
      </div>

      {/* Zoom — explicit in/out/fit buttons in addition to the mouse wheel. */}
      <div className="bg-ui-bg-1/85 backdrop-blur border border-ui-accent/50 rounded-lg p-2 shadow-2xl">
        <div className="text-[10px] uppercase tracking-widest text-ui-accent font-bold mb-1.5">Zoom</div>
        <div className="grid grid-cols-3 gap-1">
          <button onClick={() => onZoom('out')}
                  title="Pull camera away (Shift+Scroll also works)"
                  className="px-2 py-1.5 text-sm rounded border border-ui-border bg-ui-bg-2 text-ui-text hover:bg-ui-bg-3 hover:border-ui-accent hover:text-ui-accent font-bold">
            −
          </button>
          <button onClick={() => onZoom('fit')}
                  title="Re-frame camera to show the whole ship"
                  className="px-2 py-1.5 text-[9px] uppercase tracking-wide rounded border border-ui-accent bg-ui-accent/40 text-ui-accent hover:bg-ui-accent/70">
            Fit
          </button>
          <button onClick={() => onZoom('in')}
                  title="Push camera closer"
                  className="px-2 py-1.5 text-sm rounded border border-ui-border bg-ui-bg-2 text-ui-text hover:bg-ui-bg-3 hover:border-ui-accent hover:text-ui-accent font-bold">
            +
          </button>
        </div>
      </div>

      {/* Camera presets — 6 orthographic-style angles + a default 3/4 view */}
      <div className="bg-ui-bg-1/85 backdrop-blur border border-ui-accent/50 rounded-lg p-2 shadow-2xl">
        <div className="text-[10px] uppercase tracking-widest text-ui-accent font-bold mb-1.5">Camera</div>
        <div className="grid grid-cols-3 gap-1">
          {(['fore', 'aft', 'top', 'port', 'starboard', 'threequarter'] as const).map(p => (
            <button key={p}
                    onClick={() => onPreset(p)}
                    className="px-1 py-1 text-[9px] uppercase tracking-wide rounded border border-ui-border bg-ui-bg-2 text-ui-text hover:bg-ui-bg-3 hover:border-ui-accent hover:text-ui-accent">
              {p === 'threequarter' ? '3⁄4' : p}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
