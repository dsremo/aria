/**
 * LiveStateBadge — propagated live ECI state vector for a real spacecraft,
 * shown next to the simulator's synthetic state for "sim-vs-real" comparison.
 *
 * Hits /api/telemetry/live_state which pulls the latest TLE from the
 * Celestrak cache (10-minute TTL) and propagates it via the same SGP4-J2
 * code we use everywhere else. Falls back to the bundled snapshot if
 * Celestrak is unreachable.
 *
 * Roadmap Track 1 Phase 1 — see docs/ROADMAP_THREE_GAPS.md.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type LiveStateVector } from '../api/aria';

interface Props {
  /** NORAD catalog ID. Default 25544 (ISS). */
  norad?: string;
  /** Celestrak group to search. Default 'stations' (small + always cached). */
  group?: string;
  /** Refresh interval in seconds. Default 60. */
  refreshSec?: number;
  /** Optional comparison vector from the simulator (km). */
  simRkm?: [number, number, number];
}

function formatKm(v: number): string {
  return v.toFixed(1);
}

function ageSec(fetchedAtWall: number): number {
  return Math.max(0, Math.floor(Date.now() / 1000 - fetchedAtWall));
}

export function LiveStateBadge({
  norad = '25544',
  group = 'stations',
  refreshSec = 60,
  simRkm,
}: Props) {
  const [state, setState] = useState<LiveStateVector | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const s = await ariaApi.telemetryLiveState(norad, group);
        if (!cancelled) {
          setState(s);
          setErr(null);
        }
      } catch (e) {
        if (!cancelled) setErr((e as Error).message);
      }
    };
    tick();
    const id = setInterval(tick, Math.max(10, refreshSec) * 1000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [norad, group, refreshSec]);

  if (err) {
    return (
      <div className="rounded border border-sev-crit/40 bg-sev-crit/30 px-3 py-2 text-xs text-sev-crit">
        live state unavailable — {err}
      </div>
    );
  }
  if (!state) {
    return (
      <div className="rounded border border-ui-border-strong/40 bg-ui-bg-1/40 px-3 py-2 text-xs text-ui-text-dim">
        loading live state…
      </div>
    );
  }

  const age = ageSec(state.fetched_at_wall);
  const stale = age > 600; // bundled fallback / very old cache
  const sourceColor = state.source === 'celestrak' ? 'text-sev-ok' : 'text-sev-warn';

  let delta: { km: number; kmps: number } | null = null;
  if (simRkm) {
    const dx = state.r_eci_km[0] - simRkm[0];
    const dy = state.r_eci_km[1] - simRkm[1];
    const dz = state.r_eci_km[2] - simRkm[2];
    delta = {
      km: Math.sqrt(dx * dx + dy * dy + dz * dz),
      kmps: 0,
    };
  }

  return (
    <div className="rounded border border-ui-border-strong/40 bg-ui-bg-1/40 px-3 py-2 text-xs text-ui-text">
      <div className="flex items-center justify-between gap-3">
        <div className="font-semibold tracking-wide text-ui-text">
          {state.name} <span className="text-ui-text-faint">({state.norad})</span>
        </div>
        <div className={sourceColor}>
          {state.source} · {age}s old{stale ? ' · stale' : ''}
        </div>
      </div>
      <div className="mt-1 grid grid-cols-3 gap-2 text-ui-text">
        <div>alt {formatKm(state.altitude_km)} km</div>
        <div>v {state.speed_kmps.toFixed(3)} km/s</div>
        <div>T {state.period_min.toFixed(2)} min</div>
      </div>
      <div className="mt-1 font-mono text-[10px] text-ui-text-faint">
        r_eci = [{state.r_eci_km.map((v) => v.toFixed(1)).join(', ')}] km
      </div>
      {delta && (
        <div className="mt-1 text-[10px] text-ui-accent">
          sim-vs-live position residual: {delta.km.toFixed(2)} km
        </div>
      )}
    </div>
  );
}

export default LiveStateBadge;
