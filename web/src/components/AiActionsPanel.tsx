/**
 * AI Actions panel — recon view of every LLM-derived action across
 * the agent fleet. Two row statuses:
 *
 *   advisory  — parsed intent that no agent dispatched
 *   executed  — agent actually ran the corresponding actuator command
 *
 * Polls /api/ai/recent_actions every 5 s with `since_id` so the
 * payload stays small. Filters by agent + status. Shown alongside
 * the AI Decisions tab so operators can see decisions (LLM Q&A) and
 * actions (concrete state changes) side-by-side.
 *
 * Roadmap Track 3 Phase 5 — operator oversight surface.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Cog } from 'lucide-react';
import { ariaApi, type AiActionEntry } from '../api/aria';
import { EmptyState } from './EmptyState';

const AGENTS = ['power', 'thermal', 'eclss', 'comms', 'navigation', 'propulsion'];

const STATUS_COLOR: Record<string, string> = {
  executed: 'bg-sev-ok/40 text-sev-ok border-sev-ok/40',
  advisory: 'bg-sev-warn/30 text-sev-warn border-sev-warn/30',
};

function fmtTs(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString();
}

export function AiActionsPanel() {
  const [entries, setEntries] = useState<AiActionEntry[]>([]);
  const [agentFilter, setAgentFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<'' | 'advisory' | 'executed'>('');
  const [err, setErr] = useState<string | null>(null);
  const sinceRef = useRef(0);

  const tick = useMemo(
    () =>
      async () => {
        try {
          const r = await ariaApi.aiRecentActions(
            sinceRef.current,
            agentFilter || undefined,
            statusFilter || undefined,
          );
          if (r.entries.length > 0) {
            sinceRef.current = r.entries[r.entries.length - 1].id;
            setEntries((prev) => {
              // Keep up to 200 entries on the client side.
              const next = [...prev, ...r.entries];
              return next.slice(-200);
            });
          }
          setErr(null);
        } catch (e) {
          setErr((e as Error).message);
        }
      },
    [agentFilter, statusFilter],
  );

  // Reset since-id when filters change so we re-fetch the matching slice.
  useEffect(() => {
    sinceRef.current = 0;
    setEntries([]);
  }, [agentFilter, statusFilter]);

  useEffect(() => {
    tick();
    const id = setInterval(tick, 5_000);
    return () => clearInterval(id);
  }, [tick]);

  const filtered = entries; // server already filters by agent/status

  return (
    <div className="h-full flex flex-col p-3">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-ui-accent">AI Actions</h2>
          <p className="text-xs text-ui-text-dim">
            Per-agent LLM actions (advisory + executed) · {entries.length} buffered
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            className="bg-ui-bg-0 border border-ui-border rounded text-xs text-ui-text px-1 py-1"
          >
            <option value="">all agents</option>
            {AGENTS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as '' | 'advisory' | 'executed')}
            className="bg-ui-bg-0 border border-ui-border rounded text-xs text-ui-text px-1 py-1"
          >
            <option value="">advisory + executed</option>
            <option value="executed">executed only</option>
            <option value="advisory">advisory only</option>
          </select>
        </div>
      </div>

      {err && (
        <div className="mb-2 rounded border border-sev-crit/40 bg-sev-crit/30 px-3 py-2 text-xs text-sev-crit">
          {err}
        </div>
      )}

      {filtered.length === 0 ? (
        <EmptyState Icon={Cog}
                    title="No actions executed"
                    hint={<>
                      The AI only dispatches actions when it sees an anomaly that needs one.
                      With a nominal sim and no faults injected, every advisory comes back as
                      "Continue monitoring · no action required" — so this list stays empty by
                      design.
                      <br /><br />
                      To see actions fire: open <strong>Mission Control</strong>, inject a fault
                      via the Hydroponic Agriculture card (e.g. "inject LED outage"), or run
                      an Apollo Replay scenario from <strong>Chronology · Apollo Replay</strong>.
                      Decisions still flow into <strong>AI Console · Decisions</strong> regardless.
                    </>}
                    size="sm" />
      ) : (
        <ul className="flex-1 overflow-y-auto space-y-1">
          {[...filtered].reverse().map((e) => (
            <li
              key={e.id}
              className="rounded border border-ui-border/40 bg-ui-bg-1/40 px-2 py-1.5 text-xs"
            >
              <div className="flex items-center gap-2">
                <span
                  className={`px-1 py-0.5 rounded border text-[10px] uppercase ${
                    STATUS_COLOR[e.status]
                  }`}
                >
                  {e.status}
                </span>
                <span className="text-ui-text font-semibold">{e.agent}</span>
                <span className="text-ui-text">→</span>
                <span className="text-ui-accent">{e.action}</span>
                <span className="ml-auto font-mono text-[10px] text-ui-text-faint">
                  {fmtTs(e.ts)}
                </span>
              </div>
              {Object.keys(e.params).length > 0 && (
                <div className="mt-1 text-[10px] font-mono text-ui-text-dim">
                  {Object.entries(e.params)
                    .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
                    .join(' · ')}
                </div>
              )}
              {e.rationale && (
                <div className="mt-1 text-[10px] italic text-ui-text-faint">{e.rationale}</div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default AiActionsPanel;
