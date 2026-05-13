import { useEffect, useRef, useState } from 'react';
import { MessageSquareQuote } from 'lucide-react';
import { EmptyState } from './EmptyState';

// Live LLM advisor panel.
//
// Polls `/api/ai/advise` on a fixed cadence. Shows the LLM's structured
// recommendation when ANTHROPIC_API_KEY is set on the backend; otherwise
// falls back to deterministic rule-based heuristics. Either way, the UI
// contract is the same so the frontend doesn't care which side answered.

type Advice = {
  source: 'llm' | 'rule';
  severity: 'NOMINAL' | 'WARNING' | 'CRITICAL' | 'EMERGENCY';
  summary: string;
  recommendation: string;
  citations: string[];
  snapshot: any;
  sim_yr: number | null;
  latency_ms: number;
  llm_error?: string;
};

const POLL_MS = 30_000; // 30 s
const HISTORY = 8;

export function AIAdvisorPanel() {
  const [focus, setFocus] = useState<'auto' | 'hull' | 'power' | 'eclss' | 'trajectory'>('auto');
  const [auto, setAuto] = useState(true);
  const [history, setHistory] = useState<Advice[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const timerRef   = useRef<number | null>(null);
  const abortRef   = useRef<AbortController | null>(null);   // cancel in-flight
  const mountedRef = useRef(true);                            // skip setState after unmount
  const inflightRef = useRef(false);                          // skip overlapping polls

  // Track mount status so async callbacks don't setState post-unmount.
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  const runOnce = async () => {
    // Guard: an earlier poll is still running — skip this tick rather
    // than pile up overlapping requests against the same endpoint.
    if (inflightRef.current) return;
    inflightRef.current = true;

    // Cancel any previous request before starting a new one so the
    // focus-switch path doesn't append a stale-focus advice later.
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    if (mountedRef.current) { setBusy(true); setErr(null); }
    try {
      const r = await fetch('/api/ai/advise', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ focus }),
        signal: ac.signal,
      });
      if (!r.ok) {
        let detail = `HTTP ${r.status}`;
        try { const b = await r.json(); if (b?.error) detail = b.error; } catch { /* not JSON */ }
        throw new Error(detail);
      }
      const a: Advice = await r.json();
      if (mountedRef.current && !ac.signal.aborted) {
        setHistory(h => [a, ...h].slice(0, HISTORY));
      }
    } catch (e: any) {
      // Abort isn't a real error — user (or focus change) cancelled.
      if (e?.name !== 'AbortError' && mountedRef.current) {
        setErr(String(e));
      }
    } finally {
      if (mountedRef.current) setBusy(false);
      inflightRef.current = false;
    }
  };

  useEffect(() => {
    if (!auto) {
      if (timerRef.current) { window.clearInterval(timerRef.current); timerRef.current = null; }
      return;
    }
    runOnce();
    timerRef.current = window.setInterval(runOnce, POLL_MS);
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto, focus]);

  const sevColor = (s: Advice['severity']) =>
    ({
      NOMINAL:   'text-sev-ok border-sev-ok bg-sev-ok/20',
      WARNING:   'text-sev-warn border-sev-warn bg-sev-warn/20',
      CRITICAL:  'text-sev-crit border-sev-crit bg-sev-crit/20',
      EMERGENCY: 'text-sev-crit border-sev-crit bg-sev-crit/50',
    }[s]);

  return (
    <div className="p-4 text-sm">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">ARIA — Live AI Advisor</h2>
        <p className="text-xs text-ui-text-dim mt-1 max-w-3xl">
          Polls <code className="text-ui-accent">/api/ai/advise</code> every 30 s during a mission.
          Sends the current ship state (hull, power, food, crew, trajectory, recent events) to
          the LLM backend when <code>ANTHROPIC_API_KEY</code> is set; otherwise a deterministic rule engine
          answers with the same schema. History of the last {HISTORY} advisories is kept.
        </p>
      </div>

      <div className="flex items-center gap-3 mb-3 text-xs">
        <label className="flex items-center gap-1">
          Focus:
          <select value={focus} onChange={e => setFocus(e.target.value as any)}
                  className="bg-ui-bg-2 border border-ui-border rounded px-2 py-1">
            <option value="auto">auto</option>
            <option value="hull">hull</option>
            <option value="power">power</option>
            <option value="eclss">eclss / food</option>
            <option value="trajectory">trajectory</option>
          </select>
        </label>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={auto} onChange={e => setAuto(e.target.checked)} />
          Auto-poll (30 s)
        </label>
        <button onClick={runOnce} disabled={busy}
                className="px-2 py-1 bg-ui-accent-strong hover:bg-ui-accent disabled:opacity-60 rounded">
          {busy ? '…asking' : '▶ Advise now'}
        </button>
        {err && <span className="text-sev-crit">{err}</span>}
      </div>

      {history.length === 0 && (
        <EmptyState Icon={MessageSquareQuote}
                    title="No advisories yet"
                    hint="Click ▶ Advise now or enable auto-poll. The advisor sends ship state to the LLM backend (or the rule fallback) and renders a verdict."
                    size="sm" />
      )}

      {history.length > 0 && history.every(a => a.source === 'rule') && (
        <div className="mb-3 px-3 py-2 rounded border border-sev-info/40 bg-sev-info/10 text-[11px] text-ui-text">
          <strong className="text-sev-info">Heads-up:</strong> all {history.length} advisories
          came from the deterministic <em>rule</em> backend, not the LLM. To enable LLM
          advisories, export <code className="text-ui-accent">ANTHROPIC_API_KEY</code> in the
          environment that runs <code>aria.simulator.web_dashboard</code> and restart the
          dashboard. The rule engine will keep working as a fallback either way.
        </div>
      )}

      <div className="space-y-3">
        {history.map((a, i) => (
          <div key={i} className={`border rounded p-3 ${sevColor(a.severity)}`}>
            <div className="flex items-center justify-between mb-1">
              <span className="font-semibold">{a.severity}</span>
              <span className="text-xs text-ui-text-dim">
                {a.source === 'llm' ? '⚛ llm' : '⚙ rules'} · {a.latency_ms} ms
                {a.sim_yr !== null && <> · yr {a.sim_yr?.toFixed(2)}</>}
              </span>
            </div>
            <div className="mb-1">{a.summary}</div>
            <pre className="text-xs whitespace-pre-wrap text-ui-text">{a.recommendation}</pre>
            {a.citations.length > 0 && (
              <div className="text-[10px] text-ui-text-dim mt-1">
                Cited: {a.citations.join(' · ')}
              </div>
            )}
            {a.llm_error && (
              <div className="text-[10px] text-sev-warn mt-1">LLM error (fell back): {a.llm_error}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
