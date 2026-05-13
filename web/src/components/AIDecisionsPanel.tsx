/**
 * AI Decisions — closed-loop trace of every LLM-involved decision.
 *
 * Polls /api/ai/decisions every 2s with since_id so we only pull new entries.
 * Each row shows source (agent / advisor), question, tools invoked, the LLM
 * response, severity, and end-to-end latency.
 *
 * Why this matters: it's the visible proof that the LLM is actually wired to
 * the simulator (not just "text advice").  When an agent calls
 * request_reasoning(), the coordinator routes it to CognitiveEngine, the
 * engine runs the tool-use loop, and the result shows up here with the tools
 * it invoked listed.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

interface DecisionEntry {
  id: number;
  ts: number;
  source: 'agent' | 'advisor' | 'manual';
  agent: string | null;
  question: string;
  response: string;
  tools_used: string[];
  steps: number;
  severity: string;
  backend: string;
  trace_id: string | null;
  latency_ms: number | null;
}

interface DecisionsResponse {
  count: number;
  capacity: number;
  entries: DecisionEntry[];
}

const SEVERITY_COLOR: Record<string, string> = {
  NOMINAL: 'text-sev-ok',
  INFO:    'text-ui-text',
  WARNING: 'text-sev-warn',
  CRITICAL: 'text-sev-crit',
  EMERGENCY: 'text-sev-crit font-bold',
};

const SOURCE_COLOR: Record<string, string> = {
  agent: 'text-ui-accent',
  advisor: 'text-ui-accent',
  manual: 'text-ui-text-dim',
};

function fmtTs(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toISOString().substring(11, 19) + ' UT';
}

export function AIDecisionsPanel() {
  const [entries, setEntries] = useState<DecisionEntry[]>([]);
  const [capacity, setCapacity] = useState(400);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [filter, setFilter] = useState<'all' | 'agent' | 'advisor'>('all');
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const sinceRef = useRef(0);

  const fetchOnce = async () => {
    try {
      const r = await fetch(`/api/ai/decisions?limit=100&since_id=${sinceRef.current}`);
      if (!r.ok) return;
      const j: DecisionsResponse = await r.json();
      setCapacity(j.capacity);
      if (j.entries.length > 0) {
        setEntries((prev) => {
          const merged = [...prev, ...j.entries];
          const unique = new Map<number, DecisionEntry>();
          for (const e of merged) unique.set(e.id, e);
          return Array.from(unique.values()).sort((a, b) => a.id - b.id);
        });
        sinceRef.current = Math.max(sinceRef.current, ...j.entries.map((e) => e.id));
      }
    } catch { /* swallow – dashboard may be restarting */ }
  };

  useEffect(() => { fetchOnce(); }, []);
  useEffect(() => {
    if (!autoRefresh) return;
    const h = setInterval(fetchOnce, 2000);
    return () => clearInterval(h);
  }, [autoRefresh]);

  const visible = useMemo(
    () => entries.filter((e) => filter === 'all' || e.source === filter).reverse(),
    [entries, filter],
  );

  const agentCount = useMemo(() => entries.filter((e) => e.source === 'agent').length, [entries]);
  const advisorCount = useMemo(() => entries.filter((e) => e.source === 'advisor').length, [entries]);

  /** Tool-use frequency over the currently-visible (filtered) entries —
   *  lets operators see which simulator tools the LLM actually reaches
   *  for, and spot "the agent is asking but never using any tool" as a
   *  warning sign. */
  const toolStats = useMemo(() => {
    const counter = new Map<string, number>();
    for (const e of entries) {
      if (filter !== 'all' && e.source !== filter) continue;
      for (const t of e.tools_used) counter.set(t, (counter.get(t) || 0) + 1);
    }
    return [...counter.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);
  }, [entries, filter]);

  /** End-to-end latency stats over the currently-visible (filtered)
   *  entries.  p50 and p95 land under the overall badge row so reviewers
   *  catch a tail blowing out without having to read every `latency_ms`. */
  const latencyStats = useMemo(() => {
    const xs = entries
      .filter((e) => (filter === 'all' || e.source === filter) && e.latency_ms != null)
      .map((e) => e.latency_ms as number)
      .sort((a, b) => a - b);
    if (xs.length === 0) return null;
    const p = (q: number) => xs[Math.min(xs.length - 1, Math.floor(q * xs.length))];
    return {
      min:  xs[0],
      p50:  p(0.5),
      p95:  p(0.95),
      max:  xs[xs.length - 1],
      count: xs.length,
    };
  }, [entries, filter]);

  const exportFiltered = () => {
    const rows = entries.filter((e) => filter === 'all' || e.source === filter);
    const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `aria-ai-decisions-${filter}-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const toggle = (id: number) => {
    const next = new Set(expanded);
    if (next.has(id)) next.delete(id); else next.add(id);
    setExpanded(next);
  };

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-ui-accent">AI Decisions — Closed-Loop Trace</h2>
          <p className="text-xs text-ui-text-dim">
            {entries.length} entries · {agentCount} agent-reasoning · {advisorCount} advisor · capacity {capacity}
          </p>
        </div>
        <label className="flex items-center gap-1 text-xs text-ui-text">
          <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
          Auto-refresh (2s)
        </label>
      </div>

      <div className="mb-3 flex gap-1 items-center flex-wrap">
        {(['all', 'agent', 'advisor'] as const).map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`px-3 py-0.5 text-xs rounded border ${
              filter === s
                ? 'bg-ui-accent/40 border-ui-accent text-white'
                : 'bg-ui-bg-2 border-ui-border text-ui-text hover:border-ui-border-strong'
            }`}
          >
            {s}
          </button>
        ))}
        {latencyStats && (
          <div className="ml-3 flex gap-2 text-[10px] font-mono">
            <span className="px-2 py-0.5 rounded border border-ui-border bg-ui-bg-1 text-ui-text">
              p50 <span className="text-ui-accent">{latencyStats.p50.toFixed(0)}</span> ms
            </span>
            <span className="px-2 py-0.5 rounded border border-ui-border bg-ui-bg-1 text-ui-text">
              p95 <span className={latencyStats.p95 > 10000 ? 'text-sev-warn' : 'text-ui-accent'}>{latencyStats.p95.toFixed(0)}</span> ms
            </span>
            <span className="px-2 py-0.5 rounded border border-ui-border bg-ui-bg-1 text-ui-text">
              min {latencyStats.min.toFixed(0)} / max {latencyStats.max.toFixed(0)} ms · n={latencyStats.count}
            </span>
          </div>
        )}
        <button
          onClick={exportFiltered}
          disabled={entries.length === 0}
          className="ml-auto px-3 py-0.5 text-xs rounded border bg-ui-bg-2 border-ui-border text-ui-text hover:border-ui-border-strong disabled:opacity-40"
        >
          ⇩ export
        </button>
        <button
          onClick={() => { setEntries([]); sinceRef.current = 0; fetchOnce(); }}
          className="px-3 py-0.5 text-xs rounded border bg-ui-bg-2 border-ui-border text-ui-text hover:border-ui-border-strong"
        >
          Reload all
        </button>
      </div>

      {toolStats.length > 0 && (
        <div className="mb-3 bg-ui-bg-1/60 border border-ui-border rounded p-3">
          <div className="text-[10px] uppercase tracking-wider text-ui-text-faint mb-2">
            Most-used simulator tools (current filter)
          </div>
          <div className="space-y-1">
            {toolStats.map(([tool, n]) => {
              const max = toolStats[0][1];
              const pct = (n / max) * 100;
              return (
                <div key={tool} className="flex items-center gap-2 text-[11px]">
                  <code className="text-sev-ok w-40 truncate">{tool}</code>
                  <div className="flex-1 h-2 bg-ui-bg-2 rounded overflow-hidden">
                    <div className="h-full bg-sev-ok" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="font-mono text-ui-text-dim w-10 text-right">{n}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {visible.length === 0 && (
        <div className="bg-ui-bg-1/60 border border-ui-border rounded p-6 text-center text-ui-text-faint text-sm">
          No AI decisions yet. Trigger the AI Advisor tab or let an agent raise a reasoning request.
        </div>
      )}

      <div className="space-y-2">
        {visible.map((e) => {
          const isOpen = expanded.has(e.id);
          const sevColor = SEVERITY_COLOR[e.severity] || 'text-ui-text';
          const srcColor = SOURCE_COLOR[e.source] || 'text-ui-text-dim';
          return (
            <div key={e.id} className="bg-ui-bg-1/60 border border-ui-border rounded overflow-hidden">
              <button
                onClick={() => toggle(e.id)}
                className="w-full text-left p-3 hover:bg-ui-bg-1 transition"
              >
                <div className="flex items-center gap-3 text-xs">
                  <span className="font-mono text-ui-text-faint w-16">#{e.id}</span>
                  <span className="font-mono text-ui-text-dim w-24">{fmtTs(e.ts)}</span>
                  <span className={`font-semibold w-16 ${srcColor}`}>{e.source}</span>
                  {e.agent && (
                    <span className="text-ui-accent w-24 truncate">{e.agent}</span>
                  )}
                  <span className={`font-semibold w-24 ${sevColor}`}>{e.severity}</span>
                  <span className="text-ui-text-faint w-20">
                    {e.backend} · {e.steps}stp
                  </span>
                  {e.latency_ms !== null && (
                    <span className="text-ui-text-faint w-16 text-right">{e.latency_ms.toFixed(0)}ms</span>
                  )}
                  <span className="flex-1 text-ui-text truncate">{e.question || '—'}</span>
                  <span className="text-ui-text-faint">{isOpen ? '▾' : '▸'}</span>
                </div>
              </button>
              {isOpen && (
                <div className="border-t border-ui-border p-3 text-xs space-y-2">
                  <div>
                    <div className="text-ui-text-faint mb-1">Question</div>
                    <div className="bg-ui-bg-0 border border-ui-border-soft rounded p-2 font-mono text-ui-text whitespace-pre-wrap">
                      {e.question || '(empty)'}
                    </div>
                  </div>
                  {e.tools_used.length > 0 && (
                    <div>
                      <div className="text-ui-text-faint mb-1">Tools invoked ({e.tools_used.length})</div>
                      <div className="flex flex-wrap gap-1">
                        {e.tools_used.map((t, i) => (
                          <code key={i} className="bg-ui-bg-2 border border-ui-border rounded px-2 py-0.5 text-sev-ok">
                            {t}
                          </code>
                        ))}
                      </div>
                    </div>
                  )}
                  <div>
                    <div className="text-ui-text-faint mb-1">Response</div>
                    <div className="bg-ui-bg-0 border border-ui-border-soft rounded p-2 font-mono text-ui-text whitespace-pre-wrap">
                      {e.response || '(empty)'}
                    </div>
                  </div>
                  {e.trace_id && (
                    <div className="text-ui-text-faint">
                      trace_id: <span className="font-mono text-ui-text-dim">{e.trace_id}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-4 text-[11px] text-ui-text-dim space-y-1">
        <p>• <span className="text-ui-accent">agent</span> rows are full closed-loop decisions: agent raises a question → CognitiveEngine runs tool-use loop → response published back to requesting agent.</p>
        <p>• <span className="text-ui-accent">advisor</span> rows are UI-initiated `/api/ai/advise` polls: a state snapshot is sent to the LLM backend for JSON-formatted recommendations (no tool loop).</p>
        <p>• Click any row to expand the full question / tools / response.</p>
      </div>
    </div>
  );
}
