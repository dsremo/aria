/**
 * Live-polling diagnostic panels for:
 *   * Reactor (derived from mission phase + part_inspector — reactor_engine)
 *   * Avionics SEU / ECC / TMR state
 *   * ECLSS trace contaminants (4 species with SMAC margin bars)
 *   * Tick engine controls
 *
 * Every panel polls its own endpoint every 2 s.
 */

import { useEffect, useState } from 'react';
import {
  ariaApi,
  type BearingState,
  type ContaminantsStatus,
  type PartSnapshot,
  type PowerBudget,
  type PropThermalState,
  type SEUStatus,
  type TickStatus,
} from '../api/aria';

export function SubsystemPanels() {
  return (
    <div className="grid grid-cols-2 gap-2 p-2 overflow-y-auto">
      <TickEnginePanel />
      <ReactorPanel />
      <AvionicsSEUPanel />
      <EclssContaminantsPanel />
      <BearingPanel />
      <PropulsionThermalPanel />
      <PowerBudgetPanel />
    </div>
  );
}


/* ────────── Bearing dynamics ────────── */

function BearingPanel() {
  const [b, setB] = useState<BearingState | null>(null);
  const refresh = () => ariaApi.bearing().then(setB).catch(() => {});
  useEffect(() => { refresh(); const t = setInterval(refresh, 2000); return () => clearInterval(t); }, []);

  if (!b) return <Panel title="Habitat Ring Bearing">Loading…</Panel>;

  const trip    = async () => setB(await ariaApi.bearingTrip('operator drill'));
  const restore = async () => setB(await ariaApi.bearingRestore());

  const modeColor = b.mode === 'magnetic' ? 'text-sev-ok'
                  : b.mode === 'roller'   ? 'text-sev-warn'
                  :                          'text-sev-crit';

  return (
    <Panel title="Habitat Ring Bearing">
      <div className="grid grid-cols-2 gap-1 text-[10px]">
        <Metric label="Mode" value={b.mode.toUpperCase()} color={modeColor} />
        <Metric label="Maglev power" value={b.maglev.powered ? 'ON' : 'OFF'} color={b.maglev.powered ? 'text-sev-ok' : 'text-sev-crit'} />
        <Metric label="Static load" value={`${(b.config.static_load_n / 1e6).toFixed(1)} MN`} />
        <Metric label="Loading" value={`${(b.config.loading_factor * 100).toFixed(1)}%`} />
        <Metric label="Coil temp" value={`${b.maglev.winding_temp_k.toFixed(0)} K`} />
        <Metric label="Powered" value={`${b.maglev.total_powered_hours.toFixed(0)} hr`} />
      </div>
      {b.mode === 'roller' && (
        <div className="mt-2 p-1 bg-sev-warn/40 border border-sev-warn rounded text-[10px]">
          <div className="text-sev-warn font-semibold">⚠ MAGLEV TRIPPED — on roller backup</div>
          <div className="text-ui-text-dim">L₁₀ life consumed: {b.roller.life_consumed_pct.toFixed(2)}% · EHL film {b.roller.lube_film_um.toFixed(2)} µm</div>
        </div>
      )}
      <div className="text-[10px] text-ui-text-faint mt-1">Trips: {b.stats.total_trips} · Alarms: {b.stats.total_alarms}</div>
      <div className="flex gap-1 mt-2">
        <button onClick={trip} className="flex-1 px-1 py-0.5 text-[10px] rounded border border-sev-warn bg-sev-warn/30 hover:bg-sev-warn/40">Force Trip</button>
        <button onClick={restore} className="flex-1 px-1 py-0.5 text-[10px] rounded border border-sev-ok bg-sev-ok/30 hover:bg-sev-ok/40">Restore Maglev</button>
      </div>
    </Panel>
  );
}


/* ────────── Propulsion thermal feedback ────────── */

