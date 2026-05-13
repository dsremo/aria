/**
 * DsnNowPanel — Deep Space Network live contact state.
 *
 * Polls /api/telemetry/dsn every 30 s (matches the backend cache TTL —
 * polling faster gives no benefit, polling slower wastes the cache).
 * Groups antennas by site (Goldstone / Madrid / Canberra) and shows
 * which spacecraft each dish is talking to right now.
 *
 * When NASA's eyes.nasa.gov upstream is unreachable, the source badge
 * goes red and the table renders the last-known contact list (stale)
 * so the operator can see the fact of the outage and the data they
 * had before it.
 *
 * Roadmap Track 1 Phase 3 — see docs/ROADMAP_THREE_GAPS.md.
 */

import { useEffect, useState } from 'react';
import { SatelliteDish } from 'lucide-react';
import { ariaApi, type DsnNowResponse } from '../api/aria';
import { EmptyState } from './EmptyState';

const SITE_COLORS: Record<string, string> = {
  Goldstone: 'text-sev-warn border-sev-warn/40',
  Madrid: 'text-sev-crit border-sev-crit/40',
  Canberra: 'text-ui-accent border-ui-accent/40',
  Unknown: 'text-ui-text-dim border-ui-border-strong/40',
};

const ACTIVITY_COLORS: Record<string, string> = {
  'two-way': 'bg-sev-ok/30 text-sev-ok',
  receive: 'bg-ui-accent-strong/30 text-ui-accent',
  transmit: 'bg-fuchsia-600/30 text-ui-accent',
  idle: 'bg-ui-bg-3/40 text-ui-text',
};

function formatBps(bps: number | null): string {
  if (bps === null || bps === 0) return '—';
  if (bps >= 1e6) return `${(bps / 1e6).toFixed(2)} Mbps`;
  if (bps >= 1e3) return `${(bps / 1e3).toFixed(2)} kbps`;
  return `${bps.toFixed(0)} bps`;
}

function formatLightTime(s: number | null): string {
  if (s === null || s <= 0) return '—';
  if (s < 60) return `${s.toFixed(1)} s`;
  const m = Math.floor(s / 60);
  const r = s - m * 60;
  return `${m}m ${r.toFixed(0)}s`;
}

export function DsnNowPanel() {
  const [data, setData] = useState<DsnNowResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = () =>
      ariaApi
        .dsnNow()
        .then((d) => {
          if (!cancelled) {
            setData(d);
            setErr(null);
          }
        })
        .catch((e: Error) => !cancelled && setErr(e.message));
    tick();
    const id = setInterval(tick, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (err) {
    return (
      <div className="rounded border border-sev-crit/40 bg-sev-crit/30 px-3 py-2 text-xs text-sev-crit">
        DSN feed unavailable — {err}
      </div>
    );
  }
  if (!data) {
    return (
      <div className="rounded border border-ui-border-strong/40 bg-ui-bg-1/40 px-3 py-2 text-xs text-ui-text-dim">
        loading DSN state…
      </div>
    );
  }

  const stale = data.source === 'offline' || data.age_s > 90;
  const sourceBadge =
    data.source === 'live'
      ? `${data.source} · ${data.age_s}s old`
      : 'offline (NASA upstream unreachable)';

  // Group by site for readability.
  const bySite: Record<string, typeof data.contacts> = {};
  for (const c of data.contacts) {
    (bySite[c.site] ??= []).push(c);
  }
  const sortedSites = Object.keys(bySite).sort();

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-ui-accent">Deep Space Network — Live</h2>
          <p className="text-xs text-ui-text-dim">
            NASA DSN-Now contact state · {data.count} active dish{data.count === 1 ? '' : 'es'}
          </p>
        </div>
        <div className={`text-xs ${stale ? 'text-sev-warn' : 'text-sev-ok'}`}>
          {sourceBadge}
        </div>
      </div>

      {data.count === 0 && (
        <EmptyState Icon={SatelliteDish}
                    title="No active spacecraft contacts"
                    hint="DSN is between handovers. Reload in a few minutes."
                    size="sm" />
      )}

      {sortedSites.map((site) => (
        <div key={site} className="mb-3">
          <div
            className={`mb-1 inline-block px-2 py-0.5 text-[10px] uppercase tracking-widest border rounded ${
              SITE_COLORS[site] ?? SITE_COLORS.Unknown
            }`}
          >
            {site} · {bySite[site].length}
          </div>
          <table className="w-full text-xs text-ui-text">
            <thead>
              <tr className="text-[10px] uppercase tracking-widest text-ui-text-faint">
                <th className="text-left py-1 pr-2">Dish</th>
                <th className="text-left py-1 pr-2">Spacecraft</th>
                <th className="text-right py-1 pr-2">Down</th>
                <th className="text-right py-1 pr-2">Up</th>
                <th className="text-right py-1 pr-2">Sig (dBm)</th>
                <th className="text-right py-1 pr-2">OWLT</th>
                <th className="text-left py-1 pr-2">Mode</th>
              </tr>
            </thead>
            <tbody>
              {bySite[site].map((c) => (
                <tr key={`${c.dish}-${c.spacecraft_id || c.spacecraft}`} className="border-t border-ui-border-soft">
                  <td className="py-1 pr-2 font-mono">{c.dish}</td>
                  <td className="py-1 pr-2">{c.spacecraft}</td>
                  <td className="py-1 pr-2 text-right">{formatBps(c.downlink_data_rate_bps)}</td>
                  <td className="py-1 pr-2 text-right">{formatBps(c.uplink_data_rate_bps)}</td>
                  <td className="py-1 pr-2 text-right">
                    {c.signal_dbm !== null ? c.signal_dbm.toFixed(1) : '—'}
                  </td>
                  <td className="py-1 pr-2 text-right">{formatLightTime(c.light_time_s)}</td>
                  <td className="py-1 pr-2">
                    <span
                      className={`px-1 py-0.5 rounded text-[10px] uppercase ${
                        ACTIVITY_COLORS[c.activity] ?? ''
                      }`}
                    >
                      {c.activity}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

export default DsnNowPanel;
