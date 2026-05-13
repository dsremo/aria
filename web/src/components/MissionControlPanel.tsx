/**
 * Mission Control — top-level operator console with 4 sub-panels:
 *   1. Auto-tick (Play/Pause + speed selector)
 *   2. Communications (light-time delay, SNR, modulation, message queue)
 *   3. Agriculture (5-crop yield, food balance, failure injection)
 *   4. Mission timeline / scheduler (queue future events)
 */

import { useEffect, useRef, useState } from 'react';
import { Spinner } from './Spinner';
import { useSettings } from './SettingsPanel';
import { MissionBrief } from './MissionBrief';
import {
  ariaApi,
  type AgricultureState,
  type AutoTickStatus,
  type CommsState,
  type SchedulerState,
} from '../api/aria';

export function MissionControlPanel() {
  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="p-2 pb-0">
        <MissionBrief />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-2 p-2">
        <AutoTickCard />
        <CommsCard />
        <AgricultureCard />
        <SchedulerCard />
      </div>
    </div>
  );
}


/* ────────── Auto-tick ────────── */

const SPEED_PRESETS: { label: string; speed: number }[] = [
  { label: '1×',     speed: 1 },
  { label: '1 min/s',  speed: 60 },
  { label: '1 hr/s',   speed: 3600 },
  { label: '1 day/s',  speed: 86400 },
  { label: '1 wk/s',   speed: 604800 },
  { label: '1 mo/s',   speed: 2.628e6 },
  { label: '1 yr/s',   speed: 31_557_600 },
];

function AutoTickCard() {
  const settings = useSettings();
  const [s, setS] = useState<AutoTickStatus | null>(null);
  const [pendingSpeed, setPendingSpeed] = useState<number | null>(null);
  const autostartFiredRef = useRef(false);

  useEffect(() => {
    const refresh = () => ariaApi.autoTickStatus().then(setS).catch(() => {});
    refresh();
    const t = setInterval(refresh, 1000);
    return () => clearInterval(t);
  }, []);

  const start = async (speed: number) => {
    setPendingSpeed(null);
    setS(await ariaApi.autoTickStart(speed));
  };
  const stop  = async () => setS(await ariaApi.autoTickStop());
  const setSpeed = async (speed: number) => setS(await ariaApi.autoTickSpeed(speed));
  const speedLabel = (sp: number): string => {
    const p = SPEED_PRESETS.find(x => x.speed === sp);
    return p ? p.label : `${sp}×`;
  };

  useEffect(() => {
    if (!s) return;
    if (autostartFiredRef.current) return;
    if (!settings.autostart) return;
    if (s.running) { autostartFiredRef.current = true; return; }
    if (settings.defaultSpeed === 'paused') { autostartFiredRef.current = true; return; }
    autostartFiredRef.current = true;
    start(Number(settings.defaultSpeed)).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s, settings.autostart, settings.defaultSpeed]);

  if (!s) return <Card title="Simulation Speed"><Spinner label="Loading…" /></Card>;

  const settingsDefaultSpeed = settings.defaultSpeed === 'paused' ? 86400 : Number(settings.defaultSpeed);
  const effectiveSpeed = s.running ? s.speed_factor : (pendingSpeed ?? (s.speed_factor || settingsDefaultSpeed));

  return (
    <Card title="Simulation Speed">
      <div className="flex items-center gap-2 mb-2">
        {!s.running ? (
          <button onClick={() => start(effectiveSpeed)}
                  className="flex-1 px-3 py-2 rounded border border-sev-ok bg-sev-ok/15 text-ui-text hover:bg-sev-ok/25 text-sm font-bold">
            ▶ PLAY
          </button>
        ) : (
          <button onClick={stop}
                  className="flex-1 px-3 py-2 rounded border border-sev-crit bg-sev-crit/15 text-ui-text hover:bg-sev-crit/25 text-sm font-bold">
            ⏸ PAUSE
          </button>
        )}
        <div className="text-[10px] text-ui-text-dim">
          {s.running
            ? `running · ${s.tick_count} ticks · ${s.cumulative_sim_yr.toFixed(3)} yr advanced`
            : pendingSpeed != null ? `paused · will start at ${speedLabel(pendingSpeed)}` : 'paused'}
        </div>
      </div>
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-[10px] uppercase tracking-wider text-ui-text-faint">Speed</span>
        <span className="text-[10px] text-ui-text-dim font-mono">{speedLabel(effectiveSpeed)}</span>
      </div>
      <div className="grid grid-cols-4 gap-1">
        {SPEED_PRESETS.map(p => {
          const active = effectiveSpeed === p.speed;
          return (
            <button key={p.label}
                    onClick={() => {
                      // BUG-010 (2026-04-24): previously branched on
                      // `s.running`, which is polled every 1 s.  Clicking
                      // Play then a speed preset within the poll window
                      // saw stale `s.running === false`, took the "pending
                      // only" branch, and the backend never received the
                      // speed change.  Fix: always stage pendingSpeed AND
                      // fire the backend update.  set_speed is a no-op on
                      // a paused tick engine so calling it while paused is
                      // harmless; start() on the next Play still wins.
                      setPendingSpeed(p.speed);
                      setSpeed(p.speed).catch(() => { /* network hiccup; retry on next click */ });
                    }}
                    title={`${p.label} — 1 wall-second = ${p.speed.toLocaleString()} sim-seconds`}
                    className={`px-1.5 py-1 text-[10px] rounded border font-medium transition-colors ${
                      active
                        ? 'border-ui-accent bg-ui-accent/25 text-ui-accent shadow-sm shadow-ui-accent/20'
                        : 'border-ui-border bg-ui-bg-2/40 text-ui-text-dim hover:bg-ui-bg-2 hover:text-ui-text'}`}>
              {p.label}
            </button>
          );
        })}
      </div>
      {s.last_error && (
        <div className="mt-2 p-1 bg-sev-crit/15 border border-sev-crit rounded text-[10px] text-sev-crit">
          ⚠ {s.last_error}
        </div>
      )}
    </Card>
  );
}


