/* R34 IncidentPanel — open / track / close incidents with full
 * audit-trace by incident_id.
 *
 * Layout: master/detail. Left column lists open + recent-closed
 * incidents, colour-coded by response_mode (AUTO_STABILIZE = red,
 * HOLD_AND_RCA = amber, HUMAN_DECIDE = blue, OBSERVE_ONLY = grey).
 * Right pane shows the full lifecycle of the selected incident
 * including the hash-chained audit entries pulled by /api/audit/trace.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { ariaApi, ariaSession, type AuditEntry, type IncidentRecord } from '../api/aria';

const PANEL_STYLE: React.CSSProperties = {
  background: 'rgb(var(--ui-bg-1))', color: 'rgb(var(--ui-text))',
  padding: 16, borderRadius: 8, marginBottom: 12,
  border: '1px solid rgb(var(--ui-border))',
};

const INPUT_STYLE: React.CSSProperties = {
  background: 'rgb(var(--ui-bg-2))', color: 'rgb(var(--ui-text))',
  border: '1px solid rgb(var(--ui-border))', borderRadius: 6,
  padding: 6, fontFamily: 'monospace', fontSize: 13,
  width: '100%',
};

const BTN_PRIMARY: React.CSSProperties = {
  background: 'rgb(var(--sev-ok))', color: '#ffffff', padding: '6px 12px',
  borderRadius: 6, border: 'none', cursor: 'pointer', marginRight: 6,
};

const BTN_NEUTRAL: React.CSSProperties = {
  background: 'rgb(var(--ui-bg-2))', color: 'rgb(var(--ui-text))', padding: '6px 12px',
  borderRadius: 6, border: '1px solid rgb(var(--ui-border))', cursor: 'pointer',
  marginRight: 6,
};

const BTN_DANGER: React.CSSProperties = {
  background: 'rgb(var(--sev-crit))', color: '#ffffff', padding: '6px 12px',
  borderRadius: 6, border: 'none', cursor: 'pointer', marginRight: 6,
};


function modeColor(mode: string): string {
  switch (mode) {
    case 'AUTO_STABILIZE': return 'rgb(var(--sev-crit))';
    case 'HOLD_AND_RCA':   return 'rgb(var(--sev-warn))';
    case 'HUMAN_DECIDE':   return 'rgb(var(--sev-info))';
    case 'OBSERVE_ONLY':   return 'rgb(var(--ui-text-dim))';
    default:               return 'rgb(var(--ui-text))';
  }
}


function severityColor(sev: string): string {
  switch (sev) {
    case 'emergency': return 'rgb(var(--sev-crit))';
    case 'critical':  return 'rgb(var(--sev-crit))';
    case 'warning':   return 'rgb(var(--sev-warn))';
    default:          return 'rgb(var(--ui-text-dim))';
  }
}


export function IncidentPanel(): React.ReactElement {
  const session = ariaSession.current();
  const [tab, setTab] = useState<'open' | 'closed'>('open');
  const [incidents, setIncidents] = useState<IncidentRecord[]>([]);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [selectedId, setSelectedId] = useState<string>('');
  const [chainStatus, setChainStatus] = useState<null | {
    entries: number; head_hash: string; chain_intact: boolean;
    first_break_seq: number | null; verify_ok: boolean;
  }>(null);
  const [error, setError] = useState<string>('');

  async function reload(): Promise<void> {
    setError('');
    try {
      const [list, status] = await Promise.all([
        ariaApi.incidentsList(tab),
        ariaApi.auditChainStatus().catch(() => null),
      ]);
      setIncidents(list.incidents);
      setStats(list.stats || {});
      setChainStatus(status as any);
      if (!selectedId && list.incidents[0]) {
        setSelectedId(list.incidents[0].incident_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => { reload(); }, [tab]);

  const selected = useMemo(
    () => incidents.find((x) => x.incident_id === selectedId) || null,
    [incidents, selectedId],
  );

  return (
    <div>
      <div style={PANEL_STYLE}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <h2 style={{ margin: 0 }}>Incidents</h2>
          <span style={{ fontSize: 12, color: 'rgb(var(--ui-text-dim))' }}>
            open: {stats['open'] ?? 0} · recent closed: {stats['closed_recent'] ?? 0}
          </span>
          <button onClick={reload} style={BTN_NEUTRAL}>Refresh</button>
          {chainStatus && (
            <span style={{
              fontSize: 12, color: chainStatus.chain_intact ? 'rgb(var(--sev-ok))' : 'rgb(var(--sev-crit))',
              fontFamily: 'monospace', marginLeft: 'auto',
            }}>
              audit chain {chainStatus.chain_intact ? 'OK' : 'BROKEN'} ·
              {' '}{chainStatus.entries} entries · head{' '}
              {chainStatus.head_hash.slice(0, 16)}…
            </span>
          )}
        </div>
        {error && <p style={{ color: 'rgb(var(--sev-crit))' }}>{error}</p>}
        {!session && (
          <p style={{ color: 'rgb(var(--ui-text-dim))' }}>
            Sign in via the <strong>Login</strong> tab to mutate incidents
            (read-only access available to anyone with telemetry.read_sensitive).
          </p>
        )}
        <div style={{ marginTop: 8 }}>
          <button
            onClick={() => setTab('open')}
            style={tab === 'open' ? BTN_PRIMARY : BTN_NEUTRAL}
          >Open</button>
          <button
            onClick={() => setTab('closed')}
            style={tab === 'closed' ? BTN_PRIMARY : BTN_NEUTRAL}
          >Recently closed</button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.6fr', gap: 12 }}>
        <div style={PANEL_STYLE}>
          <h3 style={{ marginTop: 0, fontSize: 14 }}>List ({incidents.length})</h3>
          {incidents.length === 0 && (
            <p style={{ color: 'rgb(var(--ui-text-dim))' }}>No {tab} incidents.</p>
          )}
          {incidents.map((inc) => (
            <div
              key={inc.incident_id}
              onClick={() => setSelectedId(inc.incident_id)}
              style={{
                padding: 8, marginBottom: 4, cursor: 'pointer',
                background: selectedId === inc.incident_id ? 'rgb(var(--ui-bg-2))' : 'transparent',
                borderLeft: `3px solid ${modeColor(inc.response_mode)}`,
                fontSize: 12,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontFamily: 'monospace', color: 'rgb(var(--ui-text-dim))' }}>
                  {inc.incident_id}
                </span>
                <span style={{ color: severityColor(inc.severity) }}>
                  {inc.severity}
                </span>
              </div>
              <div style={{ fontWeight: 600 }}>{inc.title}</div>
              <div style={{ color: 'rgb(var(--ui-text-dim))' }}>
                {inc.incident_class} · {inc.response_mode}
              </div>
            </div>
          ))}
        </div>

        <div style={PANEL_STYLE}>
          {!selected && (
            <p style={{ color: 'rgb(var(--ui-text-dim))' }}>Select an incident on the left.</p>
          )}
          {selected && <IncidentDetail incident={selected} onAction={reload} />}
        </div>
      </div>
    </div>
  );
}


// ─── Incident detail (right pane) ──────────────────────────────


function IncidentDetail(props: {
  incident: IncidentRecord;
  onAction: () => void;
}): React.ReactElement {
  const { incident, onAction } = props;
  const [trace, setTrace] = useState<AuditEntry[]>([]);
  const [traceErr, setTraceErr] = useState<string>('');
  const [draftNote, setDraftNote] = useState<string>('');
  const [draftFix, setDraftFix] = useState<string>('');
  const [draftRoot, setDraftRoot] = useState<string>('');
  const [draftClose, setDraftClose] = useState<string>('');

  async function loadTrace(): Promise<void> {
    setTraceErr('');
    try {
      const r = await ariaApi.auditTrace({
        incident_id: incident.incident_id, limit: 500,
      });
      setTrace(r.entries || []);
    } catch (err) {
      setTraceErr(err instanceof Error ? err.message : String(err));
    }
  }

  async function loadFlowTrace(): Promise<void> {
    /* R35: pull every event in the SAME flow (trace_id) — i.e. the
     * entire HTTP request / scheduler tick / bus chain that opened
     * this incident. Useful for diagnosing what happened upstream
     * of the incident's first audit entry. */
    if (!incident.trace_id) return;
    setTraceErr('');
    try {
      const r = await ariaApi.auditTrace({
        trace_id: incident.trace_id, limit: 500,
      });
      setTrace(r.entries || []);
    } catch (err) {
      setTraceErr(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => { loadTrace(); }, [incident.incident_id]);

  return (
    <div>
      <h3 style={{ marginTop: 0 }}>
        <span style={{ color: modeColor(incident.response_mode) }}>
          ● {incident.response_mode}
        </span>
        {' '}— {incident.title}
      </h3>
      <p style={{ fontSize: 13, color: 'rgb(var(--ui-text-dim))', fontFamily: 'monospace' }}>
        id: <strong>{incident.incident_id}</strong> · class: {incident.incident_class}
        {incident.controllability ? ` · ctl: ${incident.controllability}` : ''}
        {' '}· rule: {incident.rule_name} · status: {incident.status}
        {incident.trace_id && (
          <> · trace: <strong>{incident.trace_id}</strong></>
        )}
      </p>
      {incident.detail && Object.keys(incident.detail).length > 0 && (
        <pre style={{
          background: 'rgb(var(--ui-bg-2))', padding: 8, borderRadius: 6,
          fontSize: 12, overflowX: 'auto',
        }}>
{JSON.stringify(incident.detail, null, 2)}
        </pre>
      )}
      {incident.root_cause && (
        <p style={{ color: 'rgb(var(--sev-ok))' }}>
          <strong>Root cause:</strong> {incident.root_cause}
        </p>
      )}

      {incident.status === 'OPEN' && (
        <div>
          <h4 style={{ marginBottom: 4 }}>Add note</h4>
          <textarea
            rows={2} style={INPUT_STYLE}
            value={draftNote} onChange={(e) => setDraftNote(e.target.value)}
          />
          <button
            style={BTN_NEUTRAL}
            onClick={async () => {
              if (!draftNote.trim()) return;
              await ariaApi.incidentNote(incident.incident_id, draftNote.trim());
              setDraftNote(''); onAction();
            }}
          >Add note</button>

          <h4 style={{ marginTop: 14, marginBottom: 4 }}>Apply fix attempt</h4>
          <input
            style={INPUT_STYLE}
            placeholder="summary of fix"
            value={draftFix} onChange={(e) => setDraftFix(e.target.value)}
          />
          <button
            style={BTN_NEUTRAL}
            onClick={async () => {
              if (!draftFix.trim()) return;
              await ariaApi.incidentFix(incident.incident_id, draftFix.trim(), true);
              setDraftFix(''); onAction();
            }}
          >Record success</button>
          <button
            style={BTN_DANGER}
            onClick={async () => {
              if (!draftFix.trim()) return;
              await ariaApi.incidentFix(incident.incident_id, draftFix.trim(), false);
              setDraftFix(''); onAction();
            }}
          >Record failure</button>

          <h4 style={{ marginTop: 14, marginBottom: 4 }}>Set root cause</h4>
          <input
            style={INPUT_STYLE}
            value={draftRoot} onChange={(e) => setDraftRoot(e.target.value)}
            placeholder="root cause finding"
          />
          <button
            style={BTN_NEUTRAL}
            onClick={async () => {
              if (!draftRoot.trim()) return;
              await ariaApi.incidentRootCause(incident.incident_id, draftRoot.trim());
              setDraftRoot(''); onAction();
            }}
          >Set</button>

          <h4 style={{ marginTop: 14, marginBottom: 4 }}>Close</h4>
          <input
            style={INPUT_STYLE}
            value={draftClose} onChange={(e) => setDraftClose(e.target.value)}
            placeholder="resolution / defer reason"
          />
          <button
            style={BTN_PRIMARY}
            onClick={async () => {
              await ariaApi.incidentResolve(incident.incident_id, draftClose.trim());
              setDraftClose(''); onAction();
            }}
          >Resolve</button>
          <button
            style={BTN_NEUTRAL}
            onClick={async () => {
              await ariaApi.incidentDefer(incident.incident_id, draftClose.trim());
              setDraftClose(''); onAction();
            }}
          >Defer</button>
        </div>
      )}

      <h4 style={{ marginTop: 18 }}>
        Audit trace ({trace.length} entries)
        {' '}
        <button onClick={loadTrace} style={{ ...BTN_NEUTRAL, fontSize: 11 }}>
          incident only
        </button>
        {incident.trace_id && (
          <button onClick={loadFlowTrace} style={{ ...BTN_NEUTRAL, fontSize: 11 }}>
            full flow (trace_id)
          </button>
        )}
      </h4>
      {traceErr && <p style={{ color: 'rgb(var(--sev-crit))' }}>{traceErr}</p>}
      <div style={{ maxHeight: 360, overflowY: 'auto', fontSize: 12,
        background: 'rgb(var(--ui-bg-2))', padding: 8, borderRadius: 6 }}>
        {trace.length === 0 && (
          <span style={{ color: 'rgb(var(--ui-text-dim))' }}>No audit entries yet.</span>
        )}
        {trace.map((e) => (
          <div key={e.seq} style={{ borderBottom: '1px solid rgb(var(--ui-border-soft))', padding: '4px 0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontFamily: 'monospace', color: 'rgb(var(--ui-text-dim))' }}>
                #{e.seq} · {new Date(e.ts * 1000).toLocaleTimeString()}
              </span>
              <span style={{ color: severityColor(e.severity) }}>{e.severity}</span>
            </div>
            <div style={{ fontFamily: 'monospace' }}>
              <strong>{e.action}</strong> ({e.result})
              {' '}<span style={{ color: 'rgb(var(--ui-text-dim))' }}>· {e.identity || e.source}</span>
            </div>
            {Object.keys(e.details).length > 0 && (
              <div style={{ color: 'rgb(var(--ui-text-dim))', fontSize: 11, fontFamily: 'monospace' }}>
                {JSON.stringify(e.details).slice(0, 200)}
              </div>
            )}
            <div style={{ color: 'rgb(var(--ui-text-faint))', fontSize: 10, fontFamily: 'monospace' }}>
              h: {e.hash_value.slice(0, 16)}…
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
