/**
 * Ship Cross-Section — interactive 2D side-profile cutaway diagram.
 *
 * Shows the generation ship from a longitudinal cross-section view with
 * all major subsystems labeled and color-coded. Click a subsystem to
 * select it (links to the part inspector). Hover shows a tooltip.
 *
 * Layout (stern → bow, left → right):
 *   [Nozzle] [Reactor] [Fuel Tanks] [Hull + ECLSS] [Habitat Ring] [Shield Stack] [Sensors]
 *
 * Uses the ship's actual dimensions from /api/ship/params.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type ShipParams } from '../api/aria';

interface SubsystemRect {
  id: string;
  label: string;
  x: number;      // normalized 0-1 along ship length
  y: number;      // 0 = center, positive = up
  w: number;
  h: number;
  color: string;
  description: string;
}

const SUBSYSTEMS: SubsystemRect[] = [
  { id: 'magnetic_nozzle',  label: 'Magnetic Nozzle',     x: 0.00,  y: -0.05, w: 0.06, h: 0.30, color: '#3b82f6', description: 'Plasma exhaust nozzle, 10 kN thrust' },
  { id: 'engine_bell_0',    label: 'Engine Bells',        x: 0.02,  y: -0.25, w: 0.04, h: 0.12, color: '#f97316', description: '4 × plasma engine bells' },
  { id: 'reactor_engine',   label: 'Fusion Reactor',      x: 0.07,  y: -0.10, w: 0.08, h: 0.40, color: '#ef4444', description: 'D/He-3 fusion, 100 MWt' },
  { id: 'fuel_tank_0',      label: 'Cryo Fuel A',         x: 0.16,  y: -0.15, w: 0.06, h: 0.20, color: '#e2e8f0', description: 'D-He3 cryogenic tank' },
  { id: 'fuel_tank_1',      label: 'Cryo Fuel B',         x: 0.16,  y:  0.10, w: 0.06, h: 0.20, color: '#e2e8f0', description: 'D-He3 cryogenic tank' },
  { id: 'fuel_tank_2',      label: 'Cryo Fuel C',         x: 0.23,  y: -0.05, w: 0.06, h: 0.20, color: '#e2e8f0', description: 'D-He3 cryogenic tank' },
  { id: 'radiator_array_0', label: 'Radiator +Y',         x: 0.18,  y:  0.35, w: 0.20, h: 0.05, color: '#f97316', description: 'NaK heat radiator, 50k m²' },
  { id: 'radiator_array_1', label: 'Radiator -Y',         x: 0.18,  y: -0.35, w: 0.20, h: 0.05, color: '#f97316', description: 'NaK heat radiator, 50k m²' },
  { id: 'hull_main',        label: 'Pressure Hull',       x: 0.30,  y: -0.12, w: 0.35, h: 0.44, color: '#94a3b8', description: 'Ti-6Al-4V hull, 712 m × 80 mm' },
  { id: 'eclss',            label: 'ECLSS',               x: 0.32,  y: -0.02, w: 0.08, h: 0.14, color: '#22c55e', description: 'Life support, atmosphere, water' },
  { id: 'agriculture',      label: 'Agriculture',         x: 0.41,  y: -0.02, w: 0.06, h: 0.10, color: '#84cc16', description: 'Hydroponic farm, 5 crops' },
  { id: 'habitat_ring',     label: 'Habitat Ring',        x: 0.48,  y: -0.30, w: 0.12, h: 0.80, color: '#eab308', description: 'O\'Neill torus, 1000 m, 0.56 g' },
  { id: 'spoke_0',          label: 'Spokes (×6)',         x: 0.52,  y: -0.05, w: 0.04, h: 0.30, color: '#a1a1aa', description: '6 hollow CNT tubes' },
  { id: 'shield_layer_4',   label: 'Ice Shield',          x: 0.66,  y: -0.14, w: 0.10, h: 0.48, color: '#7dd3fc', description: '5.45 m water ice ablation' },
  { id: 'shield_layer_2',   label: 'Mag Shield',          x: 0.77,  y: -0.12, w: 0.04, h: 0.44, color: '#fbbf24', description: 'Superconducting deflector' },
  { id: 'shield_layer_0',   label: 'LIDAR Array',         x: 0.82,  y: -0.10, w: 0.04, h: 0.40, color: '#67e8f9', description: 'Threat detection' },
  { id: 'bow_sensor_ring',  label: 'Bow Sensors',         x: 0.87,  y: -0.08, w: 0.06, h: 0.36, color: '#a5b4fc', description: 'LIDAR, optical, IR sensors' },
  { id: 'comm_antenna_0',   label: 'Comms Array',         x: 0.50,  y:  0.40, w: 0.08, h: 0.06, color: '#c4b5fd', description: 'Ka-band long-haul antenna' },
  { id: 'docking_port_0',   label: 'Docking',             x: 0.94,  y: -0.02, w: 0.05, h: 0.12, color: '#cbd5e1', description: 'IDSS-compatible docking port' },
];

interface Props {
  onSelectPart?: (id: string) => void;
}

export function ShipCrossSection({ onSelectPart }: Props) {
  const [params, setParams] = useState<ShipParams | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  useEffect(() => {
    ariaApi.shipParams().then(setParams).catch(() => {});
  }, []);

  const SVG_W = 1000;
  const SVG_H = 400;
  const CX = SVG_W / 2;
  const CY = SVG_H / 2;
  const SCALE_X = SVG_W * 0.9;
  const SCALE_Y = SVG_H * 0.8;

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-2 border-b border-ui-border">
        <div className="text-[10px] uppercase tracking-widest text-ui-accent font-bold">
          Ship Cross-Section · Side Profile
        </div>
        <div className="text-[10px] text-ui-text-dim">
          Click a subsystem to inspect. {params ? `Hull ${params.hull_length_m.toFixed(0)} m × R ${params.hull_radius_m.toFixed(1)} m` : 'Loading...'}
        </div>
      </div>

      <div className="flex-1 p-3">
        <svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} className="w-full h-full" preserveAspectRatio="xMidYMid meet">
          {/* Background grid */}
          {Array.from({ length: 21 }, (_, i) => {
            const x = (i / 20) * SVG_W;
            return <line key={`vg-${i}`} x1={x} y1={0} x2={x} y2={SVG_H} stroke="#1e293b" strokeWidth={0.5} />;
          })}
          {Array.from({ length: 11 }, (_, i) => {
            const y = (i / 10) * SVG_H;
            return <line key={`hg-${i}`} x1={0} y1={y} x2={SVG_W} y2={y} stroke="#1e293b" strokeWidth={0.5} />;
          })}

          {/* Ship outline (hull silhouette) */}
          <ellipse
            cx={CX} cy={CY} rx={SCALE_X * 0.48} ry={SCALE_Y * 0.22}
            fill="none" stroke="#334155" strokeWidth={1.5} strokeDasharray="4 3"
          />

          {/* Subsystem blocks */}
          {SUBSYSTEMS.map(sub => {
            const x = (sub.x - 0.02) * SCALE_X + (SVG_W - SCALE_X) / 2;
            const y = CY + sub.y * SCALE_Y - (sub.h * SCALE_Y) / 2;
            const w = sub.w * SCALE_X;
            const h = sub.h * SCALE_Y;
            const isHovered = hovered === sub.id;
            return (
              <g
                key={sub.id}
                className="cursor-pointer"
                onClick={() => onSelectPart?.(sub.id)}
                onMouseEnter={() => setHovered(sub.id)}
                onMouseLeave={() => setHovered(null)}
              >
                <rect
                  x={x} y={y} width={w} height={h} rx={4}
                  fill={sub.color}
                  fillOpacity={isHovered ? 0.9 : 0.6}
                  stroke={isHovered ? '#06b6d4' : '#0f172a'}
                  strokeWidth={isHovered ? 2.5 : 1}
                />
                {w > 30 && h > 15 && (
                  <text
                    x={x + w / 2} y={y + h / 2 + 3}
                    textAnchor="middle" fontSize={Math.min(10, w / 6)}
                    fontWeight="600" fill="white"
                    pointerEvents="none"
                  >
                    {sub.label}
                  </text>
                )}
              </g>
            );
          })}

          {/* Stern/Bow labels */}
          <text x={30} y={CY + 4} fontSize="11" fill="#64748b" fontWeight="500">STERN</text>
          <text x={SVG_W - 30} y={CY + 4} textAnchor="end" fontSize="11" fill="#64748b" fontWeight="500">BOW</text>

          {/* Velocity arrow */}
          <line x1={SVG_W - 80} y1={30} x2={SVG_W - 20} y2={30} stroke="#06b6d4" strokeWidth={2} markerEnd="url(#arrow)" />
          <defs>
            <marker id="arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <polygon points="0 0, 8 3, 0 6" fill="#06b6d4" />
            </marker>
          </defs>
          <text x={SVG_W - 50} y={22} textAnchor="middle" fontSize="9" fill="#06b6d4">v →</text>
        </svg>
      </div>

      {/* Hover tooltip */}
      {hovered && (() => {
        const sub = SUBSYSTEMS.find(s => s.id === hovered);
        if (!sub) return null;
        return (
          <div className="px-3 py-2 border-t border-ui-border flex items-baseline gap-3 text-xs">
            <div className="w-3 h-3 rounded" style={{ background: sub.color }} />
            <div>
              <span className="font-bold text-ui-text">{sub.label}</span>
              <span className="text-ui-text-dim ml-2">{sub.description}</span>
              <span className="text-ui-text-faint ml-2 font-mono">{sub.id}</span>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
