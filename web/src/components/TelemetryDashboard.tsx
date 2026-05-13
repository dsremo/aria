/**
 * Real-time telemetry dashboard — live sparkline cards.
 *
 * Polls /api/telemetry/live every 2s. Each metric renders as a card
 * with current value + a mini SVG sparkline of recent history.
 * This is the operator's primary "at a glance" view during a mission.
 */

import { useEffect, useState } from 'react';
import { SeverityBadge } from './SeverityBadge';
import { useSettings } from './SettingsPanel';

interface MetricValue {
  value: number | string;
  unit: string;
  label: string;
}

interface TelemetryData {
  timestamp: number;
  metrics: Record<string, MetricValue>;
  history: Record<string, number>[];
}

export function TelemetryDashboard() {
  const settings = useSettings();
  const [data, setData] = useState<TelemetryData | null>(null);
  // BUG-021 (2026-04-24, walkthrough): endpoint failures used to leave
  // the panel stuck on "Loading telemetry…" forever.  Now we track the
  // last successful poll + the last failure and render an explicit
  // stale / offline banner while keeping the last-known tiles visible.
  const [lastOk, setLastOk]   = useState<number | null>(null);
  const [lastErr, setLastErr] = useState<string | null>(null);
  const [, forceTick] = useState(0);

  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      try {
        const r = await fetch('/api/telemetry/live');
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const d = await r.json();
        if (!alive) return;
        setData(d);
        setLastOk(Date.now());
        setLastErr(null);
      } catch (e: any) {
        if (!alive) return;
        setLastErr(e?.message ?? String(e));
      }
    };
    refresh();
    const t = setInterval(refresh, 2000);
    // Re-render every second so the "stale Ns ago" counter ticks even
    // when no new data arrives (otherwise the panel looks frozen).
    const tick = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => { alive = false; clearInterval(t); clearInterval(tick); };
  }, []);

  if (!data) {
    // First-load state — explicit about *why* we have nothing yet.
    return (
      <div className="p-4 text-sm text-ui-text-dim">
        {lastErr
          ? <span className="text-sev-crit">Telemetry endpoint unreachable: {lastErr} — retrying…</span>
          : <span>Loading telemetry…</span>}
      </div>
    );
  }

  const metrics = data.metrics;
  const history = data.history || [];

  // Freshness classification.
  const ageMs = lastOk !== null ? Date.now() - lastOk : Infinity;
  const freshness: 'live' | 'stale' | 'offline' =
    ageMs <  4_000 ? 'live' :
    ageMs < 30_000 ? 'stale' : 'offline';

  // Order: most important first
  const order = [
    'mission_phase', 'elapsed_yr', 'velocity_m_s', 'position_ly',
    'propellant_pct', 'propellant_kg', 'eclss_scrubber_eff_pct',
    'power_margin_pct', 'hull_health_pct', 'hull_impacts',
    'crew_health_bone', 'crew_health_psych', 'food_store_kg',
  ];
  const keys = order.filter(k => k in metrics);
  // Add any keys not in the order list
  for (const k of Object.keys(metrics)) {
    if (!keys.includes(k)) keys.push(k);
  }

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ui-accent">Live Telemetry</h2>
          {freshness === 'stale' && (
            <SeverityBadge severity="warn">⚠ stale — last update {Math.round(ageMs / 1000)}s ago</SeverityBadge>
          )}
          {freshness === 'offline' && (
            <SeverityBadge severity="crit">● offline — {Math.round(ageMs / 1000)}s since last update{lastErr ? ` (${lastErr})` : ''}</SeverityBadge>
          )}
        </div>
        <p className="text-xs text-ui-text-dim">
          Polling every 2s. Sparklines show last {history.length} samples.
        </p>
      </div>

      <div className={
        settings.telemetryDensity === 'compact'
          ? 'grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2'
          : settings.telemetryDensity === 'spacious'
          ? 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'
          : 'grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3'
      }>
        {keys.map(key => {
          const m = metrics[key];
          const isNumeric = typeof m.value === 'number';
          const histValues = isNumeric
            ? history.map(h => h[key]).filter((v): v is number => v !== undefined)
            : [];

          return (
            <MetricCard
              key={key}
              label={m.label}
              value={m.value}
              unit={m.unit}
              history={histValues}
              metricKey={key}
            />
          );
        })}
      </div>
    </div>
  );
}

