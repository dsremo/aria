/**
 * Safety Console — F-9 / F-12 / F-17 operator surface.
 *
 * Aggregates the failsafe layer into one view:
 *   - Kill-switch state (assert button, key-reset for ground tests)
 *   - Pending approval proposals (two-person rule, cooling-off)
 *   - Resource budgets (soft / hard caps, current consumption)
 *   - Constitution version banner
 *
 * Polls /api/safety/state every 3 s and /api/safety/proposals every 2 s.
 *
 * Maps to docs/FAILSAFE_ARCHITECTURE.md §F-9 / §F-12 / §F-17.
 */

import { useEffect, useState } from 'react';
import {
  ariaApi,
  type SafetyState,
  type SafetyProposal,
  type SafetyReplayReport,
  type SandbaggingReport,
  type BootManifestStatus,
} from '../api/aria';

export function SafetyConsole() {
  const [state, setState] = useState<SafetyState | null>(null);
  const [proposals, setProposals] = useState<SafetyProposal[]>([]);
  const [replay, setReplay] = useState<SafetyReplayReport | null>(null);
  const [sandbag, setSandbag] = useState<SandbaggingReport | null>(null);
  const [boot, setBoot] = useState<BootManifestStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [operatorId, setOperatorId] = useState<string>('');
  const [killReason, setKillReason] = useState<string>('');
  const [replayBusy, setReplayBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const [s, p, r, sb, bm] = await Promise.all([
          ariaApi.safetyState(),
          ariaApi.safetyProposals(),
          ariaApi.safetyReplay(),
          ariaApi.safetySandbagging(),
          ariaApi.safetyBootManifest(),
        ]);
        if (!cancelled) {
          setState(s);
          setProposals(p.proposals);
          setReplay(r.last_report);
          setSandbag(sb);
          setBoot(bm);
          setErr(null);
        }
      } catch (e) {
        if (!cancelled) setErr((e as Error).message);
      }
    };
    refresh();
    const id = setInterval(refresh, 3000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const onRunReplay = async () => {
    if (replayBusy) return;
    setReplayBusy(true);
    try {
      const r = await ariaApi.safetyReplayRun();
      setReplay(r);
    } catch (e) {
      alert('replay failed: ' + (e as Error).message);
    } finally {
      setReplayBusy(false);
    }
  };

  const onApprove = async (pid: string) => {
    const op = operatorId.trim();
    if (!op) {
      alert('enter your operator id first');
      return;
    }
    const ok = window.confirm(
      'Approve this action?\n\nYou are signing under the two-person rule. ' +
      'A second operator must also sign within 5 minutes for the action to fire ' +
      'after the cooling-off window.',
    );
    if (!ok) return;
    try {
      const r = await ariaApi.safetyApprove(pid, op);
      if (!r.ok) alert('approve failed: ' + (r.reason ?? 'unknown'));
    } catch (e) {
      alert('approve error: ' + (e as Error).message);
    }
  };

  const onVeto = async (pid: string) => {
    const op = operatorId.trim();
    if (!op) {
      alert('enter your operator id first');
      return;
    }
    const reason = window.prompt('Veto reason?');
    if (reason === null) return;
    try {
      const r = await ariaApi.safetyVeto(pid, op, reason);
      if (!r.ok) alert('veto failed: ' + (r.reason ?? 'unknown'));
    } catch (e) {
      alert('veto error: ' + (e as Error).message);
    }
  };

  const onAssertKill = async () => {
    const ok = window.confirm(
      '⚠ ASSERT KILL SWITCH ⚠\n\nThis stops every actuator command across the ' +
      'fleet until a physical-key reset clears it. Continue?',
    );
    if (!ok) return;
    try {
      await ariaApi.safetyKillAssert('console', killReason || 'operator console');
    } catch (e) {
      alert('kill assert failed: ' + (e as Error).message);
    }
  };

  const onKillReset = async () => {
    const sig = window.prompt(
      'Physical-key signature?\n\nIn production this is the HSM signature ' +
      'over a fresh nonce. For ground tests any non-empty string is accepted.',
    );
    if (!sig) return;
    try {
      const r = await ariaApi.safetyKillReset(sig);
      if (!r.ok) alert('reset rejected — switch was not asserted');
    } catch (e) {
      alert('reset error: ' + (e as Error).message);
    }
  };

  if (err) {
    return (
      <div className="p-3 text-sev-crit bg-sev-crit/30 border border-sev-crit/40 rounded">
        {err}
      </div>
    );
  }
  if (!state) return <div className="p-3 text-ui-text-dim text-xs">loading…</div>;

  const ks = state.kill_switch;

  return (
    <div className="h-full overflow-y-auto p-3 space-y-3 text-xs text-ui-text">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-ui-accent">Safety Console</h2>
          <p className="text-[10px] text-ui-text-dim">
            Constitution v{state.constitution_version} ·{' '}
            {state.pending_proposals} pending proposals
          </p>
        </div>
        <input
          placeholder="operator id"
          value={operatorId}
          onChange={(e) => setOperatorId(e.target.value)}
          className="bg-ui-bg-0 border border-ui-border rounded px-2 py-1 text-xs"
        />
      </div>

      {/* Kill switch banner */}
      <div
        className={`p-3 rounded border ${
          ks.asserted
            ? 'bg-sev-crit/40 border-sev-crit/60 text-sev-crit'
            : 'bg-sev-ok/30 border-sev-ok/40 text-sev-ok'
        }`}
      >
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-widest font-semibold">
              Kill switch
            </div>
            <div className="text-base">
              {ks.asserted ? 'ASSERTED' : 'CLEAR'}
            </div>
            {ks.asserted && (
              <div className="text-[10px] text-sev-crit mt-1">
                by {ks.asserted_by} — {ks.reason}
              </div>
            )}
          </div>
          {ks.asserted ? (
            <button
              type="button"
              onClick={onKillReset}
              className="px-3 py-1.5 rounded border border-sev-warn/60 bg-sev-warn/40 text-sev-warn hover:bg-sev-warn/50"
            >
              Physical-key reset
            </button>
          ) : (
            <div className="flex gap-2">
              <input
                placeholder="reason"
                value={killReason}
                onChange={(e) => setKillReason(e.target.value)}
                className="bg-ui-bg-0 border border-ui-border rounded px-2 py-1 text-xs"
              />
              <button
                type="button"
                onClick={onAssertKill}
                className="px-3 py-1.5 rounded border border-sev-crit/60 bg-sev-crit/40 text-sev-crit hover:bg-sev-crit/50"
              >
                Assert kill switch
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Pending proposals */}
      <div>
        <div className="text-[10px] uppercase tracking-widest text-ui-accent mb-1">
          Pending approvals ({proposals.length})
        </div>
        {proposals.length === 0 ? (
          <div className="text-ui-text-faint">No pending proposals.</div>
        ) : (
          <ul className="space-y-2">
            {proposals.map((p) => (
              <li
                key={p.proposal_id}
                className="rounded border border-ui-border/40 bg-ui-bg-1/40 p-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="font-semibold text-ui-text">
                      {p.action} <span className="text-ui-text-faint">({p.proposer})</span>
                    </div>
                    <div className="text-[10px] text-ui-text-dim">
                      {p.reason}
                    </div>
                    <div className="text-[10px] text-ui-text-faint mt-1">
                      {p.approvals_count}/{p.required_signers} signed ·{' '}
                      cool-off {p.cooling_off_s}s · undo {p.undo_window_s}s ·{' '}
                      <span className="font-mono">{p.state}</span>
                    </div>
                  </div>
                  <div className="flex flex-col gap-1">
                    <button
                      type="button"
                      onClick={() => onApprove(p.proposal_id)}
                      disabled={p.state !== 'pending'}
                      className="px-2 py-1 rounded text-[11px] border border-sev-ok/40 text-sev-ok hover:bg-sev-ok/40 disabled:opacity-40"
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      onClick={() => onVeto(p.proposal_id)}
                      disabled={!['pending', 'ready'].includes(p.state)}
                      className="px-2 py-1 rounded text-[11px] border border-sev-crit/40 text-sev-crit hover:bg-sev-crit/40 disabled:opacity-40"
                    >
                      Veto
                    </button>
                  </div>
                </div>
                <div className="mt-1 font-mono text-[10px] text-ui-text-faint">
                  {Object.entries(p.params).map(([k, v]) =>
                    `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`,
                  ).join(' · ')}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* F-13 Continuous safety-replay */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <div className="text-[10px] uppercase tracking-widest text-ui-accent">
            Safety replay (F-13)
          </div>
          <button
            type="button"
            onClick={onRunReplay}
            disabled={replayBusy}
            className="text-[10px] px-2 py-0.5 rounded border border-ui-accent/40 text-ui-accent hover:bg-ui-accent/40 disabled:opacity-40"
          >
            {replayBusy ? 'running…' : 'run now'}
          </button>
        </div>
        {!replay ? (
          <div className="text-ui-text-faint text-[11px]">No replay run yet — scheduler runs every 6 h.</div>
        ) : (
          <div
            className={`rounded border p-2 ${
              replay.drift_alarm
                ? 'border-sev-crit/60 bg-sev-crit/40'
                : 'border-sev-ok/40 bg-sev-ok/20'
            }`}
          >
            <div className="flex justify-between text-[11px]">
              <span>{replay.n_pass}/{replay.n_total} pass</span>
              <span className={replay.drift_alarm ? 'text-sev-crit' : 'text-sev-ok'}>
                {replay.drift_alarm ? '⚠ DRIFT ALARM' : 'green'} · {replay.fail_pct.toFixed(2)} %
              </span>
            </div>
            {replay.failures.length > 0 && (
              <ul className="mt-1 space-y-0.5 text-[10px] text-sev-crit">
                {replay.failures.slice(0, 5).map((f) => (
                  <li key={f.scenario_id}>
                    <span className="font-mono">{f.scenario_id}</span>: expected{' '}
                    <span className="text-sev-ok">{f.expected}</span>, got{' '}
                    <span className="text-sev-crit">{f.got}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* F-11 Sandbagging detector */}
      <div>
        <div className="text-[10px] uppercase tracking-widest text-ui-accent mb-1">
          Sandbagging detector (F-11)
        </div>
        {!sandbag ? (
          <div className="text-ui-text-faint text-[11px]">no data</div>
        ) : (
          <div
            className={`rounded border p-2 ${
              sandbag.suspect
                ? 'border-sev-warn/60 bg-sev-warn/40'
                : 'border-ui-border-strong/40 bg-ui-bg-1/40'
            }`}
          >
            <div className="flex justify-between text-[11px]">
              <span>
                eval n={sandbag.n_eval} · prod n={sandbag.n_prod}
              </span>
              <span className={sandbag.suspect ? 'text-sev-warn' : 'text-sev-ok'}>
                {sandbag.suspect ? '⚠ SUSPECT' : 'nominal'}
              </span>
            </div>
            <div className="mt-1 text-[10px] text-ui-text-dim grid grid-cols-2 gap-x-4">
              <div>refusal-gap</div>
              <div className="text-right font-mono">{sandbag.refusal_rate_gap.toFixed(3)}</div>
              <div>length-z</div>
              <div className="text-right font-mono">{sandbag.length_z.toFixed(2)}</div>
              <div>action-overlap</div>
              <div className="text-right font-mono">{sandbag.action_overlap_pct.toFixed(0)} %</div>
            </div>
            {sandbag.suspect && (
              <div className="mt-1 text-[10px] text-sev-warn">{sandbag.reason}</div>
            )}
          </div>
        )}
      </div>

      {/* F-18 Boot manifest */}
      <div>
        <div className="text-[10px] uppercase tracking-widest text-ui-accent mb-1">
          Boot manifest (F-18)
        </div>
        {!boot ? (
          <div className="text-ui-text-faint text-[11px]">no data</div>
        ) : (
          <div
            className={`rounded border p-2 text-[11px] ${
              boot.ok
                ? 'border-sev-ok/40 bg-sev-ok/20 text-sev-ok'
                : 'border-sev-crit/60 bg-sev-crit/40 text-sev-crit'
            }`}
          >
            <div className="flex justify-between">
              <span>{boot.manifest_present ? 'manifest present' : 'manifest missing (dev path)'}</span>
              <span>{boot.ok ? 'ok' : 'tamper detected'}</span>
            </div>
            {boot.error && <div className="mt-1 text-[10px]">{boot.error}</div>}
          </div>
        )}
      </div>

      {/* Resource budgets */}
      <div>
        <div className="text-[10px] uppercase tracking-widest text-ui-accent mb-1">
          Resource budgets
        </div>
        <ul className="space-y-1">
          {Object.entries(state.budgets).map(([res, b]) => {
            const pct = b.pct_of_hard;
            const colour = pct > 80 ? 'bg-sev-crit' : pct > 50 ? 'bg-sev-warn' : 'bg-sev-ok';
            return (
              <li
                key={res}
                className="rounded border border-ui-border/40 bg-ui-bg-1/40 p-2"
              >
                <div className="flex justify-between text-[11px]">
                  <span>{res}</span>
                  <span className="font-mono">
                    {b.current.toFixed(1)} / {b.hard_cap.toFixed(0)} {b.unit}
                  </span>
                </div>
                <div className="h-1.5 bg-ui-bg-3/40 rounded mt-1 overflow-hidden">
                  <div
                    className={`h-full ${colour}`}
                    style={{ width: `${Math.min(100, pct)}%` }}
                  />
                </div>
                <div className="text-[10px] text-ui-text-faint mt-0.5">
                  soft {b.soft_cap.toFixed(0)} {b.unit}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

export default SafetyConsole;
