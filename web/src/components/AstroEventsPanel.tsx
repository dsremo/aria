/**
 * Astronomical Events Panel — what's coming up in the sky.
 *
 * Calls /api/astro_events for the chosen date range and lists every
 * upcoming opposition, conjunction, elongation, perihelion, and lunar
 * perigee/apogee. Filterable by kind, sortable chronologically. The
 * "JD → date" conversion runs client-side so we can format civil dates
 * without a round-trip.
 *
 * 2026-04-24 upgrade: each row now carries a type icon + an at-a-glance
 * "in N d" countdown, and a "next up" hero card makes the single most
 * imminent event visible without scanning the table.  An extra
 * Moon-phase section computed client-side via astronomy-engine (MIT)
 * lists the next 8 new/first-quarter/full/third-quarter moments — these
 * don't come from the backend ephemeris endpoint and are purely
 * browser-side, zero round-trip.
 */

import { useEffect, useMemo, useState } from 'react';
import * as Astronomy from 'astronomy-engine';

interface AstroEvent {
  jd: number;
  kind: string;
  body: string;
  body2: string | null;
  value: number;
  description: string;
}

interface EventsResponse {
  start_jd: number;
  end_jd: number;
  count: number;
  events: AstroEvent[];
}

const KIND_FILTERS: { id: string; label: string; emoji?: string }[] = [
  { id: 'all',                  label: 'All' },
  { id: 'opposition',           label: 'Oppositions' },
  { id: 'gr_elongation',        label: 'Elongations' },
  { id: 'conjunction',          label: 'Conjunctions' },
  { id: 'eclipse',              label: 'Eclipses' },
  { id: 'meteor_shower',        label: 'Meteor showers' },
  { id: 'perihelion',           label: 'Perihelia' },
  { id: 'lunar',                label: 'Lunar perigee/apogee' },
];

const KIND_COLOR: Record<string, string> = {
  opposition:            'text-sev-ok',
  gr_elongation:         'text-ui-accent',
  inferior_conjunction:  'text-sev-warn',
  superior_conjunction:  'text-sev-warn',
  planet_conjunction:    'text-sev-warn',
  perihelion:            'text-ui-accent',
  comet_perihelion:      'text-blue-300',
  perigee:               'text-sev-crit',
  apogee:                'text-sev-crit',
  solar_eclipse:         'text-sev-warn',
  lunar_eclipse:         'text-sev-crit',
  meteor_shower:         'text-lime-300',
};

const KIND_ICON: Record<string, string> = {
  opposition:            '◉',
  gr_elongation:         '⬌',
  inferior_conjunction:  '⊙',
  superior_conjunction:  '⊙',
  planet_conjunction:    '⚹',
  perihelion:            '↯',
  comet_perihelion:      '☄',
  perigee:               '◐',
  apogee:                '◑',
  solar_eclipse:         '☀',
  lunar_eclipse:         '🌑',
  meteor_shower:         '✹',
};

// JD → civil date (Meeus Ch.7) — same algorithm as our Python side.
function jdToCivil(jd: number): { year: number; month: number; day: number; hour: number; minute: number } {
  const Z = Math.floor(jd + 0.5);
  let A = Z;
  if (Z >= 2299161) {
    const alpha = Math.floor((Z - 1867216.25) / 36524.25);
    A = Z + 1 + alpha - Math.floor(alpha / 4);
  }
  const B = A + 1524;
  const C = Math.floor((B - 122.1) / 365.25);
  const D = Math.floor(365.25 * C);
  const E = Math.floor((B - D) / 30.6001);
  const dayFrac = B - D - Math.floor(30.6001 * E) + (jd + 0.5 - Z);
  const day = Math.floor(dayFrac);
  const fracDay = dayFrac - day;
  const month = E < 14 ? E - 1 : E - 13;
  const year = month > 2 ? C - 4716 : C - 4715;
  const hour = Math.floor(fracDay * 24);
  const minute = Math.floor((fracDay * 24 - hour) * 60);
  return { year, month, day, hour, minute };
}

