/**
 * Dependency-graph visualiser. Renders the full DAG from /api/inspect/graph
 * as an interactive SVG — no react-flow dependency so the scaffold stays
 * install-free until the user runs `npm install`.
 *
 * Layout is a simple force-free circular sweep grouped by subsystem so it's
 * deterministic and readable for 30-node graphs. Nodes clickable → selects
 * the part in the parent (same behaviour as the 3D viewport click).
 */

import { useEffect, useMemo, useState } from 'react';
import { ariaApi, type DepGraph } from '../api/aria';

const SUBSYSTEM_ORDER = [
  'structure', 'propulsion', 'reactor', 'thermal', 'power',
  'shielding', 'habitat', 'eclss', 'agriculture',
  'comms', 'navigation', 'avionics', 'other',
];

const SUBSYSTEM_COLORS: Record<string, string> = {
  structure:   '#8892a8',
  propulsion:  '#ee8822',
  reactor:     '#ff5533',
  thermal:     '#4488ee',
  power:       '#f2c158',
  shielding:   '#4bd27a',
  habitat:     '#f2dba0',
  eclss:       '#a0e0c0',
  agriculture: '#86c26a',
  comms:       '#dde4ee',
  navigation:  '#d0d6e0',
  avionics:    '#b266e6',
  other:       '#667799',
};

function inferSubsystem(partId: string): string {
  if (partId.startsWith('hull_')) return 'structure';
  if (partId.startsWith('fuel_tank_') || partId === 'magnetic_nozzle' || partId.startsWith('engine_bell_')) return 'propulsion';
  if (partId === 'reactor_engine') return 'reactor';
  if (partId === 'thermal_loop' || partId.startsWith('radiator_array_')) return 'thermal';
  if (partId === 'power_distribution') return 'power';
  if (partId.startsWith('shield_layer_')) return 'shielding';
  if (partId === 'habitat_ring' || partId.startsWith('spoke_') || partId.startsWith('hab_module_')) return 'habitat';
  if (partId === 'eclss') return 'eclss';
  if (partId === 'agriculture') return 'agriculture';
  if (partId.startsWith('comm_antenna_') || partId === 'bow_sensor_ring') return 'comms';
  if (partId === 'avionics') return 'avionics';
  return 'other';
}

interface Props {
  selectedPartId: string | null;
  onSelectPart: (id: string) => void;
}

export function DepGraphViz({ selectedPartId, onSelectPart }: Props) {
  const [graph, setGraph] = useState<DepGraph | null>(null);
  const [err, setErr]     = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);

  useEffect(() => {
    ariaApi.graph().then(setGraph).catch((e: any) => setErr(String(e)));
  }, []);

  const layout = useMemo(() => graph ? computeLayout(graph) : null, [graph]);

  if (err)    return <div className="p-4 text-xs text-sev-crit">Graph API: {err}</div>;
  if (!graph) return <div className="p-4 text-xs text-ui-text-dim">Loading dependency graph…</div>;
  if (!layout) return null;

  // Highlight edges touching the hovered or selected node
  const focused = hover ?? selectedPartId;
  const edgeAdjacent = (src: string, dst: string) =>
    focused != null && (src === focused || dst === focused);

  const W = 900, H = 600;

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-1.5 border-b border-ui-border text-[10px] uppercase tracking-wider text-ui-accent font-bold">
        Dependency Graph · {graph.nodes.length} nodes · {graph.edges.length} edges
      </div>
      <div className="flex-1 overflow-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-full" preserveAspectRatio="xMidYMid meet">
          {/* Edges */}
          {graph.edges.map((e, i) => {
            const a = layout.positions[e.src];
            const b = layout.positions[e.dst];
            if (!a || !b) return null;
            const dim = focused != null && !edgeAdjacent(e.src, e.dst);
            const color = e.critical ? '#ef4444' : '#4b5563';
            return (
              <line key={i}
                    x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    stroke={color}
                    strokeWidth={e.critical ? 1.25 : 0.75}
                    strokeOpacity={dim ? 0.1 : (e.critical ? 0.8 : 0.4)}
                    strokeDasharray={e.critical ? '0' : '4 3'} />
            );
          })}
          {/* Nodes */}
          {graph.nodes.map(n => {
            const p = layout.positions[n];
            if (!p) return null;
            const sub = inferSubsystem(n);
            const color = SUBSYSTEM_COLORS[sub] ?? SUBSYSTEM_COLORS.other;
            const selected = selectedPartId === n;
            const hovered = hover === n;
            const r = hovered ? 8 : selected ? 7 : 5;
            return (
              <g key={n}
                 className="cursor-pointer"
                 onClick={() => onSelectPart(n)}
                 onMouseEnter={() => setHover(n)}
                 onMouseLeave={() => setHover(null)}>
                <circle cx={p.x} cy={p.y} r={r}
                        fill={color}
                        stroke={selected ? '#06b6d4' : '#0a0e17'}
                        strokeWidth={selected ? 2 : 1.5}
                        opacity={focused && !(selected || hovered || edgeAdjacent(focused, n) || edgeAdjacent(n, focused)) ? 0.35 : 1} />
                {(hovered || selected) && (
                  <text x={p.x} y={p.y - r - 4}
                        textAnchor="middle"
                        fontSize="10"
                        fill="#e2e8f0"
                        stroke="#0a0e17"
                        strokeWidth="3"
                        paintOrder="stroke"
                        pointerEvents="none">
                    {n}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
      <div className="px-3 py-1 border-t border-ui-border flex flex-wrap gap-2 text-[9px]">
        {SUBSYSTEM_ORDER.map(sub => (
          <div key={sub} className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full" style={{ background: SUBSYSTEM_COLORS[sub] }} />
            <span className="text-ui-text-dim">{sub}</span>
          </div>
        ))}
        <div className="ml-auto text-ui-text-dim">
          <span className="inline-block w-4 border-t-2 border-sev-crit align-middle" /> critical edge &nbsp;
          <span className="inline-block w-4 border-t border-ui-border-strong border-dashed align-middle" /> non-critical
        </div>
      </div>
    </div>
  );
}

/** Circular-by-subsystem layout — deterministic, readable for ≲ 100 nodes. */
function computeLayout(graph: DepGraph) {
  const bySubsystem: Record<string, string[]> = {};
  for (const n of graph.nodes) {
    const sub = inferSubsystem(n);
    (bySubsystem[sub] = bySubsystem[sub] ?? []).push(n);
  }
  const W = 900, H = 600;
  const cx = W / 2, cy = H / 2;
  const positions: Record<string, { x: number; y: number }> = {};
  const presentSubs = SUBSYSTEM_ORDER.filter(s => bySubsystem[s]?.length);

  const ringRadius = Math.min(W, H) * 0.38;
  presentSubs.forEach((sub, subIdx) => {
    const subAngle = (subIdx / presentSubs.length) * 2 * Math.PI - Math.PI / 2;
    const subCenterX = cx + Math.cos(subAngle) * ringRadius;
    const subCenterY = cy + Math.sin(subAngle) * ringRadius;
    const parts = bySubsystem[sub].sort();
    const clusterRadius = Math.min(70, 12 + parts.length * 2);
    parts.forEach((p, i) => {
      if (parts.length === 1) {
        positions[p] = { x: subCenterX, y: subCenterY };
      } else {
        const theta = (i / parts.length) * 2 * Math.PI;
        positions[p] = {
          x: subCenterX + Math.cos(theta) * clusterRadius,
          y: subCenterY + Math.sin(theta) * clusterRadius,
        };
      }
    });
  });

  return { positions };
}
