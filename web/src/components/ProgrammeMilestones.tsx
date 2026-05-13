/**
 * ProgrammeMilestones — overlay of real-world programme dates for a live
 * mission (Artemis 2 / Artemis 3 / Apollo 11). Pulls from the curated
 * /api/telemetry/mission_schedule endpoint backed by
 * src/aria/integrations/nasa_public/artemis_schedule.py.
 *
 * Roadmap Track 1 Phase 2 — gives the operator a date-stamped overlay so
 * "what date does TLI happen on the real timeline?" is one glance away.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type MissionSchedule } from '../api/aria';

const CONFIDENCE_COLOR: Record<string, string> = {
  NET:       'text-sev-warn border-sev-warn/40 bg-sev-warn/30',
  planned:   'text-ui-accent border-ui-accent/40 bg-ui-accent/30',
  committed: 'text-sev-ok border-sev-ok/40 bg-sev-ok/30',
};

interface Props {
  /** Programme key. 'artemis2' | 'artemis3' | 'apollo11'. */
  program?: string;
  /** Compact (single column) vs default (date column + body). */
  compact?: boolean;
}

export function ProgrammeMilestones({ program = 'artemis2', compact = false }: Props) {
  const [data, setData] = useState<MissionSchedule | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    ariaApi
      .missionSchedule(program)
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setErr(null);
        }
      })
      .catch((e: Error) => !cancelled && setErr(e.message));
    return () => {
      cancelled = true;
    };
  }, [program]);

  if (err) {
    return (
      <div className="rounded border border-sev-crit/40 bg-sev-crit/30 px-3 py-2 text-xs text-sev-crit">
        schedule unavailable — {err}
      </div>
    );
  }
  if (!data) {
    return (
      <div className="rounded border border-ui-border-strong/40 bg-ui-bg-1/40 px-3 py-2 text-xs text-ui-text-dim">
        loading {program} schedule…
      </div>
    );
  }

  return (
    <div className="rounded border border-ui-border-strong/40 bg-ui-bg-1/40 p-3 text-xs text-ui-text">
      <div className="mb-2 flex items-center justify-between">
        <div className="font-semibold text-ui-text">
          {data.program} — {data.milestone_count} milestones
        </div>
        <div className="text-[10px] text-ui-text-faint">
          curated from public NASA sources
        </div>
      </div>
      <ul className="space-y-1">
        {data.milestones.map((m) => (
          <li key={m.id} className="flex items-start gap-2">
            <div className="font-mono text-[11px] text-ui-text w-20 shrink-0">
              {m.date_iso}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-ui-text">{m.label}</span>
                <span
                  className={`px-1 py-0.5 rounded border text-[9px] uppercase ${
                    CONFIDENCE_COLOR[m.confidence] ?? 'text-ui-text-dim border-ui-border-strong/40'
                  }`}
                >
                  {m.confidence}
                </span>
              </div>
              {!compact && (
                <>
                  <div className="text-ui-text-dim text-[10px]">{m.notes}</div>
                  <div className="text-ui-text-faint text-[10px] italic">{m.source}</div>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default ProgrammeMilestones;
