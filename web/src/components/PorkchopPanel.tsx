/**
 * Porkchop Panel — interplanetary launch-window contour map.
 *
 * Fetches a porkchop grid from /api/porkchop/{origin}/{dest} (Lambert-Izzo solver,
 * heliocentric two-body), then renders a 2D heatmap of departure C3 vs.
 * (departure_day, arrival_day) — the classic NASA "porkchop plot."
 *
 * The dark valleys reveal optimal launch windows; the marker shows the
 * minimum-C3 transfer found in the grid.
 */

import { useEffect, useRef, useState } from 'react';

interface PorkchopResponse {
  origin: string;
  destination: string;
  departure_days: number[];
  arrival_days: number[];
  c3_departure: (number | null)[][];
  v_inf_arrival: (number | null)[][];
  tof_days: (number | null)[][];
  best_c3: number | null;
  best_dep_day: number;
  best_arr_day: number;
  best_tof_days: number;
  valid_count: number;
  total_count: number;
}

const PLANETS = ['mercury', 'venus', 'earth', 'mars', 'jupiter', 'saturn'];

interface CellHit {
  i: number; j: number;
  dep_day: number; arr_day: number;
  c3: number | null; v_inf: number | null; tof: number | null;
  // Canvas coords of the cell centre — rendered tooltip uses the
  // bounding-rect-translated version.
  canvasX: number; canvasY: number;
}

