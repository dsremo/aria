/**
 * FMEA Panel — Failure Modes and Effects Analysis worksheet.
 *
 * Editable RPN table (Severity × Occurrence × Detection) per MIL-STD-1629A,
 * with criticality classification, SPOF detection, and per-subsystem reliability
 * roll-up. Pre-loaded with a representative spacecraft FMEA seeded from
 * aria.safety.risk_assessment patterns.
 *
 * Pure client-side; no backend round-trip needed for FMEA editing.
 */

import { useMemo, useState } from 'react';

interface FailureMode {
  id: string;
  component: string;
  mode: string;
  effect: string;
  severity: number;       // 1-10
  occurrence: number;     // 1-10
  detection: number;      // 1-10
  mitigation: string;
}

interface SubsystemReliability {
  name: string;
  reliability: number;    // 0-1
}

const SEED_MODES: FailureMode[] = [
  { id: 'm1', component: 'RCS valve',     mode: 'stuck open',       effect: 'uncontrolled thrust → attitude loss', severity: 9, occurrence: 3, detection: 4, mitigation: 'redundant isolation valve' },
  { id: 'm2', component: 'Reactor coolant pump', mode: 'seizure',   effect: 'thermal runaway',                      severity: 10, occurrence: 2, detection: 3, mitigation: 'TMR pumps + scram interlock' },
  { id: 'm3', component: 'Solar array hinge',    mode: 'fail-deploy', effect: 'power deficit',                       severity: 8, occurrence: 2, detection: 2, mitigation: 'spring-loaded backup release' },
  { id: 'm4', component: 'Battery cell',         mode: 'thermal runaway', effect: 'pack fire',                       severity: 9, occurrence: 1, detection: 3, mitigation: 'cell-level fuses + isolation' },
  { id: 'm5', component: 'Star tracker',         mode: 'optic occulted', effect: 'attitude knowledge loss',          severity: 6, occurrence: 4, detection: 2, mitigation: 'dual head, sun-shade' },
  { id: 'm6', component: 'Comms HGA gimbal',     mode: 'stuck',          effect: 'no high-rate downlink',            severity: 5, occurrence: 3, detection: 2, mitigation: 'LGA fallback' },
  { id: 'm7', component: 'CO₂ scrubber bed',     mode: 'channeling',     effect: 'CO₂ buildup in habitat',           severity: 8, occurrence: 4, detection: 3, mitigation: 'redundant bed + Δp monitor' },
  { id: 'm8', component: 'Hull weld joint',      mode: 'fatigue crack',  effect: 'leak path',                        severity: 9, occurrence: 2, detection: 6, mitigation: 'periodic acoustic NDE' },
  { id: 'm9', component: 'GNSS receiver',        mode: 'GPS jamming',    effect: 'orbit determination degraded',     severity: 4, occurrence: 5, detection: 2, mitigation: 'IMU + range ranging fallback' },
  { id: 'm10', component: 'Reaction wheel',      mode: 'bearing wear',   effect: 'momentum saturation',              severity: 6, occurrence: 5, detection: 3, mitigation: '4-wheel pyramid + RCS dump' },
];

const SEED_SUBSYSTEMS: SubsystemReliability[] = [
  { name: 'Power',     reliability: 0.992 },
  { name: 'Thermal',   reliability: 0.995 },
  { name: 'GNC',       reliability: 0.988 },
  { name: 'Propulsion',reliability: 0.985 },
  { name: 'Comms',     reliability: 0.997 },
  { name: 'ECLSS',     reliability: 0.982 },
  { name: 'Structures',reliability: 0.998 },
];

function rpn(m: FailureMode): number {
  return m.severity * m.occurrence * m.detection;
}

function criticality(m: FailureMode): { label: string; color: string } {
  const r = rpn(m);
  if (r >= 200) return { label: 'CRITICAL', color: 'text-sev-crit bg-sev-crit/30' };
  if (r >= 100) return { label: 'MAJOR',    color: 'text-sev-warn bg-sev-warn/20' };
  if (r >= 50)  return { label: 'MODERATE', color: 'text-sev-warn bg-sev-warn/30' };
  return { label: 'MINOR', color: 'text-sev-ok bg-sev-ok/30' };
}

function isSpof(m: FailureMode): boolean {
  return m.severity >= 9 && m.detection >= 5;
}

function nomVoting(p: number, n: number, k: number): number {
  // C(n,i) p^i (1-p)^(n-i) for i = k..n.
  const fact = (x: number) => { let f = 1; for (let i = 2; i <= x; i++) f *= i; return f; };
  const comb = (a: number, b: number) => fact(a) / (fact(b) * fact(a - b));
  let total = 0;
  for (let i = k; i <= n; i++) {
    total += comb(n, i) * Math.pow(p, i) * Math.pow(1 - p, n - i);
  }
  return total;
}

