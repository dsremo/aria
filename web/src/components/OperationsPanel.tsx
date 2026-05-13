/**
 * Operations panel — three tools the operator uses constantly:
 *   1. Fuel tanks (per-tank + RCS xenon)
 *   2. Crew health (5 metrics: bone, VO2, SANS, vestibular, psych)
 *   3. Failure injector (8 scenarios — drill mode)
 */

import { useEffect, useState } from 'react';
import { Spinner } from './Spinner';
import {
  ariaApi,
  type CrewHealth,
  type FailureScenarios,
  type FuelInventory,
} from '../api/aria';

export function OperationsPanel() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 p-2 overflow-y-auto">
      <FuelPanel />
      <CrewHealthPanel />
      <FailureInjectorPanel />
    </div>
  );
}


/* ────────── Fuel ────────── */

function FuelPanel() {
  const [f, setF] = useState<FuelInventory | null>(null);

  useEffect(() => {
    const refresh = () => ariaApi.fuel().then(setF).catch(() => {});
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);

  if (!f) return <Card title="Fuel Inventory"><Spinner label="Loading…" /></Card>;

  const tte = f.summary.time_to_empty_main_yr;
  return (
    <Card title="Fuel Inventory">
      <div className="text-[10px] text-ui-text-dim mb-1">
        Main {f.summary.main_fill_pct.toFixed(2)} % full · burn {f.summary.main_burn_rate_kg_s.toFixed(1)} kg/s · RCS {f.summary.rcs_burn_rate_kg_s.toFixed(3)} kg/s
        {tte != null && tte < 1e6 && <> · TTE {tte.toFixed(2)} yr</>}
      </div>

      {(f.summary.alarm_low || f.summary.alarm_critical) && (
        <div className={`p-1 mb-1 rounded text-[10px] ${f.summary.alarm_critical ? 'bg-sev-crit/40 text-sev-crit border border-sev-crit' : 'bg-sev-warn/40 text-sev-warn border border-sev-warn'}`}>
          ⚠ {f.summary.alarm_critical ? 'TANK EMPTY' : 'Tank below 5 %'}
        </div>
      )}

      <div className="space-y-1.5">
        {f.tanks.map(tank => {
          const color = tank.fill_fraction > 0.5 ? 'bg-sev-ok'
                      : tank.fill_fraction > 0.1 ? 'bg-sev-warn' : 'bg-sev-crit';
          return (
            <div key={tank.tank_id}>
              <div className="flex justify-between text-[10px]">
                <span className="text-ui-text">{tank.label}</span>
                <span className="font-mono text-ui-text-dim">
                  {tank.fuel_type === 'D-He3'
                    ? `${(tank.contents_kg / 1e6).toFixed(3)} / ${(tank.capacity_kg / 1e6).toFixed(0)} kt`
                    : `${(tank.contents_kg / 1e3).toFixed(2)} / ${(tank.capacity_kg / 1e3).toFixed(2)} t`}
                  &nbsp;({(tank.fill_fraction * 100).toFixed(2)} %)
                </span>
              </div>
              <div className="h-1 bg-ui-bg-2 rounded overflow-hidden">
                <div className={`h-full ${color}`} style={{ width: `${tank.fill_fraction * 100}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}


/* ────────── Crew Health ────────── */

function CrewHealthPanel() {
  const [c, setC] = useState<CrewHealth | null>(null);

  useEffect(() => {
    const refresh = () => ariaApi.crewHealth().then(setC).catch(() => {});
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);

  if (!c) return <Card title="Crew Health (Aggregate)"><Spinner label="Loading…" /></Card>;

  const m = c.metrics;
  const rows: { label: string; value: number; unit: string; danger_below?: number; warn_below?: number; }[] = [
    { label: 'Bone density', value: m.bone_density_pct, unit: '%', warn_below: 80, danger_below: 70 },
    { label: 'VO₂max',       value: m.vo2max_pct,       unit: '%', warn_below: 80, danger_below: 65 },
    { label: 'Psych cohesion', value: m.psych_cohesion_pct, unit: '%', warn_below: 70, danger_below: 50 },
  ];
  const adverse: { label: string; value: number; unit: string; warn_above?: number; danger_above?: number; }[] = [
    { label: 'SANS prevalence',         value: m.sans_prevalence_pct,        unit: '%', warn_above: 5, danger_above: 20 },
    { label: 'Vestibular unadapted',    value: m.vestibular_unadapted_pct,   unit: '%' },
  ];

  return (
    <Card title="Crew Health (Aggregate)">
      <div className="text-[10px] text-ui-text-dim mb-2">
        {c.crew_size} crew · effective g = {c.effective_g.toFixed(2)} · {c.elapsed_yr.toFixed(2)} mission yr · {c.alarms_fired} alarms fired
      </div>
      <div className="space-y-1.5">
        {rows.map(r => {
          const color = r.danger_below != null && r.value < r.danger_below ? 'bg-sev-crit'
                      : r.warn_below   != null && r.value < r.warn_below   ? 'bg-sev-warn' : 'bg-sev-ok';
          return (
            <div key={r.label}>
              <div className="flex justify-between text-[10px]">
                <span className="text-ui-text">{r.label}</span>
                <span className="font-mono text-ui-text-dim">{r.value.toFixed(2)}{r.unit}</span>
              </div>
              <div className="h-1 bg-ui-bg-2 rounded overflow-hidden">
                <div className={`h-full ${color}`} style={{ width: `${Math.max(0, Math.min(100, r.value))}%` }} />
              </div>
            </div>
          );
        })}
        {adverse.map(r => {
          const color = r.danger_above != null && r.value > r.danger_above ? 'bg-sev-crit'
                      : r.warn_above   != null && r.value > r.warn_above   ? 'bg-sev-warn' : 'bg-sev-info';
          return (
            <div key={r.label}>
              <div className="flex justify-between text-[10px]">
                <span className="text-ui-text-dim">{r.label}</span>
                <span className="font-mono text-ui-text-faint">{r.value.toFixed(2)}{r.unit}</span>
              </div>
              <div className="h-1 bg-ui-bg-2 rounded overflow-hidden">
                <div className={`h-full ${color}`} style={{ width: `${Math.max(0, Math.min(100, r.value))}%` }} />
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-2 text-[9px] text-ui-text-faint italic">
        Sources: {c.sources.slice(0, 3).join(' · ')}
      </div>
    </Card>
  );
}


/* ────────── Failure Injector ────────── */

function FailureInjectorPanel() {
  const [list, setList] = useState<FailureScenarios | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [last, setLast] = useState<{ id: string; impact: string; severity: string } | null>(null);

  useEffect(() => {
    ariaApi.failureScenarios().then(setList).catch(console.error);
  }, []);

  const fire = async (id: string) => {
    setRunning(id);
    try {
      const r = await ariaApi.failureTrigger(id);
      setLast({ id: r.id, impact: r.impact, severity: r.severity });
    } catch (e) { console.error(e); }
    finally { setRunning(null); }
  };

  return (
    <Card title="Failure Injector (Operator Drills)">
      {!list && <div className="text-ui-text-dim"><Spinner label="Loading…" /></div>}
      {list && (
        <>
          <div className="text-[10px] text-ui-text-dim mb-2">
            {list.count} scenarios · click any to inject (alarms appear in Alarms + Event Log tabs)
          </div>
          <div className="space-y-1 max-h-56 overflow-y-auto">
            {list.scenarios.map(s => {
              const sevColor = s.severity === 'critical' ? 'border-sev-crit bg-sev-crit/20' : 'border-sev-warn bg-sev-warn/20';
              return (
                <button key={s.id}
                        onClick={() => fire(s.id)}
                        disabled={running != null}
                        className={`w-full text-left px-2 py-1 rounded border ${sevColor} hover:brightness-125 disabled:opacity-50 transition`}>
                  <div className="text-[11px] font-bold text-ui-text">{s.label}</div>
                  <div className="text-[9px] text-ui-text-dim">{s.description}</div>
                  <div className="text-[9px] text-ui-text-faint italic mt-0.5">↳ {s.impact}</div>
                </button>
              );
            })}
          </div>
          {last && (
            <div className="mt-2 p-1.5 rounded border border-ui-accent bg-ui-accent/20 text-[10px]">
              ✓ <strong>{last.id}</strong> injected ({last.severity}) — {last.impact}
            </div>
          )}
        </>
      )}
    </Card>
  );
}


/* ────────── Shared ────────── */

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="p-2 bg-ui-bg-1/40 border border-ui-border rounded">
      <div className="text-[10px] uppercase tracking-wider text-ui-accent font-bold mb-1">{title}</div>
      {children}
    </div>
  );
}