function MetricCard({
  label, value, unit, history, metricKey,
}: {
  label: string;
  value: number | string;
  unit: string;
  history: number[];
  metricKey: string;
}) {
  const isNumeric = typeof value === 'number';

  // BUG-009 (2026-04-24): the generic "k"-suffix formatter + unit label
  // "kg" produced "40.6k kg", which reads as 40.6 kilograms but actually
  // means 40.6 thousand kg (= 40.6 tonnes).  The Agriculture panel
  // correctly shows it as "40.6 t".  Prefer unit promotion over bare
  // SI-prefix on mass so the displayed label matches the scale.
  let displayVal: string;
  let displayUnit = unit;
  if (!isNumeric) {
    displayVal = String(value);
  } else if (unit === 'kg' && (value as number) >= 1000) {
    // Promote to tonnes.  A "mega-tonne" tier covers generation-ship
    // inventory scales (hull mass, shield mass).
    const v = value as number;
    if (v >= 1e9) {
      displayVal = (v / 1e9).toFixed(2);
      displayUnit = 'Mt';
    } else if (v >= 1e6) {
      displayVal = (v / 1e6).toFixed(2);
      displayUnit = 'kt';
    } else {
      displayVal = (v / 1e3).toFixed(1);
      displayUnit = 't';
    }
  } else if ((value as number) >= 1e6) {
    displayVal = `${(value as number / 1e6).toFixed(2)}M`;
  } else if ((value as number) >= 1e3) {
    displayVal = `${(value as number / 1e3).toFixed(1)}k`;
  } else if (Number.isInteger(value)) {
    displayVal = String(value);
  } else {
    displayVal = (value as number).toFixed(2);
  }

  // Color based on metric type
  const color = metricKey.includes('health') || metricKey === 'propellant_pct' || metricKey === 'power_margin_pct'
    ? (typeof value === 'number' && value < 30 ? 'text-sev-crit' : typeof value === 'number' && value < 70 ? 'text-sev-warn' : 'text-sev-ok')
    : metricKey === 'mission_phase'
    ? 'text-ui-accent'
    : 'text-ui-text';

  return (
    <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-3 flex flex-col">
      <div className="text-[9px] uppercase tracking-wider text-ui-text-faint mb-1">{label}</div>
      <div className={`text-xl font-bold font-mono ${color} mb-1`}>
        {displayVal}
        {displayUnit && <span className="text-xs text-ui-text-dim ml-1">{displayUnit}</span>}
      </div>
      {history.length > 2 && (
        <>
          <Sparkline data={history} color={metricKey.includes('health') || metricKey === 'propellant_pct' ? '#10b981' : '#06b6d4'} />
          {/* Trend stats row — min / mean / max over the visible
              window, and Δ since the first sample.  Helps operators
              spot "slowly creeping" metrics (where the final value
              reads fine but the trend is down) at a glance. */}
          {isNumeric && <TrendStats data={history} />}
        </>
      )}
    </div>
  );
}

function TrendStats({ data }: { data: number[] }) {
  const min  = Math.min(...data);
  const max  = Math.max(...data);
  const mean = data.reduce((s, v) => s + v, 0) / data.length;
  const dSinceStart = data[data.length - 1] - data[0];
  // Pick an appropriate decimal resolution: integer-looking values
  // stay integer, sub-unit values get more decimals.
  const fmt = (v: number) => {
    const abs = Math.abs(v);
    if (abs >= 1000) return (v / 1000).toFixed(1) + 'k';
    if (abs >= 10)   return v.toFixed(1);
    if (abs >= 1)    return v.toFixed(2);
    return v.toFixed(3);
  };
  const deltaColor = Math.abs(dSinceStart) < (max - min) * 0.05
    ? 'text-ui-text-dim'
    : dSinceStart > 0 ? 'text-sev-ok' : 'text-sev-crit';
  const deltaArrow = Math.abs(dSinceStart) < 1e-6 ? '→' : dSinceStart > 0 ? '↗' : '↘';
  return (
    <div className="mt-0.5 flex items-center justify-between text-[8px] font-mono text-ui-text-faint">
      <span title="min in window">↓ {fmt(min)}</span>
      <span title="mean in window">μ {fmt(mean)}</span>
      <span title="max in window">↑ {fmt(max)}</span>
      <span className={deltaColor} title={`Δ since first sample (${data.length} pts)`}>
        {deltaArrow} {fmt(dSinceStart)}
      </span>
    </div>
  );
}

function Sparkline({ data, color = '#06b6d4' }: { data: number[]; color?: string }) {
  if (data.length < 2) return null;

  const W = 120;
  const H = 28;
  const PAD = 2;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data.map((v, i) => {
    const x = PAD + (i / (data.length - 1)) * (W - 2 * PAD);
    const y = H - PAD - ((v - min) / range) * (H - 2 * PAD);
    return `${x},${y}`;
  }).join(' ');

  // Fill area under the line
  const first = `${PAD},${H - PAD}`;
  const last = `${PAD + ((data.length - 1) / (data.length - 1)) * (W - 2 * PAD)},${H - PAD}`;
  const fillPoints = `${first} ${points} ${last}`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-7 mt-auto" preserveAspectRatio="none">
      <polygon points={fillPoints} fill={color} fillOpacity="0.15" />
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      {/* Current value dot */}
      {data.length > 0 && (() => {
        const lastX = PAD + ((data.length - 1) / (data.length - 1)) * (W - 2 * PAD);
        const lastY = H - PAD - ((data[data.length - 1] - min) / range) * (H - 2 * PAD);
        return <circle cx={lastX} cy={lastY} r="2" fill={color} />;
      })()}
    </svg>
  );
}
