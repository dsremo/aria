/**
 * Failure Cascade Simulator — click a part to see what breaks downstream.
 *
 * Uses /api/inspect/cascade/{part_id} to compute the full failure chain,
 * then visualizes it as an expanding ripple from the failed part outward.
 * Shows how many parts are doomed, which subsystems are affected, and
 * the severity of the cascade.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type CascadeResult, type PartSnapshot } from '../api/aria';

/** Common "what-if" anchor points — each tries a few candidate
 *  substring matches against the part catalog so the preset works
 *  even as part IDs get renamed.  If no match is found for a preset
 *  we just grey it out (rather than error silently on click). */
const PRESET_SCENARIOS: { name: string; match: (p: PartSnapshot) => boolean; hint: string }[] = [
  { name: 'Reactor primary',  match: (p) => /reactor|fusion_core|primary_coolant/i.test(p.part_id + ' ' + p.name), hint: 'fusion core primary loop' },
  { name: 'Main power bus',   match: (p) => /main_bus|power_bus|distribution/i.test(p.part_id + ' ' + p.name),    hint: 'ship-wide power distribution' },
  { name: 'ECLSS scrubber',   match: (p) => /scrubber|co2|air_revit/i.test(p.part_id + ' ' + p.name),             hint: 'life support air revitalisation' },
  { name: 'Radiator wing',    match: (p) => /radiator/i.test(p.part_id + ' ' + p.name),                            hint: 'thermal radiator array' },
  { name: 'Hab ring bearing', match: (p) => /bearing|maglev|ring_hub/i.test(p.part_id + ' ' + p.name),             hint: 'rotating habitat bearing' },
  { name: 'Shield layer 4',   match: (p) => /shield.*(4|layer_4|hydrogen)/i.test(p.part_id + ' ' + p.name),        hint: 'ablation-ice anti-GCR shield' },
];