function fmtDate(jd: number): string {
  const d = jdToCivil(jd);
  const mm = String(d.month).padStart(2, '0');
  const dd = String(d.day).padStart(2, '0');
  const hh = String(d.hour).padStart(2, '0');
  const mn = String(d.minute).padStart(2, '0');
  return `${d.year}-${mm}-${dd} ${hh}:${mn} UT`;
}

function jdNow(): number {
  // JS Date → JD (UT). Unix epoch 1970-Jan-01 = JD 2440587.5.
  return Date.now() / 86400000 + 2440587.5;
}

function jdFromYearMonth(year: number, month: number): number {
  // Meeus eq. 7.1 at day 1.
  let y = year, m = month;
  if (m <= 2) { y -= 1; m += 12; }
  const a = Math.floor(y / 100);
  const b = 2 - a + Math.floor(a / 4);
  return Math.floor(365.25 * (y + 4716)) + Math.floor(30.6001 * (m + 1)) + 1 + b - 1524.5;
}

function fmtCountdown(jd: number, nowJd: number): string {
  const dt = jd - nowJd;
  if (dt < 0) {
    const abs = Math.abs(dt);
    if (abs < 1/24) return `${Math.round(abs * 1440)} min ago`;
    if (abs < 1)    return `${Math.round(abs * 24)} h ago`;
    return `${Math.round(abs)} d ago`;
  }
  if (dt < 1/24) return `in ${Math.round(dt * 1440)} min`;
  if (dt < 1)    return `in ${Math.round(dt * 24)} h`;
  if (dt < 30)   return `in ${Math.round(dt)} d`;
  if (dt < 365)  return `in ${Math.round(dt / 30.4375)} mo`;
  return `in ${(dt / 365.25).toFixed(1)} yr`;
}

const MOON_PHASE_LABEL: Record<number, string> = {
  0:  'New',
  90: 'First quarter',
  180: 'Full',
  270: 'Third quarter',
};
const MOON_PHASE_ICON: Record<number, string> = {
  0:   '🌑',
  90:  '🌓',
  180: '🌕',
  270: '🌗',
};

function nextMoonPhases(n = 8): { date: Date; phase: number }[] {
  // astronomy-engine's SearchMoonPhase scans forward for the next
  // moment the moon's ecliptic longitude hits the target (0/90/180/270°).
  // We walk through all four targets repeatedly until we have `n`
  // events, then sort chronologically.
  const out: { date: Date; phase: number }[] = [];
  const targets = [0, 90, 180, 270];
  let cursor = new Date();
  while (out.length < n) {
    for (const phase of targets) {
      try {
        const t = Astronomy.SearchMoonPhase(phase, cursor, 40);
        if (t) out.push({ date: t.date, phase });
      } catch { /* skip on failure */ }
    }
    // Advance the cursor by 30 days so the inner loop doesn't keep
    // finding the same four dates.
    cursor = new Date(cursor.getTime() + 30 * 86400000);
  }
  return out
    .sort((a, b) => a.date.getTime() - b.date.getTime())
    .slice(0, n);
}