function PropulsionThermalPanel() {
  const [pt, setPt] = useState<PropThermalState | null>(null);
  const refresh = () => ariaApi.propulsionThermal().then(setPt).catch(() => {});
  useEffect(() => { refresh(); const t = setInterval(refresh, 2000); return () => clearInterval(t); }, []);

  if (!pt) return <Panel title="Propulsion Thermal Feedback">Loading…</Panel>;

  const throttling = pt.thrust.throttle_active;
  const marginColor = pt.thermal.margin_w > 5e7 ? 'text-sev-ok' : pt.thermal.margin_w > 0 ? 'text-sev-warn' : 'text-sev-crit';
  const tempColor = pt.thermal.hull_aft_cap_temp_k < pt.thermal.hull_temp_limit_k * 0.75 ? 'text-sev-ok'
                 : pt.thermal.hull_aft_cap_temp_k < pt.thermal.hull_temp_limit_k        ? 'text-sev-warn'
                 :                                                                        'text-sev-crit';

  return (
    <Panel title="Propulsion Thermal Feedback">
      <div className="grid grid-cols-2 gap-1 text-[10px]">
        <Metric label="Thrust requested" value={`${(pt.thrust.requested_frac * 100).toFixed(0)}%`} />
        <Metric label="Thrust actual" value={`${(pt.thrust.actual_frac * 100).toFixed(0)}%`} color={throttling ? 'text-sev-warn' : undefined} />
        <Metric label="Plume back-rad" value={`${(pt.thermal.back_radiated_w / 1e6).toFixed(2)} MW`} />
        <Metric label="Radiator margin" value={`${(pt.thermal.margin_w / 1e6).toFixed(1)} MW`} color={marginColor} />
        <Metric label="Hull aft cap T" value={`${pt.thermal.hull_aft_cap_temp_k.toFixed(0)} K`} color={tempColor} />
        <Metric label="View factor" value={`${(pt.config.nozzle_to_hull_view_factor * 100).toFixed(0)}%`} />
      </div>
      {throttling && (
        <div className="mt-2 p-1 bg-sev-warn/40 border border-sev-warn rounded text-[10px]">
          <div className="text-sev-warn font-semibold">⚠ AUTO-THROTTLING ACTIVE — thermal margin negative at requested thrust</div>
        </div>
      )}
      <div className="text-[9px] text-ui-text-faint mt-1 italic">
        Plasma deflection eff: {(pt.config.plasma_deflection_efficiency * 100).toFixed(1)}% · {pt.stats.total_throttle_events} throttle events · auto-throttle: {pt.config.auto_throttle_enabled ? 'ON' : 'OFF'}
      </div>
    </Panel>
  );
}


/* ────────── Power budget ────────── */

function PowerBudgetPanel() {
  const [pb, setPb] = useState<PowerBudget | null>(null);
  const refresh = () => ariaApi.powerBudget().then(setPb).catch(() => {});
  useEffect(() => { refresh(); const t = setInterval(refresh, 2000); return () => clearInterval(t); }, []);

  if (!pb) return <Panel title="Power Budget">Loading…</Panel>;

  const marginColor = pb.summary.margin_pct > 30 ? 'bg-sev-ok'
                    : pb.summary.margin_pct > 5  ? 'bg-sev-warn' : 'bg-sev-crit';

  return (
    <Panel title="Power Budget · 20.4 kV HVDC">
      <div className="text-[10px] text-ui-text-dim mb-1">
        Reactor → bus: {(pb.summary.peak_electric_w / 1e6).toFixed(1)} MWe peak ({(pb.summary.thermal_to_electric_eff * 100).toFixed(0)}% Brayton)
      </div>
      <div className="flex justify-between text-[10px] mb-0.5">
        <span>{(pb.summary.allocated_w / 1e6).toFixed(2)} / {(pb.summary.available_w / 1e6).toFixed(2)} MW allocated</span>
        <span>margin {pb.summary.margin_pct.toFixed(1)}%</span>
      </div>
      <div className="h-2 bg-ui-bg-2 rounded overflow-hidden mb-2">
        {/* R65-R5 (2026-04-24): clamp negative (margin > 100 %) too —
            was only clamped at the high end, so a large-overhead case
            would render a negative width string and disappear. */}
        <div className={`h-full ${marginColor} transition-all`}
             style={{ width: `${Math.max(0, Math.min(100, 100 - pb.summary.margin_pct))}%` }} />
      </div>

      {/* per-subsystem table */}
      <div className="space-y-0.5 max-h-44 overflow-y-auto">
        {pb.subsystems.filter(s => s.requested_w > 0).map(s => {
          const pct = s.requested_w > 0 ? 100 * s.allocated_w / s.requested_w : 100;
          const color = s.shed ? 'bg-sev-crit' : s.priority >= 80 ? 'bg-ui-accent' : 'bg-sev-info';
          return (
            <div key={s.name} className="text-[10px]">
              <div className="flex justify-between gap-2">
                <span className="text-ui-text truncate flex-1">
                  <span className="text-ui-text-faint text-[8px]">P{s.priority}</span> {s.name}
                </span>
                <span className={`font-mono ${s.shed ? 'text-sev-crit' : 'text-ui-text-dim'}`}>
                  {(s.allocated_w / 1e3).toFixed(1)} / {(s.requested_w / 1e3).toFixed(1)} kW
                </span>
              </div>
              <div className="h-0.5 bg-ui-bg-2 rounded overflow-hidden">
                <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
              </div>
            </div>
          );
        })}
      </div>

      {pb.stats.total_shed_events > 0 && (
        <div className="mt-2 text-[9px] text-sev-warn">
          ⚠ {pb.stats.total_shed_events} load-shed events · {(pb.stats.cumulative_shed_wh / 1000).toFixed(2)} MWh shed cumulative
        </div>
      )}
    </Panel>
  );
}


