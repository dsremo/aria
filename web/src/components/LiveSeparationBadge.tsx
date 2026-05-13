/**
 * LiveSeparationBadge — inter-spacecraft separation in ECI.
 *
 * Polls /api/telemetry/separation every 60 s and shows the distance
 * between two named NORAD objects (e.g., ISS vs Tiangong) plus their
 * relative speed. Useful operationally as a sanity overlay against
 * conjunction screening — the residual is the same physics that fires
 * the conjunction watcher's high-Pc events.
 *
 * Roadmap Track 1 Phase 4 — see docs/ROADMAP_THREE_GAPS.md.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type SeparationResponse } from '../api/aria';

interface Props {
  noradA?: string;
  noradB?: string;
  /** Celestrak group (single shared one — both NORADs propagated against same TLE pull). */
  group?: string;
  refreshSec?: number;
  label?: string;
}

function fmtKm(km: number): string {
  if (km >= 100_000) return `${(km / 1000).toFixed(0)} k·km`;
  if (km >= 1000) return `${km.toFixed(0)} km`;
  return `${km.toFixed(1)} km`;
}

export function LiveSeparationBadge({
  noradA = '25544',  // ISS (ZARYA)
  noradB = '48274',  // Tiangong space station
  group = 'stations',
  refreshSec = 60,
  label,
}: Props) {
  const [data, setData] = useState<SeparationResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = () =>
      ariaApi
        .telemetrySeparation(noradA, noradB, group, group)
        .then((d) => {
          if (!cancelled) {
            setData(d);
            setErr(null);
          }
        })
        .catch((e: Error) => !cancelled && setErr(e.message));
    tick();
    const id = setInterval(tick, Math.max(15, refreshSec) * 1000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [noradA, noradB, group, refreshSec]);

  if (err) {
    return (
      <div className="rounded border border-sev-crit/40 bg-sev-crit/30 px-3 py-2 text-xs text-sev-crit">
        separation unavailable — {err}
      </div>
    );
  }
  if (!data) {
    return (
      <div className="rounded border border-ui-border-strong/40 bg-ui-bg-1/40 px-3 py-2 text-xs text-ui-text-dim">
        loading separation…
      </div>
    );
  }

  const sepClass = data.separation_km < 100
    ? 'text-sev-crit'
    : data.separation_km < 1000
      ? 'text-sev-warn'
      : 'text-ui-accent';

  return (
    <div className="rounded border border-ui-border-strong/40 bg-ui-bg-1/40 px-3 py-2 text-xs text-ui-text">
      {label && (
        <div className="text-[10px] uppercase tracking-widest text-ui-accent mb-1">
          {label}
        </div>
      )}
      <div className="flex items-center justify-between gap-3">
        <div className="font-semibold text-ui-text">
          {data.a.name} <span className="text-ui-text-faint">↔</span> {data.b.name}
        </div>
        <div className={`font-mono ${sepClass}`}>{fmtKm(data.separation_km)}</div>
      </div>
      <div className="mt-1 grid grid-cols-2 gap-1 text-[10px] text-ui-text-dim">
        <div>relative speed</div>
        <div className="text-right font-mono">{data.relative_speed_kmps.toFixed(3)} km/s</div>
      </div>
    </div>
  );
}

export default LiveSeparationBadge;