export function AstroEventsPanel() {
  const today = useMemo(() => {
    const d = jdToCivil(jdNow());
    return { year: d.year, month: d.month };
  }, []);
  const [yearStart, setYearStart] = useState(today.year);
  const [monthStart, setMonthStart] = useState(today.month);
  const [spanMonths, setSpanMonths] = useState(12);
  const [filter, setFilter] = useState('all');
  const [data, setData] = useState<EventsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const fetchEvents = async () => {
    setLoading(true);
    setErr(null);
    try {
      const start = jdFromYearMonth(yearStart, monthStart);
      const end = start + spanMonths * 30.4375;
      const r = await fetch(`/api/astro_events?start_jd=${start}&end_jd=${end}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setData(j);
    } catch (e: any) {
      setErr(e.message ?? String(e));
    } finally {
      setLoading(false);
    }
  };

  // R65 (2026-04-24) C-2: missing `[yearStart, monthStart, spanMonths]`
  // meant changing the date-range controls did nothing until the user
  // clicked Refresh.  Auto-refetch on range change; `filter` is purely
  // client-side so it stays out of deps.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchEvents(); }, [yearStart, monthStart, spanMonths]);

  const filtered = useMemo(() => {
    if (!data) return [];
    if (filter === 'all') return data.events;
    if (filter === 'conjunction')
      return data.events.filter((e) =>
        e.kind === 'planet_conjunction' || e.kind === 'inferior_conjunction' || e.kind === 'superior_conjunction');
    if (filter === 'perihelion')
      return data.events.filter((e) => e.kind === 'perihelion' || e.kind === 'comet_perihelion');
    if (filter === 'lunar')
      return data.events.filter((e) => e.kind === 'perigee' || e.kind === 'apogee');
    if (filter === 'eclipse')
      return data.events.filter((e) => e.kind === 'solar_eclipse' || e.kind === 'lunar_eclipse');
    return data.events.filter((e) => e.kind === filter);
  }, [data, filter]);

  // Next-up hero card: the first event after "now", across all kinds.
  const nowJd = jdNow();
  const nextUp = useMemo(() => {
    if (!data) return null;
    return data.events
      .filter((e) => e.jd >= nowJd)
      .sort((a, b) => a.jd - b.jd)[0] ?? null;
  }, [data, nowJd]);

  // Client-side moon phases (astronomy-engine, MIT).  Recomputed once
  // per mount — these change on a 29-day cycle so re-fetching on every
  // filter change would be wasteful.
  const moonPhases = useMemo(() => {
    try { return nextMoonPhases(8); }
    catch { return []; }
  }, []);

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Astronomical Events</h2>
        <p className="text-xs text-ui-text-dim">
          Oppositions · Conjunctions · Elongations · Perihelia · Lunar perigee/apogee
        </p>
      </div>

      <div className="flex flex-wrap gap-2 items-end mb-3 text-xs">
        <label className="flex flex-col">
          <span className="text-ui-text-dim">Start year</span>
          <input
            type="number" min={1900} max={2100}
            value={yearStart}
            onChange={(e) => setYearStart(Number(e.target.value))}
            className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text w-24"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-ui-text-dim">Start month</span>
          <input
            type="number" min={1} max={12}
            value={monthStart}
            onChange={(e) => setMonthStart(Math.max(1, Math.min(12, Number(e.target.value))))}
            className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text w-20"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-ui-text-dim">Span (months)</span>
          <input
            type="number" min={1} max={60}
            value={spanMonths}
            onChange={(e) => setSpanMonths(Math.max(1, Math.min(60, Number(e.target.value))))}
            className="bg-ui-bg-2 border border-ui-border-strong rounded px-2 py-1 text-ui-text w-24"
          />
        </label>
        <button
          onClick={fetchEvents}
          disabled={loading}
          className="px-4 py-1.5 bg-ui-accent/40 hover:bg-ui-accent-strong text-white rounded disabled:opacity-50"
        >
          {loading ? 'Searching…' : 'Find events'}
        </button>
      </div>

      <div className="flex flex-wrap gap-1 mb-3">
        {KIND_FILTERS.map((k) => (
          <button
            key={k.id}
            onClick={() => setFilter(k.id)}
            className={`px-2 py-0.5 text-xs rounded border ${
              filter === k.id
                ? 'bg-ui-accent/40 border-ui-accent text-white'
                : 'bg-ui-bg-2 border-ui-border text-ui-text hover:border-ui-border-strong'
            }`}
          >
            {k.label}
          </button>
        ))}
      </div>

      {err && (
        <div className="bg-sev-crit/40 border border-sev-crit rounded p-2 text-sev-crit text-xs mb-2">
          Error: {err}
        </div>
      )}

      {nextUp && (
        <div className="mb-3 bg-gradient-to-br from-cyan-950/70 to-slate-900 border border-ui-accent rounded-lg p-3 flex items-center gap-3">
          <div className={`text-3xl ${KIND_COLOR[nextUp.kind] || 'text-ui-text'}`}>
            {KIND_ICON[nextUp.kind] || '•'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-wider text-ui-accent">Next up — {fmtCountdown(nextUp.jd, nowJd)}</div>
            <div className="text-sm text-ui-text truncate">{nextUp.description}</div>
            <div className="text-[11px] text-ui-text-dim font-mono">{fmtDate(nextUp.jd)} · {nextUp.kind.replace(/_/g, ' ')}</div>
          </div>
        </div>
      )}

      {data && (
        <div className="text-xs text-ui-text-dim mb-2">
          {filtered.length} event{filtered.length !== 1 ? 's' : ''} of {data.count} total in range.
        </div>
      )}

      <div className="bg-ui-bg-1/60 border border-ui-border rounded overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-ui-bg-2 text-ui-text-dim">
            <tr>
              <th className="text-left p-2 w-10"></th>
              <th className="text-left p-2 w-44">Date (UT)</th>
              <th className="text-left p-2 w-24">Countdown</th>
              <th className="text-left p-2 w-32">Kind</th>
              <th className="text-left p-2">Description</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((e, idx) => {
              const isNext = nextUp && e.jd === nextUp.jd && e.kind === nextUp.kind;
              return (
                <tr key={idx}
                    className={`border-t border-ui-border ${isNext ? 'bg-ui-accent/30' : ''}`}>
                  <td className={`p-2 text-lg ${KIND_COLOR[e.kind] || 'text-ui-text'}`}>
                    {KIND_ICON[e.kind] || '•'}
                  </td>
                  <td className="p-2 font-mono text-ui-text">{fmtDate(e.jd)}</td>
                  <td className={`p-2 font-mono ${e.jd < nowJd ? 'text-ui-text-faint' : 'text-ui-text'}`}>
                    {fmtCountdown(e.jd, nowJd)}
                  </td>
                  <td className={`p-2 ${KIND_COLOR[e.kind] || 'text-ui-text'}`}>
                    {e.kind.replace(/_/g, ' ')}
                  </td>
                  <td className="p-2 text-ui-text">{e.description}</td>
                </tr>
              );
            })}
            {filtered.length === 0 && !loading && (
              <tr><td colSpan={5} className="p-3 text-center text-ui-text-faint italic">
                No events in this range / filter.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {moonPhases.length > 0 && (
        <div className="mt-4 bg-ui-bg-1/60 border border-ui-border rounded p-3">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-ui-text">Moon phases — next 8</h3>
            <span className="text-[10px] text-ui-text-faint uppercase tracking-wider">
              client-side · astronomy-engine
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {moonPhases.map((p, i) => {
              const jd = p.date.getTime() / 86400000 + 2440587.5;
              return (
                <div key={i} className="bg-ui-bg-0/60 border border-ui-border rounded p-2 flex items-center gap-2">
                  <span className="text-2xl">{MOON_PHASE_ICON[p.phase] || '●'}</span>
                  <div className="min-w-0">
                    <div className="text-[11px] text-ui-text">{MOON_PHASE_LABEL[p.phase]}</div>
                    <div className="text-[10px] font-mono text-ui-text-dim truncate">{fmtDate(jd)}</div>
                    <div className="text-[10px] text-ui-accent">{fmtCountdown(jd, nowJd)}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="mt-3 text-[11px] text-ui-text-dim space-y-1">
        <p>• Times are UT. Refinement: ~1 minute via golden-section search on the underlying ephemeris.</p>
        <p>• "Greatest elongation" = best evening (east) or morning (west) viewing for Mercury / Venus.</p>
        <p>• Source ephemerides: Standish 1992 (planets), MPCORB 2024-Jul-01 (comets); moon phases via astronomy-engine 2.1.19 (MIT).</p>
      </div>
    </div>
  );
}