export function CascadeSimulator() {
  const [parts, setParts] = useState<PartSnapshot[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [cascade, setCascade] = useState<CascadeResult | null>(null);
  const [loading, setLoading] = useState(false);
  // Recent simulation history — lets operators compare severity across
  // N scenarios without re-running them one at a time.
  const [history, setHistory] = useState<{
    partId: string; partName: string; count: number; at: number;
  }[]>([]);

  useEffect(() => {
    ariaApi.listParts().then(r => setParts(r.parts)).catch(() => {});
  }, []);

  const simulate = async (partId: string) => {
    setSelected(partId);
    setLoading(true);
    setCascade(null);
    try {
      const result = await ariaApi.cascade(partId);
      setCascade(result);
      const part = parts.find((p) => p.part_id === partId);
      setHistory((prev) => [
        { partId, partName: part?.name ?? partId, count: result.count, at: Date.now() },
        ...prev.filter((h) => h.partId !== partId),  // dedup most-recent wins
      ].slice(0, 6));
    } catch (e: any) {
      setCascade(null);
    } finally {
      setLoading(false);
    }
  };

  const resolvePreset = (p: typeof PRESET_SCENARIOS[number]) =>
    parts.find(p.match);

  const copyCascadeJson = () => {
    if (!cascade) return;
    const payload = {
      trigger_part: selected,
      count: cascade.count,
      cascade: cascade.cascade,
      subsystems_hit: Array.from(affectedSubsystems).sort(),
      severity,
      total_parts: parts.length,
      percent_of_ship: (cascade.count / Math.max(parts.length, 1)) * 100,
    };
    navigator.clipboard?.writeText(JSON.stringify(payload, null, 2))
      .catch(() => {/* older browser — silently fail */});
  };

  // Group parts by subsystem for the selector
  const grouped: Record<string, PartSnapshot[]> = {};
  for (const p of parts) {
    (grouped[p.subsystem] = grouped[p.subsystem] || []).push(p);
  }

  // Cascade analysis
  const cascadeSet = new Set(cascade?.cascade || []);
  const affectedSubsystems = new Set<string>();
  for (const p of parts) {
    if (cascadeSet.has(p.part_id)) affectedSubsystems.add(p.subsystem);
  }

  const severity =
    !cascade ? 'none' :
    cascade.count > 40 ? 'CATASTROPHIC' :
    cascade.count > 20 ? 'CRITICAL' :
    cascade.count > 5  ? 'SEVERE' :
    cascade.count > 0  ? 'MODERATE' : 'NONE';

  const sevColor =
    severity === 'CATASTROPHIC' ? 'text-sev-crit' :
    severity === 'CRITICAL' ? 'text-sev-crit' :
    severity === 'SEVERE' ? 'text-sev-warn' :
    severity === 'MODERATE' ? 'text-sev-warn' : 'text-sev-ok';

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Failure Cascade Simulator</h2>
        <p className="text-xs text-ui-text-dim">
          Select a part to simulate its failure. The cascade shows every downstream
          part that would fail as a consequence, based on the dependency graph.
        </p>
      </div>

      {/* Preset scenarios — jump to commonly-worried-about single-point
          failures without scrolling the 100+ part catalog.  Each preset
          resolves to whichever part_id currently matches its substring
          regex; if none matches, the button greys out. */}
      <div className="mb-3 flex flex-wrap gap-1 items-center text-[11px]">
        <span className="text-ui-text-faint uppercase tracking-wider mr-1">Presets:</span>
        {PRESET_SCENARIOS.map((ps) => {
          const p = resolvePreset(ps);
          return (
            <button key={ps.name}
                    onClick={() => p && simulate(p.part_id)}
                    disabled={!p}
                    title={p ? `${ps.hint} — ${p.part_id}` : 'no matching part in current catalog'}
                    className={`px-2 py-0.5 rounded border ${
                      !p ? 'border-ui-border-soft bg-ui-bg-1 text-ui-text-faint cursor-not-allowed'
                         : selected === p.part_id
                           ? 'border-sev-crit bg-sev-crit/40 text-sev-crit'
                           : 'border-ui-border bg-ui-bg-1 text-ui-text hover:border-ui-accent hover:bg-ui-bg-2'
                    }`}>
              {ps.name}
            </button>
          );
        })}
      </div>

      {/* Recent-scenario history for side-by-side severity comparison */}
      {history.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1 items-center text-[10px]">
          <span className="text-ui-text-faint uppercase tracking-wider mr-1">Recent:</span>
          {history.map((h) => (
            <button key={h.partId}
                    onClick={() => simulate(h.partId)}
                    title={`${h.partId} — last run ${Math.round((Date.now() - h.at) / 1000)} s ago`}
                    className={`px-2 py-0.5 rounded border ${
                      selected === h.partId
                        ? 'border-ui-accent bg-ui-accent/40 text-ui-accent'
                        : 'border-ui-border bg-ui-bg-1 text-ui-text hover:bg-ui-bg-2'
                    }`}>
              {h.partName} <span className="text-ui-text-faint">· {h.count}</span>
            </button>
          ))}
        </div>
      )}

      {/* Part selector */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-1 mb-4">
        {Object.entries(grouped).sort().map(([subsystem, subParts]) => (
          <div key={subsystem}>
            <div className="text-[8px] uppercase tracking-wider text-ui-text-faint font-bold mb-0.5">
              {subsystem}
            </div>
            {subParts.slice(0, 8).map(p => (
              <button
                key={p.part_id}
                onClick={() => simulate(p.part_id)}
                className={`block w-full text-left px-2 py-0.5 text-[10px] rounded mb-0.5 transition-colors ${
                  selected === p.part_id
                    ? 'bg-sev-crit/60 border border-sev-crit text-sev-crit'
                    : cascadeSet.has(p.part_id)
                    ? 'bg-sev-warn/40 border border-sev-warn/50 text-sev-warn'
                    : 'bg-ui-bg-2/40 border border-transparent text-ui-text hover:bg-ui-bg-3/40'
                }`}
              >
                {p.name}
              </button>
            ))}
          </div>
        ))}
      </div>

      {/* Loading */}
      {loading && (
        <div className="text-center text-ui-text-dim py-4">Simulating cascade...</div>
      )}

      {/* Results */}
      {cascade && !loading && (
        <div className="space-y-3">
          {/* Summary card */}
          <div className={`bg-ui-bg-1/60 border rounded-lg p-4 ${
            severity === 'CATASTROPHIC' ? 'border-sev-crit' :
            severity === 'CRITICAL' ? 'border-sev-crit' :
            severity === 'SEVERE' ? 'border-sev-warn' : 'border-ui-border'
          }`}>
            <div className="flex items-baseline justify-between mb-2">
              <div>
                <span className="text-sm font-bold text-sev-crit">{selected}</span>
                <span className="text-xs text-ui-text-dim ml-2">fails →</span>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-lg font-bold ${sevColor}`}>{severity}</span>
                <button onClick={copyCascadeJson}
                        title="Copy cascade as JSON"
                        className="px-2 py-0.5 text-[10px] rounded border border-ui-border bg-ui-bg-1
                                   hover:border-ui-accent hover:bg-ui-bg-2 text-ui-text">
                  ⎘ copy
                </button>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div>
                <div className="text-2xl font-bold text-sev-crit font-mono">{cascade.count}</div>
                <div className="text-[9px] text-ui-text-faint uppercase">Parts doomed</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-sev-warn font-mono">{affectedSubsystems.size}</div>
                <div className="text-[9px] text-ui-text-faint uppercase">Subsystems hit</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-ui-text font-mono">{parts.length}</div>
                <div className="text-[9px] text-ui-text-faint uppercase">Total parts</div>
              </div>
            </div>
            {/* Impact bar */}
            <div className="mt-3">
              <div className="h-3 bg-ui-bg-2 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    severity === 'CATASTROPHIC' ? 'bg-sev-crit' :
                    severity === 'CRITICAL' ? 'bg-sev-crit' :
                    severity === 'SEVERE' ? 'bg-sev-warn' : 'bg-sev-warn'
                  }`}
                  style={{ width: `${(cascade.count / Math.max(parts.length, 1)) * 100}%` }}
                />
              </div>
              <div className="text-[9px] text-ui-text-faint mt-0.5 text-center">
                {((cascade.count / Math.max(parts.length, 1)) * 100).toFixed(1)}% of ship affected
              </div>
            </div>
          </div>

          {/* Affected subsystems */}
          <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-wider text-ui-text-faint font-bold mb-2">
              Affected Subsystems
            </div>
            <div className="flex flex-wrap gap-1">
              {Array.from(affectedSubsystems).sort().map(sub => (
                <span key={sub} className="px-2 py-0.5 text-[10px] rounded bg-sev-crit/40 border border-sev-crit/50 text-sev-crit">
                  {sub}
                </span>
              ))}
            </div>
          </div>

          {/* Cascade chain */}
          <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-wider text-ui-text-faint font-bold mb-2">
              Cascade Chain ({cascade.count} parts)
            </div>
            <div className="flex flex-wrap gap-1 max-h-48 overflow-y-auto">
              {cascade.cascade.map((pid, i) => (
                <span key={pid} className="px-1.5 py-0.5 text-[9px] rounded bg-ui-bg-2 text-ui-text font-mono">
                  {i > 0 && <span className="text-sev-crit mr-1">→</span>}
                  {pid}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* No selection */}
      {!selected && !loading && (
        <div className="text-center text-ui-text-faint py-8">
          Click any part above to simulate its failure cascade.
        </div>
      )}
    </div>
  );
}