/* ────────── Tick engine ────────── */

function TickEnginePanel() {
  const [status, setStatus] = useState<TickStatus | null>(null);
  const refresh = () => ariaApi.tickStatus().then(setStatus).catch(() => {});
  useEffect(() => { refresh(); const t = setInterval(refresh, 2000); return () => clearInterval(t); }, []);

  const advance = async (dt: number) => {
    try { setStatus(await ariaApi.tickAdvance(dt)); } catch { /* ignore */ }
  };

  return (
    <Panel title="Tick Engine">
      {status && (
        <>
          <div className="text-[10px] text-ui-text-dim">
            {status.registered.length} subsystems · {status.tick_count} ticks · {status.last_wall_ms.toFixed(2)} ms/tick
          </div>
          <div className="text-[10px] text-ui-text-faint font-mono mt-1">
            Sim time: {status.total_sim_time_s.toFixed(1)} s ({(status.total_sim_time_s / 3600).toFixed(2)} hr)
          </div>
          <div className="flex flex-wrap gap-1 mt-2">
            {status.registered.map(n => (
              <span key={n} className="text-[9px] px-1 py-0.5 rounded bg-ui-bg-2 border border-ui-border">{n}</span>
            ))}
          </div>
          <div className="flex gap-1 mt-2">
            <button onClick={() => advance(1)}    className="flex-1 px-1 py-0.5 text-[10px] rounded bg-ui-bg-2 border border-ui-border hover:bg-ui-bg-3">+1 s</button>
            <button onClick={() => advance(60)}   className="flex-1 px-1 py-0.5 text-[10px] rounded bg-ui-bg-2 border border-ui-border hover:bg-ui-bg-3">+1 min</button>
            <button onClick={() => advance(3600)} className="flex-1 px-1 py-0.5 text-[10px] rounded bg-ui-bg-2 border border-ui-border hover:bg-ui-bg-3">+1 hr</button>
            <button onClick={() => advance(86400)} className="flex-1 px-1 py-0.5 text-[10px] rounded bg-ui-accent/15 border border-ui-accent hover:bg-ui-accent/40">+1 day</button>
          </div>
        </>
      )}
    </Panel>
  );
}


/* ────────── Reactor (derived from part_inspector) ────────── */

function ReactorPanel() {
  const [snap, setSnap] = useState<PartSnapshot | null>(null);
  const refresh = () => ariaApi.inspectPart('reactor_engine').then(setSnap).catch(() => {});
  useEffect(() => { refresh(); const t = setInterval(refresh, 2000); return () => clearInterval(t); }, []);

  if (!snap) return <Panel title="Fusion Reactor">Loading…</Panel>;

  const tempC = snap.temperature_k ? (snap.temperature_k - 273.15).toFixed(0) : '—';
  const power = snap.power_draw_w != null
    ? snap.power_draw_w >= 1e6 ? (snap.power_draw_w / 1e6).toFixed(1) + ' MW'
    :   snap.power_draw_w >= 1e3 ? (snap.power_draw_w / 1e3).toFixed(1) + ' kW'
    :   snap.power_draw_w.toFixed(0) + ' W'
    : '—';

  const statusColor = !snap.operational ? 'text-sev-crit'
                    : (snap.duty_cycle_pct ?? 0) > 50 ? 'text-sev-warn'
                    : 'text-sev-ok';

  return (
    <Panel title="Fusion Reactor (D/He-3)">
      <div className="grid grid-cols-2 gap-1 text-[10px]">
        <Metric label="Status" value={snap.operational ? 'ONLINE' : 'OFFLINE'} color={statusColor} />
        <Metric label="Duty"   value={snap.duty_cycle_pct != null ? `${snap.duty_cycle_pct.toFixed(0)}%` : '—'} />
        <Metric label="T first-wall" value={`${tempC} °C`} />
        <Metric label="Thermal P"    value={power} />
        <Metric label="Health" value={`${snap.health_pct.toFixed(1)}%`} />
        <Metric label="Mass"   value={`${(snap.mass_kg/1000).toFixed(0)} t`} />
      </div>
      {snap.failure_mode && (
        <div className="mt-1 text-[10px] text-sev-crit">⚠ {snap.failure_mode}</div>
      )}
      <div className="mt-2 text-[9px] text-ui-text-faint italic">
        {snap.description}
      </div>
    </Panel>
  );
}