export function PorkchopPanel() {
  const [origin, setOrigin] = useState('earth');
  const [dest, setDest] = useState('mars');
  const [depStart, setDepStart] = useState(0);
  const [depEnd, setDepEnd] = useState(400);
  const [arrStart, setArrStart] = useState(150);
  const [arrEnd, setArrEnd] = useState(700);
  const [grid, setGrid] = useState(30);
  const [data, setData] = useState<PorkchopResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [hover, setHover]   = useState<null | { hit: CellHit; clientX: number; clientY: number }>(null);
  const [pinned, setPinned] = useState<null | CellHit>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const compute = async () => {
    setLoading(true);
    setErr(null);
    try {
      const params = new URLSearchParams({
        dep_start: String(depStart), dep_end: String(depEnd),
        arr_start: String(arrStart), arr_end: String(arrEnd),
        n_dep: String(grid), n_arr: String(grid),
      });
      const r = await fetch(`/api/porkchop/${origin}/${dest}?${params}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      if (j.error) throw new Error(j.error);
      setData(j);
    } catch (e: any) {
      setErr(e.message ?? String(e));
    } finally {
      setLoading(false);
    }
  };

  // R65 (2026-04-24) C-3: missing deps meant dropdown / slider changes
  // on origin/dest/departure-range/arrival-range/grid did nothing until
  // the user clicked Compute.  Auto-compute when any of those change.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { compute(); }, [origin, dest, depStart, depEnd, arrStart, arrEnd, grid]);

  useEffect(() => {
    if (!data || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    ctx.fillStyle = '#020617';
    ctx.fillRect(0, 0, W, H);

    const padL = 56, padB = 32, padT = 16, padR = 16;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;

    const c3 = data.c3_departure;
    const nDep = c3.length;
    const nArr = c3[0]?.length ?? 0;
    if (nDep === 0 || nArr === 0) return;

    // Find finite min/max for color scale.
    let cMin = Infinity, cMax = -Infinity;
    for (const row of c3) for (const v of row) {
      if (v !== null && Number.isFinite(v)) {
        if (v < cMin) cMin = v;
        if (v > cMax) cMax = v;
      }
    }
    if (!Number.isFinite(cMin)) return;
    // Cap at reasonable upper bound (5× best C3) for visible contrast.
    const cCap = Math.min(cMax, cMin * 5 + 5);

    // Color ramp: low C3 = deep blue, high = red.
    const color = (v: number): string => {
      const t = Math.max(0, Math.min(1, (v - cMin) / Math.max(1e-6, cCap - cMin)));
      // Blue (low) → cyan → green → yellow → red (high).
      const r = Math.round(t < 0.5 ? 30 + t * 200 : 230 + (t - 0.5) * 50);
      const g = Math.round(t < 0.5 ? 100 + t * 300 : 250 - (t - 0.5) * 400);
      const b = Math.round(t < 0.5 ? 220 - t * 300 : 70 - (t - 0.5) * 140);
      return `rgb(${r},${Math.max(0, Math.min(255, g))},${Math.max(0, b)})`;
    };

    const cellW = plotW / nDep;
    const cellH = plotH / nArr;

    // Heatmap.
    for (let i = 0; i < nDep; i++) {
      for (let j = 0; j < nArr; j++) {
        const v = c3[i][j];
        if (v === null) {
          ctx.fillStyle = '#1e293b';
        } else {
          ctx.fillStyle = color(Math.min(v, cCap));
        }
        ctx.fillRect(
          padL + i * cellW,
          padT + (nArr - 1 - j) * cellH,
          Math.ceil(cellW),
          Math.ceil(cellH),
        );
      }
    }

    // Best-C3 marker.
    if (data.best_c3 !== null) {
      const dep0 = data.departure_days[0];
      const dep1 = data.departure_days[data.departure_days.length - 1];
      const arr0 = data.arrival_days[0];
      const arr1 = data.arrival_days[data.arrival_days.length - 1];
      // R65-R5 (2026-04-24): guard against single-sample ranges where
      // dep0 === dep1 (user set window to 1 day) — division would produce
      // Infinity and render the marker off-canvas.
      const depSpan = dep1 - dep0;
      const arrSpan = arr1 - arr0;
      if (depSpan <= 0 || arrSpan <= 0) return;
      const x = padL + ((data.best_dep_day - dep0) / depSpan) * plotW;
      const y = padT + (1 - (data.best_arr_day - arr0) / arrSpan) * plotH;
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x, y, 7, 0, Math.PI * 2);
      ctx.moveTo(x - 12, y);
      ctx.lineTo(x + 12, y);
      ctx.moveTo(x, y - 12);
      ctx.lineTo(x, y + 12);
      ctx.stroke();
    }

    // Axes.
    ctx.strokeStyle = '#475569';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, padT); ctx.lineTo(padL, padT + plotH);
    ctx.lineTo(padL + plotW, padT + plotH);
    ctx.stroke();

    ctx.fillStyle = '#cbd5e1';
    ctx.font = '11px monospace';
    ctx.fillText(`Departure (days from epoch)`, padL + plotW / 2 - 80, H - 8);
    ctx.save();
    ctx.translate(12, padT + plotH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText(`Arrival (days)`, -36, 0);
    ctx.restore();

    // Tick labels.
    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px monospace';
    for (let k = 0; k <= 4; k++) {
      const tDep = depStart + (depEnd - depStart) * k / 4;
      ctx.fillText(`${tDep.toFixed(0)}`, padL + (plotW * k) / 4 - 10, padT + plotH + 14);
      const tArr = arrStart + (arrEnd - arrStart) * k / 4;
      ctx.fillText(`${tArr.toFixed(0)}`, 6, padT + plotH - (plotH * k) / 4 + 4);
    }

    // Color bar.
    const barX = padL + plotW + 6;
    const barW = 8;
    if (barX + barW < W - 4) {
      for (let yy = 0; yy < plotH; yy++) {
        const t = 1 - yy / plotH;
        ctx.fillStyle = color(cMin + t * (cCap - cMin));
        ctx.fillRect(barX, padT + yy, barW, 1);
      }
      ctx.fillStyle = '#cbd5e1';
      ctx.font = '9px monospace';
      ctx.fillText(`${cMin.toFixed(0)}`, barX - 4, padT + plotH + 10);
      ctx.fillText(`${cCap.toFixed(0)}`, barX - 4, padT - 2);
    }
  }, [data, depStart, depEnd, arrStart, arrEnd]);

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Porkchop Plot — Launch Window Optimizer</h2>
        <p className="text-xs text-ui-text-dim">
          Heliocentric Lambert-Izzo over (departure, arrival) grid. Dark = low C3 = good launch.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
        <label className="flex flex-col text-xs">
          <span className="text-ui-text-dim">Origin</span>
          <select value={origin} onChange={(e) => setOrigin(e.target.value)} className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text">
            {PLANETS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label className="flex flex-col text-xs">
          <span className="text-ui-text-dim">Destination</span>
          <select value={dest} onChange={(e) => setDest(e.target.value)} className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text">
            {PLANETS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <NumIn label="Dep start (d)" value={depStart} onChange={setDepStart} />
        <NumIn label="Dep end (d)" value={depEnd} onChange={setDepEnd} />
        <NumIn label="Arr start (d)" value={arrStart} onChange={setArrStart} />
        <NumIn label="Arr end (d)" value={arrEnd} onChange={setArrEnd} />
        <NumIn label="Grid (each)" value={grid} onChange={(v) => setGrid(Math.max(8, Math.min(60, v)))} />
        <button
          onClick={compute}
          disabled={loading}
          className="self-end px-4 py-1 bg-ui-accent/40 hover:bg-ui-accent-strong text-white rounded text-sm disabled:opacity-50"
        >
          {loading ? 'Computing…' : 'Compute'}
        </button>
      </div>

      {err && (
        <div className="bg-sev-crit/40 border border-sev-crit rounded p-2 text-sev-crit text-xs mb-2">
          Error: {err}
        </div>
      )}

      <div
        className="relative"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          if (!data || !canvasRef.current) return;
          const hit = hitTestCell(e, canvasRef.current, data, depStart, depEnd, arrStart, arrEnd);
          if (hit) setHover({ hit, clientX: e.nativeEvent.offsetX, clientY: e.nativeEvent.offsetY });
          else setHover(null);
        }}
        onClick={(e) => {
          if (!data || !canvasRef.current) return;
          const hit = hitTestCell(e, canvasRef.current, data, depStart, depEnd, arrStart, arrEnd);
          if (hit) setPinned((prev) => prev && prev.i === hit.i && prev.j === hit.j ? null : hit);
        }}>
        <canvas
          ref={canvasRef}
          width={780}
          height={420}
          className="w-full border border-ui-border rounded cursor-crosshair block"
        />
        {hover && (
          <div className="absolute pointer-events-none z-10 px-2 py-1 rounded
                          border border-ui-accent bg-ui-bg-1/95 text-xs shadow-lg
                          whitespace-nowrap"
               style={{
                 left: Math.min(hover.clientX + 12, 600),
                 top:  Math.max(hover.clientY - 44, 4),
               }}>
            <div className="text-[10px] uppercase tracking-wider text-ui-accent">
              dep d{hover.hit.dep_day.toFixed(0)} → arr d{hover.hit.arr_day.toFixed(0)}
            </div>
            <div className="font-mono text-ui-text">
              C3 {hover.hit.c3 != null ? `${hover.hit.c3.toFixed(2)} km²/s²` : '—'}
            </div>
            <div className="font-mono text-ui-text-dim text-[11px]">
              v∞ arr {hover.hit.v_inf != null ? `${hover.hit.v_inf.toFixed(2)} km/s` : '—'} · TOF {hover.hit.tof != null ? `${hover.hit.tof.toFixed(0)} d` : '—'}
            </div>
          </div>
        )}
      </div>

      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
          <Stat label="Best C3" value={data.best_c3 !== null ? `${data.best_c3.toFixed(2)} km²/s²` : '—'} />
          <Stat label="Best dep day" value={`${data.best_dep_day.toFixed(0)}`} />
          <Stat label="Best arr day" value={`${data.best_arr_day.toFixed(0)}`} />
          <Stat label="Best TOF" value={`${data.best_tof_days.toFixed(0)} d`} />
          <Stat label="Valid Lambert solves" value={`${data.valid_count} / ${data.total_count}`} />
        </div>
      )}

      {/* Pinned-cell detail — click any grid cell to pin, click again
          to unpin.  Useful for comparing a "known good" cell against
          a later what-if window without re-hovering. */}
      {pinned && (
        <div className="mt-3 bg-ui-bg-1/60 border border-ui-accent rounded p-3 text-xs">
          <div className="flex items-baseline justify-between mb-2">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-ui-accent">Pinned transfer</div>
              <div className="text-sm text-ui-text font-mono">
                {origin} → {dest} · dep day {pinned.dep_day.toFixed(0)} · arr day {pinned.arr_day.toFixed(0)}
              </div>
            </div>
            <button onClick={() => setPinned(null)}
                    className="text-[10px] text-ui-text-dim hover:text-ui-text">unpin ✕</button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="C3" value={pinned.c3 != null ? `${pinned.c3.toFixed(2)} km²/s²` : '—'} />
            <Stat label="v∞ arrival" value={pinned.v_inf != null ? `${pinned.v_inf.toFixed(2)} km/s` : '—'} />
            <Stat label="Time of flight" value={pinned.tof != null ? `${pinned.tof.toFixed(0)} d` : '—'} />
            <Stat label="Δ from best C3"
                  value={pinned.c3 != null && data?.best_c3 != null
                    ? `${(pinned.c3 - data.best_c3).toFixed(2)} km²/s²`
                    : '—'} />
          </div>
        </div>
      )}

      <div className="mt-4 text-[11px] text-ui-text-dim space-y-1">
        <p>• Ephemeris: simplified circular heliocentric (±2%); use JPL DE430 for flight design.</p>
        <p>• C3 = launch v∞² (km²/s²). Mars Hohmann-class is ~14-18; Jupiter direct ~85.</p>
        <p>• White cross = global minimum found in the grid.</p>
      </div>
    </div>
  );
}

/** Translate a React MouseEvent on the wrapper div into (dep_idx,
 *  arr_idx) of the Lambert grid, and return the filled CellHit.  The
 *  padding constants must match the values used in the draw loop
 *  above (padL=56, padB=32, padT=16, padR=16). */
function hitTestCell(
  e: React.MouseEvent,
  canvas: HTMLCanvasElement,
  data: PorkchopResponse,
  depStart: number, depEnd: number,
  arrStart: number, arrEnd: number,
): CellHit | null {
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width  / rect.width;
  const scaleY = canvas.height / rect.height;
  const cx = (e.clientX - rect.left) * scaleX;
  const cy = (e.clientY - rect.top)  * scaleY;
  const padL = 56, padR = 16, padT = 16, padB = 32;
  const plotW = canvas.width - padL - padR;
  const plotH = canvas.height - padT - padB;
  if (cx < padL || cx > padL + plotW || cy < padT || cy > padT + plotH) return null;
  const c3 = data.c3_departure;
  const nDep = c3.length;
  const nArr = c3[0]?.length ?? 0;
  if (!nDep || !nArr) return null;
  const i = Math.max(0, Math.min(nDep - 1, Math.floor((cx - padL) / (plotW / nDep))));
  // Y is flipped — arrival increases upward.
  const jFromTop = Math.floor((cy - padT) / (plotH / nArr));
  const j = Math.max(0, Math.min(nArr - 1, nArr - 1 - jFromTop));
  const dep_day = data.departure_days[i] ?? (depStart + (i / (nDep - 1)) * (depEnd - depStart));
  const arr_day = data.arrival_days[j] ?? (arrStart + (j / (nArr - 1)) * (arrEnd - arrStart));
  return {
    i, j, dep_day, arr_day,
    c3:    c3[i][j],
    v_inf: data.v_inf_arrival[i]?.[j] ?? null,
    tof:   data.tof_days[i]?.[j] ?? null,
    canvasX: padL + (i + 0.5) * (plotW / nDep),
    canvasY: padT + (nArr - 1 - j + 0.5) * (plotH / nArr),
  };
}

function NumIn({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <label className="flex flex-col text-xs">
      <span className="text-ui-text-dim">{label}</span>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text"
      />
    </label>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
      <div className="text-xs text-ui-text-dim">{label}</div>
      <div className="text-base font-mono text-ui-text">{value}</div>
    </div>
  );
}
