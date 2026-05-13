/**
 * Captain's Log — combined panel showing:
 *   1. Crew schedule (3 bands, who's on duty / sleeping / off)
 *   2. Repair queue (3D printer feedstock + active repair tasks)
 *   3. Narrative log (event-bus → human-readable mission timeline)
 */

import { useEffect, useState } from 'react';
import { Spinner } from './Spinner';
import {
  ariaApi,
  type CrewScheduleState,
  type NarrativeLogState,
  type RepairQueueState,
} from '../api/aria';

export function CaptainsLogPanel() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-2 p-2 overflow-y-auto h-full">
      <CrewScheduleCard />
      <RepairQueueCard />
      <div className="lg:col-span-2">
        <NarrativeCard />
      </div>
    </div>
  );
}


/* ────────── Crew schedule ────────── */

function CrewScheduleCard() {
  const [s, setS] = useState<CrewScheduleState | null>(null);
  useEffect(() => {
    const refresh = () => ariaApi.crewSchedule().then(setS).catch(() => {});
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);

  if (!s) return <Card title="Crew Schedule"><Spinner label="Loading…" /></Card>;

  const overtime = async (b: string) => setS(await ariaApi.crewOvertime(b, 4));

  return (
    <Card title={`Crew Schedule · Local ${formatHr(s.local_clock_hr)}`}>
      <div className="text-[10px] text-ui-text-dim mb-2">
        on duty: <span className="text-sev-ok font-mono">{s.on_duty_now}</span> ·
        sleeping: <span className="text-sev-info font-mono">{s.sleeping_now}</span> ·
        recreation: <span className="text-sev-warn font-mono">{s.recreation_now}</span>
        &nbsp;· avg productivity <span className="text-ui-accent font-mono">{(s.avg_productivity * 100).toFixed(1)}%</span>
      </div>
      <div className="space-y-1">
        {s.bands.map(b => {
          const status = b.is_on_duty ? 'ON DUTY' : b.is_sleeping ? 'SLEEPING' : 'RECREATION';
          const color  = b.is_on_duty ? 'text-sev-ok' : b.is_sleeping ? 'text-sev-info' : 'text-sev-warn';
          return (
            <div key={b.band_id} className="text-[11px]">
              <div className="flex justify-between items-baseline">
                <span className="text-ui-text">
                  Band <strong>{b.band_id}</strong> ({b.crew_count} crew, starts {formatHr(b.on_duty_start_hr)})
                  &nbsp;· <span className={color}>{status}</span>
                </span>
                <span className="text-ui-text-faint font-mono text-[9px]">
                  prod {(b.productivity_index * 100).toFixed(0)}% · debt {b.sleep_debt_hr.toFixed(1)} hr
                </span>
              </div>
              <div className="h-1 bg-ui-bg-2 rounded overflow-hidden">
                <div className={`h-full ${b.productivity_index > 0.7 ? 'bg-sev-ok' : b.productivity_index > 0.4 ? 'bg-sev-warn' : 'bg-sev-crit'}`}
                     style={{ width: `${b.productivity_index * 100}%` }} />
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex gap-1">
        {s.bands.map(b => (
          <button key={b.band_id}
                  onClick={() => overtime(b.band_id)}
                  className="flex-1 px-1 py-0.5 text-[10px] rounded border border-sev-warn bg-sev-warn/30 hover:bg-sev-warn/40">
            +4 hr Band {b.band_id}
          </button>
        ))}
      </div>
      <div className="text-[9px] text-ui-text-faint mt-1">
        Total work delivered: {(s.total_work_hours_delivered).toFixed(0)} crew-hr · used for repairs: {s.total_repair_hours_used.toFixed(0)} crew-hr
      </div>
    </Card>
  );
}


/* ────────── Repair queue ────────── */

function RepairQueueCard() {
  const [r, setR] = useState<RepairQueueState | null>(null);
  useEffect(() => {
    const refresh = () => ariaApi.repairQueue().then(setR).catch(() => {});
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);

  if (!r) return <Card title="3D Printer + Repair Queue"><Spinner label="Loading…" /></Card>;

  const refill = async () => setR((await ariaApi.repairRefill(2000)).state);
  const cancel = async (id: string) => { await ariaApi.repairCancel(id); setR(await ariaApi.repairQueue()); };

  return (
    <Card title="3D Printer + Repair Queue">
      <div className="text-[10px] text-ui-text-dim mb-1">
        Feedstock {r.feedstock_kg.toFixed(1)} / {r.feedstock_capacity_kg.toFixed(0)} kg ({r.feedstock_pct.toFixed(1)}%)
        · {r.stats.completed} done / {r.stats.failed} failed
      </div>
      <div className="h-1 bg-ui-bg-2 rounded overflow-hidden mb-2">
        <div className={`h-full ${r.feedstock_pct > 50 ? 'bg-sev-ok' : r.feedstock_pct > 20 ? 'bg-sev-warn' : 'bg-sev-crit'}`}
             style={{ width: `${r.feedstock_pct}%` }} />
      </div>
      <button onClick={refill}
              className="px-2 py-0.5 mb-2 text-[10px] rounded border border-ui-accent bg-ui-accent/30 hover:bg-ui-accent/50">
        + Refill 2 t feedstock
      </button>
      <div className="space-y-0.5 max-h-44 overflow-y-auto">
        {r.tasks.length === 0 && (
          <div className="text-[10px] text-ui-text-faint italic">
            No active repair tasks. Hull damage will auto-create them.
          </div>
        )}
        {r.tasks.slice().reverse().map(t => {
          const sevColor = t.status === 'complete' ? 'text-sev-ok'
                        : t.status === 'failed'   ? 'text-sev-crit'
                        : t.status === 'printing' ? 'text-ui-accent'
                        : t.status === 'installing' ? 'text-sev-warn'
                        :                              'text-ui-text-dim';
          return (
            <div key={t.task_id} className="text-[10px]">
              <div className="flex justify-between gap-1">
                <span className={sevColor + ' uppercase text-[8px]'}>{t.status}</span>
                <span className="flex-1 truncate text-ui-text">{t.label}</span>
                <span className="text-ui-text-faint text-[9px]">{t.feedstock_kg.toFixed(1)} kg · {t.crew_hours.toFixed(1)} hr</span>
                {(t.status === 'pending' || t.status === 'printing') && (
                  <button onClick={() => cancel(t.task_id)}
                          className="text-sev-crit text-[9px] hover:underline">cancel</button>
                )}
              </div>
              {t.status !== 'complete' && t.status !== 'failed' && (
                <div className="h-0.5 bg-ui-bg-2 rounded overflow-hidden">
                  <div className="h-full bg-ui-accent" style={{ width: `${t.progress_pct}%` }} />
                </div>
              )}
              {t.note && <div className="text-[9px] italic text-sev-warn">{t.note}</div>}
            </div>
          );
        })}
      </div>
    </Card>
  );
}


/* ────────── Narrative log ────────── */

function NarrativeCard() {
  const [n, setN] = useState<NarrativeLogState | null>(null);
  const [note, setNote] = useState('');
  // R65 (2026-04-24) C-5: replaced native alert() with an inline status
  // banner — alerts are modal, browser-native, unstyled, and break the
  // rest of the UI.  The banner auto-clears after 4 s.
  const [exportErr, setExportErr] = useState<string | null>(null);

  useEffect(() => {
    const refresh = () => ariaApi.narrative().then(setN).catch(() => {});
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (!exportErr) return;
    const t = setTimeout(() => setExportErr(null), 4000);
    return () => clearTimeout(t);
  }, [exportErr]);

  if (!n) return <Card title="Captain's Log"><Spinner label="Loading…" /></Card>;

  const addNote = async () => {
    if (!note.trim()) return;
    await ariaApi.narrativeNote(note);
    setNote('');
    setN(await ariaApi.narrative());
  };
  const clearAll = async () => { await ariaApi.narrativeClear(); setN(await ariaApi.narrative()); };
  const downloadText = async () => {
    try {
      const r = await fetch('/api/narrative/text?limit=1000');
      if (!r.ok) { setExportErr(`Export failed: HTTP ${r.status}`); return; }
      const text = await r.text();
      const blob = new Blob([text], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `aria-captains-log-${new Date().toISOString().replace(/[:.]/g,'-')}.txt`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setExportErr(`Export failed: ${e?.message ?? e}`);
    }
  };

  return (
    <Card title={`Captain's Log · ${n.entry_count} entries`}>
      {exportErr && (
        <div className="mb-2 px-2 py-1 text-[11px] rounded border border-sev-crit bg-sev-crit/30 text-sev-crit">
          {exportErr}
        </div>
      )}
      <div className="flex gap-1 mb-2">
        <input value={note} onChange={e => setNote(e.target.value)}
               onKeyDown={e => { if (e.key === 'Enter') addNote(); }}
               placeholder="Add operator note…"
               className="flex-1 px-2 py-0.5 bg-ui-bg-2 border border-ui-border rounded text-xs" />
        <button onClick={addNote}
                className="px-2 py-0.5 text-[10px] rounded border border-ui-accent bg-ui-accent/30 hover:bg-ui-accent/50">
          + Note
        </button>
        <button onClick={downloadText}
                className="px-2 py-0.5 text-[10px] rounded border border-sev-info bg-sev-info/30 hover:bg-sev-info/50">
          📄 Export
        </button>
        <button onClick={clearAll}
                className="px-2 py-0.5 text-[10px] rounded border border-sev-crit bg-sev-crit/30 hover:bg-sev-crit/50">
          Clear
        </button>
      </div>
      <div className="font-mono text-[11px] leading-relaxed bg-ui-bg-1/40 border border-ui-border rounded p-2 max-h-96 overflow-y-auto">
        {n.entries.length === 0 && (
          <div className="text-ui-text-faint italic">
            Captain's log empty. Press Play, schedule events, or add an operator note above.
          </div>
        )}
        {n.entries.slice().reverse().map((e, i) => {
          const sevColor = e.severity === 'critical' ? 'text-sev-crit'
                        : e.severity === 'warning'  ? 'text-sev-warn'
                        : 'text-ui-text';
          // Key blends sim_time + text prefix so reordering a reversed list
          // doesn't reuse stale DOM rows from different entries.
          const key = `${e.sim_time_yr}-${i}-${e.text.slice(0, 24)}`;
          return (
            <div key={key} className={sevColor}>
              <span className="text-ui-text-faint">Year {e.sim_time_yr.toFixed(2).padStart(7, ' ')}</span>{' '}
              <span>{e.icon}</span>{' '}
              {e.text}
            </div>
          );
        })}
      </div>
    </Card>
  );
}


/* ────────── Shared ────────── */

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="p-2 bg-ui-bg-1/40 border border-ui-border rounded flex flex-col">
      <div className="text-[10px] uppercase tracking-wider text-ui-accent font-bold mb-1">{title}</div>
      {children}
    </div>
  );
}

function formatHr(h: number): string {
  const hr = Math.floor(h);
  const mn = Math.floor((h - hr) * 60);
  return `${hr.toString().padStart(2, '0')}:${mn.toString().padStart(2, '0')}`;
}