/* ────────── Avionics SEU ────────── */

function AvionicsSEUPanel() {
  const [seu, setSEU] = useState<SEUStatus | null>(null);
  const refresh = () => ariaApi.avionicsSEU().then(setSEU).catch(() => {});
  useEffect(() => { refresh(); const t = setInterval(refresh, 2000); return () => clearInterval(t); }, []);

  if (!seu) return <Panel title="Avionics (SEU / ECC / TMR)">Loading…</Panel>;

  return (
    <Panel title="Avionics (SEU / ECC / TMR)">
      <div className="grid grid-cols-2 gap-1 text-[10px]">
        <Metric label="SRAM"     value={`${seu.config.total_sram_mbit} Mbit`} />
        <Metric label="CPUs"     value={`${seu.config.cpu_count} (TMR ${seu.config.tmr_enabled ? 'on' : 'off'})`} />
        <Metric label="SEU events"   value={String(seu.totals.seu_events)} />
        <Metric label="ECC corrected" value={String(seu.totals.ecc_corrected)} />
        <Metric label="ECC halts"     value={String(seu.totals.ecc_detect_only_halts)}
                color={seu.totals.ecc_detect_only_halts > 0 ? 'text-sev-warn' : undefined} />
        <Metric label="ECC escapes"   value={String(seu.totals.ecc_escapes)}
                color={seu.totals.ecc_escapes > 0 ? 'text-sev-crit' : 'text-sev-ok'} />
        <Metric label="TMR disagree"  value={String(seu.totals.tmr_disagreements)} />
        <Metric label="SEU rate/day"  value={seu.rates.seu_per_day.toExponential(2)} />
      </div>
      <div className="text-[9px] text-ui-text-faint mt-1">
        Shielding factor: {seu.rates.shielding_factor.toExponential(1)} · correction rate: {(seu.rates.correction_rate * 100).toFixed(2)}%
      </div>
    </Panel>
  );
}


/* ────────── ECLSS trace contaminants ────────── */

function EclssContaminantsPanel() {
  const [data, setData] = useState<ContaminantsStatus | null>(null);
  const refresh = () => ariaApi.eclssContaminants().then(setData).catch(() => {});
  useEffect(() => { refresh(); const t = setInterval(refresh, 2000); return () => clearInterval(t); }, []);

  if (!data) return <Panel title="ECLSS Trace Contaminants">Loading…</Panel>;

  return (
    <Panel title="ECLSS Trace Contaminants">
      <div className="text-[10px] text-ui-text-dim mb-1">
        Volume: {(data.cabin_volume_m3 / 1000).toFixed(0)}k m³ · Crew: {data.crew_size} · Scrubber eff: {(data.scrubber_efficiency_frac * 100).toFixed(0)}%
      </div>
      <div className="space-y-1">
        {Object.entries(data.contaminants).map(([key, c]) => {
          const margin = c.margin_to_smac_180d_pct;
          const color = margin > 50 ? 'bg-sev-ok' : margin > 10 ? 'bg-sev-warn' : 'bg-sev-crit';
          return (
            <div key={key}>
              <div className="flex justify-between text-[10px]">
                <span className={c.alarm ? 'text-sev-crit' : 'text-ui-text'}>
                  {c.alarm && '⚠ '}{c.name} ({c.formula})
                </span>
                <span className="font-mono text-ui-text-dim">
                  {c.concentration_mg_m3.toFixed(3)} / {c.smac_180day} mg·m⁻³
                </span>
              </div>
              <div className="h-1 bg-ui-bg-2 rounded overflow-hidden">
                <div className={`h-full ${color} transition-all`} style={{ width: `${Math.max(2, Math.min(100, 100 - margin))}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}


/* ────────── Shared helpers ────────── */

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="p-2 bg-ui-bg-1/40 border border-ui-border rounded">
      <div className="text-[10px] uppercase tracking-wider text-ui-accent font-bold mb-1">{title}</div>
      {children}
    </div>
  );
}

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="text-[8px] uppercase tracking-wide text-ui-text-faint">{label}</div>
      <div className={`font-mono ${color ?? 'text-ui-text'}`}>{value}</div>
    </div>
  );
}
