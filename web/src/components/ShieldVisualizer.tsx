/**
 * Shield Erosion Visualizer — 7-layer shield health display.
 *
 * Shows the 7 concentric shield layers from the ship parameters:
 * L0 LIDAR → L1 Plasma → L2 Magnetic → L3 Grid → L4 Ice → L5 Whipple → L6 Hull.
 * Each layer displayed as a horizontal bar with thickness and material info.
 *
 * Reads from /api/ship/params for the shield_layers array.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type ShipParams } from '../api/aria';

const LAYER_COLORS = [
  '#67e8f9', // L0 LIDAR — cyan
  '#a78bfa', // L1 Plasma — purple
  '#fbbf24', // L2 Magnetic — amber
  '#f97316', // L3 Grid — orange
  '#7dd3fc', // L4 Ice — light blue
  '#94a3b8', // L5 Whipple — grey
  '#e2e8f0', // L6 Hull — white
];

const LAYER_DESCRIPTIONS = [
  'Threat detection — LIDAR + IR sensors',
  'Active plasma deflector — ionise neutrals',
  'Superconducting magnetic deflector — bend charged particles',
  'Electrostatic tungsten mesh grid',
  'Water ice ablation shield — 5.45 m',
  'SiC-Kevlar-Al Whipple bumper — shrapnel breakup',
  'Structural Ti-6Al-4V + HealTech self-repair',
];

export function ShieldVisualizer() {
  const [params, setParams] = useState<ShipParams | null>(null);

  useEffect(() => {
    ariaApi.shipParams().then(setParams).catch(() => {});
  }, []);

  if (!params) return <div className="p-4 text-sm text-ui-text-dim">Loading shield data...</div>;

  const layers = params.shield_layers || [];
  const totalThickness = layers.reduce((s, l) => s + l.thickness_m, 0);

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Shield Stack — 7 Layers</h2>
        <p className="text-xs text-ui-text-dim">
          Total shield thickness: {totalThickness.toFixed(2)} m across {layers.length} layers.
          Bow-facing only — at 0.05c cruise, 99% of flux is forward.
        </p>
      </div>

      {/* Concentric rings visualization */}
      <div className="flex justify-center mb-4">
        <svg viewBox="0 0 400 400" className="w-64 h-64">
          {layers.map((layer, i) => {
            const outerR = 180 - i * 22;
            const innerR = outerR - Math.max(8, layer.thickness_m * 3);
            return (
              <g key={i}>
                <circle
                  cx={200} cy={200} r={outerR}
                  fill="none" stroke={LAYER_COLORS[i] || '#475569'}
                  strokeWidth={outerR - innerR}
                  strokeOpacity={0.7}
                />
                <text
                  x={200 + outerR - 5} y={200 - 4}
                  fontSize="8" fill={LAYER_COLORS[i]} fontWeight="600"
                  textAnchor="end"
                >
                  L{i}
                </text>
              </g>
            );
          })}
          {/* Center: Hull */}
          <circle cx={200} cy={200} r={30} fill="#1e293b" stroke="#475569" />
          <text x={200} y={203} textAnchor="middle" fontSize="9" fill="#94a3b8">HULL</text>
          {/* Arrow showing threat direction */}
          <line x1={370} y1={200} x2={200 + 185} y2={200} stroke="#ef4444" strokeWidth={2} markerEnd="url(#shieldArrow)" />
          <defs>
            <marker id="shieldArrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <polygon points="0 0, 8 3, 0 6" fill="#ef4444" />
            </marker>
          </defs>
          <text x={380} y={195} fontSize="9" fill="#ef4444" textAnchor="end">Threat</text>
        </svg>
      </div>

      {/* Layer detail cards */}
      <div className="space-y-2">
        {layers.map((layer, i) => {
          const pct = totalThickness > 0 ? (layer.thickness_m / totalThickness) * 100 : 0;
          return (
            <div key={i} className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 rounded" style={{ background: LAYER_COLORS[i] || '#475569' }} />
                  <span className="text-sm font-bold text-ui-text">
                    L{i} — {layer.name.replace(/_/g, ' ')}
                  </span>
                </div>
                <span className="text-xs font-mono text-ui-accent">
                  {layer.thickness_m >= 1 ? `${layer.thickness_m.toFixed(2)} m` : `${(layer.thickness_m * 1000).toFixed(1)} mm`}
                </span>
              </div>
              <div className="text-[10px] text-ui-text-dim mb-1.5">
                {LAYER_DESCRIPTIONS[i] || layer.material}
              </div>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-2 bg-ui-bg-2 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${pct}%`, background: LAYER_COLORS[i] }}
                  />
                </div>
                <span className="text-[9px] text-ui-text-faint w-10 text-right">{pct.toFixed(1)}%</span>
                <span className="text-[9px] text-ui-text-faint font-mono">{layer.material}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