export function FMEAPanel() {
  const [modes, setModes] = useState<FailureMode[]>(SEED_MODES);
  const [subs] = useState<SubsystemReliability[]>(SEED_SUBSYSTEMS);
  const [vote_p, setVoteP] = useState(0.99);
  const [vote_n, setVoteN] = useState(3);
  const [vote_k, setVoteK] = useState(2);

  const sorted = useMemo(
    () => [...modes].sort((a, b) => rpn(b) - rpn(a)),
    [modes]
  );

  const spofCount = useMemo(() => modes.filter(isSpof).length, [modes]);

  const stats = useMemo(() => {
    let critical = 0, major = 0, moderate = 0, minor = 0;
    for (const m of modes) {
      const c = criticality(m).label;
      if (c === 'CRITICAL') critical++;
      else if (c === 'MAJOR') major++;
      else if (c === 'MODERATE') moderate++;
      else minor++;
    }
    // R65-R5 (2026-04-24): Math.max(...[]) = -Infinity; seed with 0 so
    // an empty failure-modes list renders a sensible "max RPN: 0".
    return { critical, major, moderate, minor, max_rpn: Math.max(0, ...modes.map(rpn)) };
  }, [modes]);

  const sysReliability = useMemo(
    () => subs.reduce((acc, s) => acc * s.reliability, 1),
    [subs]
  );

  const spofs = useMemo(() => modes.filter(isSpof), [modes]);
  const tmrR = nomVoting(vote_p, vote_n, vote_k);

  function update(id: string, field: keyof FailureMode, value: any) {
    setModes((ms) => ms.map((m) => (m.id === id ? { ...m, [field]: value } : m)));
  }

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">FMEA — Failure Modes & Effects Analysis</h2>
        <p className="text-xs text-ui-text-dim">
          MIL-STD-1629A · RPN = Severity × Occurrence × Detection · NASA/SP-2010-576
        </p>
      </div>

      {/* Top-level summary */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-4">
        <Stat label="System reliability" value={`${(sysReliability * 100).toFixed(2)}%`} accent={sysReliability < 0.95 ? 'red' : 'green'} />
        <Stat label="Critical modes" value={stats.critical.toString()} accent={stats.critical > 0 ? 'red' : 'green'} />
        <Stat label="Major modes" value={stats.major.toString()} accent={stats.major > 0 ? 'orange' : 'green'} />
        <Stat label="SPOFs" value={spofs.length.toString()} accent={spofs.length > 0 ? 'red' : 'green'} />
        <Stat label="Max RPN" value={stats.max_rpn.toString()} />
      </div>

      {/* Subsystem reliability bars */}
      <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3 mb-4">
        <h3 className="text-sm font-semibold text-ui-accent mb-2">Subsystem Reliability (serial)</h3>
        <div className="space-y-1">
          {subs.map((s) => (
            <div key={s.name} className="flex items-center gap-2 text-xs">
              <div className="w-24 text-ui-text-dim">{s.name}</div>
              <div className="flex-1 h-3 bg-ui-bg-2 rounded overflow-hidden">
                <div
                  className={s.reliability >= 0.99 ? 'h-full bg-sev-ok' : s.reliability >= 0.95 ? 'h-full bg-sev-warn' : 'h-full bg-sev-crit'}
                  style={{ width: `${s.reliability * 100}%` }}
                />
              </div>
              <div className="w-20 text-right font-mono text-ui-text">
                {(s.reliability * 100).toFixed(2)}%
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* N-of-M voting calculator */}
      <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3 mb-4">
        <h3 className="text-sm font-semibold text-ui-accent mb-2">N-of-M Voting (TMR analyzer)</h3>
        <div className="flex flex-wrap gap-3 items-end text-xs">
          <label className="flex flex-col">
            <span className="text-ui-text-dim">per-unit p</span>
            <input
              type="number" min={0} max={1} step={0.001}
              value={vote_p}
              onChange={(e) => setVoteP(Number(e.target.value))}
              className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text w-24"
            />
          </label>
          <label className="flex flex-col">
            <span className="text-ui-text-dim">N units</span>
            <input
              type="number" min={1} max={9}
              value={vote_n}
              onChange={(e) => setVoteN(Math.max(1, Math.min(9, Number(e.target.value))))}
              className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text w-24"
            />
          </label>
          <label className="flex flex-col">
            <span className="text-ui-text-dim">K required</span>
            <input
              type="number" min={1} max={vote_n}
              value={vote_k}
              onChange={(e) => setVoteK(Math.max(1, Math.min(vote_n, Number(e.target.value))))}
              className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text w-24"
            />
          </label>
          <div className="bg-ui-bg-2 border border-ui-border rounded px-3 py-2">
            <div className="text-ui-text-dim">{vote_k}-of-{vote_n} reliability</div>
            <div className="font-mono text-sev-ok">{(tmrR * 100).toFixed(4)}%</div>
          </div>
        </div>
      </div>

      {/* FMEA table */}
      <div className="bg-ui-bg-1/60 border border-ui-border rounded overflow-hidden">
        <div className="flex items-center justify-between px-2 py-1 bg-ui-bg-2/60 border-b border-ui-border">
          <div className="text-[11px] text-ui-text-dim">
            {sorted.length} failure modes · sorted by RPN desc
            {spofCount > 0 && (
              <span className="ml-3 px-2 py-0.5 text-[10px] rounded border border-sev-crit bg-sev-crit/40 text-sev-crit">
                🔴 {spofCount} SPOF
              </span>
            )}
          </div>
          <div className="flex gap-1 text-[10px]">
            <button onClick={() => exportJson(sorted)}
                    className="px-2 py-0.5 rounded border border-ui-border-strong bg-ui-bg-1
                               hover:border-ui-accent hover:bg-ui-bg-2 text-ui-text">
              ⇩ export all (JSON)
            </button>
            <button onClick={() => exportCsv(sorted)}
                    className="px-2 py-0.5 rounded border border-ui-border-strong bg-ui-bg-1
                               hover:border-ui-accent hover:bg-ui-bg-2 text-ui-text">
              ⇩ CSV
            </button>
          </div>
        </div>
        <table className="w-full text-xs">
          <thead className="bg-ui-bg-2 text-ui-text-dim">
            <tr>
              <th className="text-left p-2">Component</th>
              <th className="text-left p-2">Mode</th>
              <th className="text-left p-2">Effect</th>
              <th className="p-2">S</th>
              <th className="p-2">O</th>
              <th className="p-2">D</th>
              <th className="p-2">RPN</th>
              <th className="p-2">Class</th>
              <th className="text-left p-2">Mitigation</th>
              <th className="p-2 w-8"></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((m) => {
              const c = criticality(m);
              return (
                <tr key={m.id} className="border-t border-ui-border group">
                  <td className="p-2 text-ui-text">{m.component}</td>
                  <td className="p-2 text-ui-text">{m.mode}</td>
                  <td className="p-2 text-ui-text-dim">{m.effect}</td>
                  <td className="p-1"><Spin v={m.severity}    on={(v) => update(m.id, 'severity',    v)} /></td>
                  <td className="p-1"><Spin v={m.occurrence}  on={(v) => update(m.id, 'occurrence',  v)} /></td>
                  <td className="p-1"><Spin v={m.detection}   on={(v) => update(m.id, 'detection',   v)} /></td>
                  <td className="p-2 text-center font-mono text-ui-text">{rpn(m)}</td>
                  <td className="p-2"><span className={`px-2 py-0.5 rounded ${c.color}`}>{c.label}</span></td>
                  <td className="p-2 text-ui-text-dim">{m.mitigation}{isSpof(m) && <span className="ml-2 text-sev-crit font-bold">SPOF</span>}</td>
                  <td className="p-1">
                    <button onClick={() => exportJson([m])}
                            title={`Export ${m.component} as JSON`}
                            className="opacity-0 group-hover:opacity-100 px-1 text-ui-text-dim hover:text-ui-accent">
                      ⇩
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-3 text-[11px] text-ui-text-dim space-y-1">
        <p>• SPOF flag = Severity ≥ 9 AND Detection ≥ 5 (high-impact, hard-to-detect failure).</p>
        <p>• System reliability assumes serial subsystems (any failure = mission loss). Add redundancy to lift the weakest link.</p>
      </div>
    </div>
  );
}

function exportJson(rows: FailureMode[]) {
  const enriched = rows.map((m) => ({
    ...m,
    rpn: rpn(m),
    class: criticality(m).label,
    spof: isSpof(m),
  }));
  const blob = new Blob([JSON.stringify(enriched, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const tag = rows.length === 1 ? rows[0].id : `all-${rows.length}`;
  a.download = `aria-fmea-${tag}-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function exportCsv(rows: FailureMode[]) {
  const esc = (s: string) => `"${s.replace(/"/g, '""')}"`;
  const header = 'id,component,mode,effect,severity,occurrence,detection,rpn,class,spof,mitigation';
  const lines = rows.map((m) => [
    m.id, esc(m.component), esc(m.mode), esc(m.effect),
    m.severity, m.occurrence, m.detection, rpn(m),
    criticality(m).label, isSpof(m) ? 'true' : 'false', esc(m.mitigation),
  ].join(','));
  const blob = new Blob([[header, ...lines].join('\n')], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `aria-fmea-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function Spin({ v, on }: { v: number; on: (n: number) => void }) {
  return (
    <input
      type="number"
      min={1}
      max={10}
      value={v}
      onChange={(e) => on(Math.max(1, Math.min(10, Number(e.target.value))))}
      className="bg-ui-bg-2 border border-ui-border-strong rounded px-1 py-0.5 text-ui-text w-12 text-center"
    />
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: 'red' | 'green' | 'orange' }) {
  const color =
    accent === 'red' ? 'text-sev-crit' :
    accent === 'orange' ? 'text-sev-warn' :
    accent === 'green' ? 'text-sev-ok' : 'text-ui-text';
  return (
    <div className="bg-ui-bg-1/60 border border-ui-border rounded p-3">
      <div className="text-xs text-ui-text-dim">{label}</div>
      <div className={`text-base font-mono ${color}`}>{value}</div>
    </div>
  );
}
