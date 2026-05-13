/**
 * Toast Notification System — slide-in alerts for mission events.
 *
 * Polls /api/events/recent for new warning/critical events and shows
 * them as auto-dismissing toast cards in the bottom-right corner.
 * Max 5 visible toasts at a time.  Both warning and critical toasts
 * auto-dismiss: warning after 8 s, critical after 30 s.  Critical
 * events stay permanently visible in the Alarms panel — the toast is
 * only the transient "you should know about this" signal, so letting
 * it pile up indefinitely on a dashboard was hurting SA more than
 * helping it (see user report 2026-04-24, the avionics_ecc_cascade
 * drill left 3 CRITICAL toasts at YR 0.000 stuck on-screen forever).
 *
 * Users can still click × to dismiss early.  A "clear all" is shown
 * above the stack when ≥2 toasts are visible.
 */

import { useEffect, useRef, useState } from 'react';
import { ariaApi, type BusEvent } from '../api/aria';
import { useSettings } from './SettingsPanel';

interface Toast {
  id: string;
  severity: 'warning' | 'critical';
  topic: string;
  text: string;
  simYr: number;
  createdAt: number;
}

const MAX_TOASTS = 5;
const WARNING_TTL_MS  = 8_000;
const CRITICAL_TTL_MS = 30_000;

export function ToastNotifications() {
  const settings = useSettings();
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seenRef = useRef(new Set<string>());

  // Wall-clock second at which this component mounted.  Any event whose
  // backend `timestamp` is older than this is replay from the server's
  // in-memory event history — we've already seen it in a prior session
  // (or the user just hit refresh).  Toasts are a "pay attention to
  // THIS new thing" signal; events from before you opened the page are
  // not new, so we mark them as seen on first poll and never render.
  const mountWallSecRef = useRef(Date.now() / 1000);

  useEffect(() => {
    let firstPoll = true;
    const poll = async () => {
      try {
        const r = await ariaApi.eventsRecent(10, undefined, 'warning');
        for (const ev of r.events) {
          // Deduplicate by topic + sim time (rounded to 0.001 yr)
          const key = `${ev.topic}:${ev.sim_time_yr.toFixed(3)}`;
          if (seenRef.current.has(key)) continue;
          seenRef.current.add(key);

          // Prune seen set to prevent unbounded growth
          if (seenRef.current.size > 500) {
            const arr = Array.from(seenRef.current);
            seenRef.current = new Set(arr.slice(-200));
          }

          // Replay guard: the first poll seeds `seenRef` from the
          // server's existing history without raising any toasts, AND
          // any subsequent event that's older than mount time is also
          // suppressed.  This fixes the hard-refresh regression where
          // CRITICAL events from a pre-refresh drill kept re-appearing
          // whenever the dashboard reloaded.
          if (firstPoll) continue;
          if (ev.timestamp && ev.timestamp < mountWallSecRef.current) continue;

          if (settings.notificationsPaused) continue;
          const sev = ev.severity as 'warning' | 'critical';
          if (sev === 'warning'  && settings.hideWarningToasts)  continue;
          if (sev === 'critical' && settings.hideCriticalToasts) continue;

          const toast: Toast = {
            id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            severity: ev.severity as 'warning' | 'critical',
            topic: ev.topic,
            text: ev.payload?.message || ev.payload?.description || ev.topic.split('.').pop() || '',
            simYr: ev.sim_time_yr,
            createdAt: Date.now(),
          };

          setToasts(prev => [toast, ...prev].slice(0, MAX_TOASTS));
        }
        firstPoll = false;
      } catch { /* silent */ }
    };

    poll();
    const t = setInterval(poll, 3000);
    return () => clearInterval(t);
  }, []);

  // Auto-dismiss both warning and critical after their respective TTLs.
  // Previously critical toasts were excluded from the filter entirely,
  // so a drill like avionics_ecc_cascade left 3 red cards at YR 0.000
  // stuck on-screen forever with no "cleared" state.
  useEffect(() => {
    const t = setInterval(() => {
      const now = Date.now();
      setToasts(prev =>
        prev.filter(toast => {
          const ttl = toast.severity === 'critical' ? CRITICAL_TTL_MS : WARNING_TTL_MS;
          return (now - toast.createdAt) < ttl;
        })
      );
    }, 1000);
    return () => clearInterval(t);
  }, []);

  const dismiss = (id: string) => setToasts(prev => prev.filter(t => t.id !== id));
  const dismissAll = () => setToasts([]);

  if (toasts.length === 0) return null;

  const critCount = toasts.filter(t => t.severity === 'critical').length;
  const warnCount = toasts.filter(t => t.severity === 'warning').length;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm pointer-events-none">
      {toasts.length >= 2 && (
        <div className="self-end pointer-events-auto inline-flex items-center gap-1 px-2 py-0.5 rounded border border-ui-border-strong bg-ui-bg-1/80 text-[10px] uppercase tracking-wider">
          {critCount > 0 && <span className="text-sev-crit">● {critCount}</span>}
          {warnCount > 0 && <span className="text-sev-warn">● {warnCount}</span>}
          <button onClick={dismissAll}
                  className="ml-1 text-ui-text hover:text-white">
            dismiss all
          </button>
        </div>
      )}
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`pointer-events-auto rounded-lg border p-3 shadow-2xl backdrop-blur-sm text-white
            animate-[slideIn_0.3s_ease-out]
            ${toast.severity === 'critical'
              ? 'bg-sev-crit/95 border-sev-crit'
              : 'bg-sev-warn/95 border-sev-warn'}`}
        >
          <div className="flex items-start gap-2">
            <span className="text-lg leading-none mt-0.5">
              {toast.severity === 'critical' ? '🔴' : '🟡'}
            </span>
            <div className="flex-1 min-w-0">
              <div className="text-[10px] uppercase tracking-wider font-bold">
                {toast.severity} · yr {toast.simYr.toFixed(3)}
              </div>
              <div className="text-xs mt-0.5 font-mono truncate text-white/90">{toast.topic}</div>
              {toast.text && (
                <div className="text-[11px] mt-0.5 line-clamp-2 text-white/95">{toast.text}</div>
              )}
            </div>
            <button
              onClick={() => dismiss(toast.id)}
              className="text-xs text-white/70 hover:text-white leading-none"
            >
              ✕
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
