/**
 * Right-side inspection panel. Shows full PartSnapshot for the selected part:
 * name, subsystem, health, temperature, power, dependencies, cascade preview.
 */

import { useEffect, useState } from 'react';
import { Spinner } from './Spinner';
import { ariaApi, type PartSnapshot } from '../api/aria';

interface Props {
  partId: string | null;
  onSelectPart: (id: string) => void;
}

export function PartPanel({ partId, onSelectPart }: Props) {
  const [snap, setSnap]     = useState<PartSnapshot | null>(null);
  const [cascade, setCascade] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!partId) { setSnap(null); setCascade([]); return; }
    setLoading(true);
    Promise.all([
      ariaApi.inspectPart(partId).then(setSnap).catch(() => setSnap(null)),
      ariaApi.cascade(partId).then(r => setCascade(r.cascade)).catch(() => setCascade([])),
    ]).finally(() => setLoading(false));
  }, [partId]);

  if (!partId) {
    return (
      <div className="p-4 text-sm text-ui-text-dim">
        Click a part in the 3D view or parts list to inspect.
      </div>
    );
  }
  if (loading) return <div className="p-4 text-sm text-ui-text-dim"><Spinner label="Loading…" /></div>;
  if (!snap)   return <div className="p-4 text-sm text-sev-crit">Failed to load part.</div>;

  return (
    <div className="p-4 space-y-4">
      <div>
        <div className="text-[10px] uppercase tracking-wide text-ui-text-faint">Name</div>
        <div className="text-lg font-bold text-ui-accent">{snap.name}</div>
        <div className="text-xs text-ui-text-dim mt-1">{snap.description}</div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Stat label="Subsystem" value={snap.subsystem} />
        <Stat label="Material"  value={snap.material} />
        <Stat label="Mass"      value={`${(snap.mass_kg / 1000).toFixed(1)} t`} />
        <Stat label="Health"    value={`${snap.health_pct.toFixed(1)}%`} color={snap.health_pct > 85 ? 'text-sev-ok' : 'text-sev-warn'} />
        <Stat label="Operational" value={snap.operational ? 'ONLINE' : 'OFFLINE'} color={snap.operational ? 'text-sev-ok' : 'text-sev-crit'} />
        <Stat label="Duty"     value={snap.duty_cycle_pct != null ? `${snap.duty_cycle_pct.toFixed(0)}%` : '—'} />
        <Stat label="Temp"     value={snap.temperature_k != null ? `${snap.temperature_k.toFixed(0)} K` : '—'} />
        <Stat label="Power"    value={snap.power_draw_w != null ? formatPower(snap.power_draw_w) : '—'} />
      </div>

      {snap.failure_mode && (
        <div className="p-2 bg-sev-crit/30 border border-sev-crit rounded text-xs text-sev-crit">
          ⚠ {snap.failure_mode}
        </div>
      )}

      <div>
        <div className="text-[10px] uppercase tracking-wide text-ui-text-faint mb-1">Dimensions</div>
        <div className="text-xs space-y-0.5">
          {Object.entries(snap.dimensions_m).map(([k, v]) => (
            <div key={k} className="flex justify-between">
              <span className="text-ui-text-dim">{k}:</span>
              <span className="font-mono text-ui-text">{v} m</span>
            </div>
          ))}
        </div>
      </div>

      {snap.depends_on.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wide text-ui-text-faint mb-1">
            Depends on ({snap.depends_on.length})
          </div>
          <div className="flex flex-wrap gap-1">
            {snap.depends_on.map(id => (
              <button key={id}
                      onClick={() => onSelectPart(id)}
                      className="px-1.5 py-0.5 text-[10px] rounded border border-sev-info bg-sev-info/30 hover:bg-sev-info/50">
                {id}
              </button>
            ))}
          </div>
        </div>
      )}

      {snap.feeds.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wide text-ui-text-faint mb-1">
            Feeds ({snap.feeds.length})
          </div>
          <div className="flex flex-wrap gap-1 max-h-28 overflow-y-auto">
            {snap.feeds.map(id => (
              <button key={id}
                      onClick={() => onSelectPart(id)}
                      className="px-1.5 py-0.5 text-[10px] rounded border border-sev-ok bg-sev-ok/30 hover:bg-sev-ok/50">
                {id}
              </button>
            ))}
          </div>
        </div>
      )}

      {cascade.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wide text-sev-crit mb-1">
            Failure cascade ({cascade.length} parts would fail)
          </div>
          <div className="text-[10px] text-ui-text-dim max-h-24 overflow-y-auto">
            {cascade.join(', ')}
          </div>
        </div>
      )}

      <div>
        <div className="text-[10px] uppercase tracking-wide text-ui-text-faint mb-1">Sources</div>
        <ul className="text-[10px] text-ui-text-dim italic space-y-0.5">
          {snap.sources.map((s, i) => <li key={i}>· {s}</li>)}
        </ul>
      </div>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wide text-ui-text-faint">{label}</div>
      <div className={`text-sm font-semibold ${color ?? 'text-ui-text'}`}>{value}</div>
    </div>
  );
}

function formatPower(w: number): string {
  if (Math.abs(w) >= 1e9) return `${(w / 1e9).toFixed(2)} GW`;
  if (Math.abs(w) >= 1e6) return `${(w / 1e6).toFixed(2)} MW`;
  if (Math.abs(w) >= 1e3) return `${(w / 1e3).toFixed(1)} kW`;
  return `${w.toFixed(0)} W`;
}