/* ────────── Comms ────────── */

function CommsCard() {
  const [c, setC] = useState<CommsState | null>(null);
  const [draft, setDraft] = useState('telemetry burst');
  const [size, setSize]   = useState(1024);
  // Rolling TX-throughput samples: [{ wallMs, cumBytes }].  Two adjacent
  // samples give a bytes/sec estimate; a 30-sample ring buffer spans the
  // last minute of polling at 2 s.  Stored in a ref so we don't force
  // a re-render on every tick — `CommsState` already changes each poll.
  const txHistRef = useRef<{ wallMs: number; cumBytes: number }[]>([]);

  useEffect(() => {
    const refresh = async () => {
      try {
        const next = await ariaApi.comms();
        const hist = txHistRef.current;
        hist.push({ wallMs: Date.now(), cumBytes: next.stats.cumulative_bytes_tx });
        if (hist.length > 30) hist.splice(0, hist.length - 30);
        setC(next);
      } catch { /* silent */ }
    };
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);

  if (!c) return <Card title="Earth Communications"><Spinner label="Loading…" /></Card>;

  // Throughput from the sparkline samples — derivative of cum_bytes_tx.
  const hist = txHistRef.current;
  let bytesPerSec = 0;
  if (hist.length >= 2) {
    const first = hist[0], last = hist[hist.length - 1];
    const dt = Math.max((last.wallMs - first.wallMs) / 1000, 0.5);
    bytesPerSec = Math.max(0, (last.cumBytes - first.cumBytes) / dt);
  }
  const fmtRate = (bps: number) =>
    bps < 1024        ? `${bps.toFixed(0)} B/s`
    : bps < 1024 ** 2 ? `${(bps / 1024).toFixed(1)} KiB/s`
    : bps < 1024 ** 3 ? `${(bps / 1024 ** 2).toFixed(2)} MiB/s`
                      : `${(bps / 1024 ** 3).toFixed(2)} GiB/s`;

  const send = async () => {
    await ariaApi.commsQueue(draft, size);
    setC(await ariaApi.comms());
  };

  const snrColor = c.link.snr_db > 20 ? 'text-sev-ok'
                 : c.link.snr_db > 5  ? 'text-sev-warn' : 'text-sev-crit';

  const fmtDelay = (s: number) => {
    if (s < 60)    return `${s.toFixed(1)} s`;
    if (s < 3600)  return `${(s / 60).toFixed(1)} min`;
    if (s < 86400) return `${(s / 3600).toFixed(1)} hr`;
    if (s < 31_557_600) return `${(s / 86400).toFixed(1)} d`;
    return `${(s / 31_557_600).toFixed(2)} yr`;
  };

  return (
    <Card title="Earth Communications · Ka-Band">
      <div className="grid grid-cols-2 gap-1 text-[10px] mb-2">
        <Stat label="Distance from Earth" value={`${c.link.distance_ly.toFixed(4)} ly`} />
        <Stat label="Light delay (one-way)" value={fmtDelay(c.link.one_way_delay_s)} />
        <Stat label="SNR" value={`${c.link.snr_db.toFixed(1)} dB`} color={snrColor} />
        <Stat label="Modulation" value={c.link.modulation} />
        <Stat label="Bandwidth" value={c.link.achievable_bps_human} />
        <Stat label="Cumulative TX" value={`${(c.stats.cumulative_bytes_tx / 1024).toFixed(1)} KiB`} />
      </div>
      <div className="flex items-center gap-1 mb-2">
        <input value={draft} onChange={e => setDraft(e.target.value)}
               className="flex-1 px-2 py-0.5 bg-ui-bg-2 border border-ui-border rounded text-xs"
               placeholder="message label" />
        <input type="number" value={size} onChange={e => setSize(Number(e.target.value))}
               className="w-20 px-2 py-0.5 bg-ui-bg-2 border border-ui-border rounded text-xs"
               placeholder="bytes" />
        <button onClick={send}
                className="px-2 py-0.5 rounded border border-ui-accent bg-ui-accent/15 text-ui-text hover:bg-ui-accent/25 text-xs">
          → TX
        </button>
      </div>
      {/* Throughput strip — instantaneous TX rate + trailing sparkline
          of bytes/sec over the last ~1 min.  Helps operators spot an
          SNR-driven rate drop or a queue stall long before cum_bytes
          stops moving in the main table. */}
      <div className="mb-2 flex items-center gap-2">
        <div className="text-[9px] uppercase tracking-wider text-ui-text-faint w-20">Throughput</div>
        <div className="font-mono text-[10px] text-ui-accent w-24">{fmtRate(bytesPerSec)}</div>
        <div className="flex-1">
          <TxSparkline hist={hist} />
        </div>
      </div>
      <div className="space-y-0.5 max-h-32 overflow-y-auto">
        {c.queue.length === 0 && <div className="text-[10px] text-ui-text-faint italic">No messages queued</div>}
        {c.queue.slice().reverse().map(m => (
          <div key={m.msg_id} className="text-[10px] flex justify-between gap-1 items-baseline">
            <span className={`text-[9px] uppercase ${m.status === 'received' ? 'text-sev-ok' : m.status === 'in_flight' ? 'text-sev-warn' : 'text-ui-text-faint'}`}>
              {m.status}
            </span>
            <span className="flex-1 truncate text-ui-text">{m.label}</span>
            <span className="text-ui-text-faint text-[9px]">{m.bytes_size} B</span>
            {m.status === 'in_flight' && <span className="text-ui-text-faint text-[9px]">ETA {m.eta_earth_yr.toFixed(3)} yr</span>}
          </div>
        ))}
      </div>
    </Card>
  );
}


/* ────────── Agriculture ────────── */

function AgricultureCard() {
  const [a, setA] = useState<AgricultureState | null>(null);

  useEffect(() => {
    const refresh = () => ariaApi.agriculture().then(setA).catch(() => {});
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);

  if (!a) return <Card title="Hydroponic Agriculture"><Spinner label="Loading…" /></Card>;

  const fail = async (cid: string, mode: string) => setA(await ariaApi.agricultureFailure(cid, mode));
  const restore = async (cid: string) => setA(await ariaApi.agricultureRestore(cid));

  const balance = a.totals.kcal_produced - a.totals.kcal_consumed;
  const balColor = balance > 0 ? 'text-sev-ok' : 'text-sev-crit';

  return (
    <Card title="Hydroponic Agriculture">
      <div className="text-[10px] text-ui-text-dim mb-2">
        {(a.total_area_m2 / 1000).toFixed(0)} k m² · {a.crew_size} crew · food store {(a.food_store_kg / 1000).toFixed(1)} t
        · kcal balance <span className={balColor}>{balance >= 0 ? '+' : ''}{(balance / 1e6).toFixed(2)} M</span>
        {a.totals.days_short_kcal > 0 && <span className="text-sev-crit"> · {a.totals.days_short_kcal} d short</span>}
      </div>
      <div className="space-y-1.5">
        {a.crops.map(c => (
          <div key={c.id} className={`p-1 rounded ${c.failure_active ? 'bg-sev-crit/10 border border-sev-crit' : ''}`}>
            <div className="flex justify-between text-[10px] gap-1">
              <span className="text-ui-text flex-1">
                {c.failure_active && <span className="text-sev-crit">⚠ </span>}
                {c.name}
                <span className="text-ui-text-faint text-[8px]"> · {c.area_m2.toLocaleString()} m²</span>
              </span>
              <span className="font-mono text-ui-text-dim text-[9px]">
                cycle {c.cycle_progress_pct.toFixed(1)} % / {c.days_to_harvest} d
              </span>
            </div>
            <div className="h-1 bg-ui-bg-2 rounded overflow-hidden">
              <div className={`h-full ${c.yield_modifier < 0.5 ? 'bg-sev-crit' : c.yield_modifier < 1 ? 'bg-sev-warn' : 'bg-sev-ok'}`}
                   style={{ width: `${c.cycle_progress_pct}%` }} />
            </div>
            <div className="flex justify-between text-[9px] text-ui-text-faint">
              <span>Last harvest: {(c.last_harvest_kg / 1000).toFixed(2)} t · cum {(c.cumulative_yield_kg / 1000).toFixed(1)} t</span>
              {!c.failure_active ? (
                <button onClick={() => fail(c.id, 'led_outage')}
                        className="text-sev-warn hover:underline">inject LED outage</button>
              ) : (
                <button onClick={() => restore(c.id)}
                        className="text-sev-ok hover:underline">restore</button>
              )}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}


/* ────────── Scheduler ────────── */

const KIND_HINTS: Record<string, { label: string; defaultPayload: () => any }> = {
  note:    { label: 'Note',                    defaultPayload: () => ({ text: 'mission milestone' }) },
  failure: { label: 'Inject failure scenario', defaultPayload: () => ({ scenario_id: 'maglev_trip' }) },
  phase:   { label: 'Transition phase',        defaultPayload: () => ({ to: 'cruise' }) },
  message: { label: 'Send Earth message',      defaultPayload: () => ({ label: 'scheduled telemetry', bytes_size: 1024 }) },
};

function SchedulerCard() {
  const [s, setS] = useState<SchedulerState | null>(null);
  const [fireAt, setFireAt] = useState(10);
  const [kind, setKind]     = useState<keyof typeof KIND_HINTS>('note');
  const [label, setLabel]   = useState('halfway check');
  const [payload, setPayload] = useState<any>({ text: 'mission milestone' });

  const refresh = () => ariaApi.scheduler().then(setS).catch(() => {});
  useEffect(() => { refresh(); const t = setInterval(refresh, 2000); return () => clearInterval(t); }, []);

  const add = async () => {
    await ariaApi.schedulerAdd(fireAt, kind, label, payload);
    refresh();
  };
  const cancel = async (id: string) => { await ariaApi.schedulerCancel(id); refresh(); };

  const setKindAndDefault = (k: keyof typeof KIND_HINTS) => {
    setKind(k);
    setPayload(KIND_HINTS[k].defaultPayload());
  };

  if (!s) return <Card title="Mission Timeline"><Spinner label="Loading…" /></Card>;

  return (
    <Card title="Mission Timeline · Scheduled Events">
      <div className="text-[10px] text-ui-text-dim mb-2">
        sim year {s.current_yr.toFixed(2)} · {s.stats.fired} fired / {s.stats.pending} pending / {s.stats.total} total
      </div>
      <div className="grid grid-cols-[60px_90px_auto_60px] gap-1 mb-2 text-[10px]">
        <input type="number" value={fireAt} onChange={e => setFireAt(Number(e.target.value))}
               className="px-1 py-0.5 bg-ui-bg-2 border border-ui-border rounded" placeholder="yr" />
        <select value={kind} onChange={e => setKindAndDefault(e.target.value as any)}
                className="px-1 py-0.5 bg-ui-bg-2 border border-ui-border rounded">
          {Object.entries(KIND_HINTS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <input value={label} onChange={e => setLabel(e.target.value)}
               className="px-1 py-0.5 bg-ui-bg-2 border border-ui-border rounded" placeholder="label" />
        <button onClick={add}
                className="px-2 rounded border border-ui-accent bg-ui-accent/15 text-ui-text hover:bg-ui-accent/25">+ ADD</button>
      </div>
      <div className="text-[9px] text-ui-text-faint mb-2 font-mono">
        Payload: {JSON.stringify(payload)}
      </div>

      <div className="space-y-0.5 max-h-44 overflow-y-auto">
        {s.events.length === 0 && (
          <div className="text-[10px] text-ui-text-faint italic">
            No scheduled events. Add one above (e.g. "215 yr · phase · begin decel" with payload {"{to: 'deceleration'}"}).
          </div>
        )}
        {s.events.map(e => (
          <div key={e.event_id} className={`flex items-center gap-1 text-[10px] px-1 py-0.5 rounded
                                            ${e.fired ? 'bg-sev-ok/10 text-ui-text-dim' : 'bg-ui-bg-2/30'}`}>
            <span className="text-[8px] uppercase w-12 text-ui-text-faint">{e.kind}</span>
            <span className="font-mono text-ui-text-dim w-14 text-right">{e.fire_at_yr.toFixed(2)} yr</span>
            <span className="flex-1 truncate text-ui-text">{e.label}</span>
            {e.fired
              ? <span className="text-sev-ok text-[9px]">✓ {e.fired_at_yr?.toFixed(2)}</span>
              : <button onClick={() => cancel(e.event_id)}
                        className="text-sev-crit hover:underline text-[9px]">cancel</button>}
          </div>
        ))}
      </div>
    </Card>
  );
}


/* ────────── Shared ────────── */

/** Tiny inline SVG of bytes/sec for the CommsCard.  Bars rather than
 *  a line chart so a zero-rate tick reads as empty column instead of
 *  ambiguously flat. */
function TxSparkline({ hist }: { hist: { wallMs: number; cumBytes: number }[] }) {
  const W = 200, H = 22;
  if (hist.length < 2) {
    return (
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`}
           preserveAspectRatio="none"
           className="border border-ui-border rounded bg-ui-bg-0">
        <text x={W/2} y={H/2 + 4} fontSize={9} textAnchor="middle"
              fill="rgb(var(--ui-text-faint))" fontFamily="monospace">gathering…</text>
      </svg>
    );
  }
  // Compute per-interval bytes/sec.
  const rates: number[] = [];
  for (let i = 1; i < hist.length; i++) {
    const dt = Math.max((hist[i].wallMs - hist[i-1].wallMs) / 1000, 0.1);
    rates.push(Math.max(0, (hist[i].cumBytes - hist[i-1].cumBytes) / dt));
  }
  const max = Math.max(...rates, 1);
  const bw = W / rates.length;
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`}
         preserveAspectRatio="none"
         className="border border-ui-border rounded bg-ui-bg-0">
      {rates.map((r, i) => {
        const h = Math.max(1, (r / max) * (H - 2));
        return (
          <rect key={i} x={i * bw + 0.5} y={H - h}
                width={Math.max(bw - 1, 0.8)} height={h}
                fill={r === 0 ? 'rgb(var(--ui-text-faint))' : 'rgb(var(--ui-accent))'} />
        );
      })}
    </svg>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="p-2 bg-ui-bg-1/60 border border-ui-border rounded flex flex-col">
      <div className="text-[10px] uppercase tracking-wider text-ui-accent font-bold mb-1">{title}</div>
      {children}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="text-[8px] uppercase tracking-wide text-ui-text-faint">{label}</div>
      <div className={`font-mono ${color ?? 'text-ui-text'}`}>{value}</div>
    </div>
  );
}
