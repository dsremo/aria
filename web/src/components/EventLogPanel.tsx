/**
 * Event log streaming from /api/events/recent.
 * Polls every 2 s + auto-scrolls; filterable by topic prefix and severity.
 * Critical events get a red border, warnings yellow, info neutral.
 *
 * 2026-04-24: topic segments are now clickable — clicking "eclss" inside
 * `eclss.contaminant.ethylene.alarm` pivots the filter to `eclss`, so
 * operators can drill into a subsystem without typing.  Per-row "⎘
 * copy" yanks the event as JSON to the clipboard; "export filtered"
 * grabs the whole current view as a JSON file.
 */

import { useEffect, useRef, useState } from 'react';
import { Inbox } from 'lucide-react';
import { ariaApi, type BusEvent } from '../api/aria';
import { EmptyState } from './EmptyState';

const SEVERITY_STYLES: Record<BusEvent['severity'], string> = {
  debug:    'border-ui-border  text-ui-text-faint',
  info:     'border-sev-info   text-ui-text',
  warning:  'border-sev-warn text-sev-warn',
  critical: 'border-sev-crit    text-sev-crit bg-sev-crit/40',
};

export function EventLogPanel() {
  const [events, setEvents]   = useState<BusEvent[]>([]);
  const [topic, setTopic]     = useState('');
  const [minSev, setMinSev]   = useState<'debug'|'info'|'warning'|'critical'>('debug');
  const [paused, setPaused]   = useState(false);
  const [subCount, setSubCount] = useState(0);
  const [copiedAt, setCopiedAt] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const copyToClipboard = async (text: string, tag: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedAt(tag);
      setTimeout(() => setCopiedAt((cur) => (cur === tag ? null : cur)), 1200);
    } catch {
      // Older browsers — fall back to a temporary textarea.
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity  = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); setCopiedAt(tag); } catch { /* nothing else to do */ }
      document.body.removeChild(ta);
    }
  };

  const exportFiltered = () => {
    const blob = new Blob([JSON.stringify(events, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const stem = topic ? topic.replace(/[^\w.-]/g, '_') : 'all';
    a.download = `aria-events-${stem}-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  useEffect(() => {
    if (paused) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await ariaApi.eventsRecent(50, topic || undefined, minSev);
        if (cancelled) return;
        setEvents(r.events);
        setSubCount(r.subscribers);
      } catch (e) { /* ignore transient network errors */ }
    };
    tick();
    const t = setInterval(tick, 2000);
    return () => { cancelled = true; clearInterval(t); };
  }, [topic, minSev, paused]);

  return (
    <div className="p-3 flex flex-col h-full text-xs">
      <div className="flex items-center gap-2 mb-2 text-[10px]">
        <div className="font-bold uppercase tracking-wide text-ui-text-faint">Event Log</div>
        <input value={topic}
               onChange={e => setTopic(e.target.value)}
               placeholder="topic prefix…"
               className="flex-1 px-1.5 py-0.5 bg-ui-bg-2 border border-ui-border rounded text-xs" />
        <select value={minSev}
                onChange={e => setMinSev(e.target.value as any)}
                className="px-1 py-0.5 bg-ui-bg-2 border border-ui-border rounded">
          <option value="debug">debug+</option>
          <option value="info">info+</option>
          <option value="warning">warn+</option>
          <option value="critical">crit</option>
        </select>
        <button onClick={() => setPaused(v => !v)}
                className={`px-2 py-0.5 rounded border ${paused ? 'bg-sev-warn/15 border-sev-warn' : 'bg-ui-bg-2 border-ui-border'}`}>
          {paused ? '▶' : '⏸'}
        </button>
        <button onClick={exportFiltered}
                disabled={events.length === 0}
                title="Download currently filtered events as JSON"
                className="px-2 py-0.5 rounded border border-ui-border bg-ui-bg-2
                           hover:border-ui-accent hover:bg-ui-bg-3 disabled:opacity-40">
          ⇩ export
        </button>
        {topic && (
          <button onClick={() => setTopic('')}
                  title="Clear topic filter"
                  className="px-2 py-0.5 rounded border border-sev-warn bg-sev-warn/30
                             text-sev-warn hover:bg-sev-warn/40">
            ✕ {topic}.*
          </button>
        )}
        <span className="text-ui-text-faint">{events.length} ev · {subCount} subs</span>
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto font-mono space-y-0.5 pr-1">
        {events.length === 0 && (
          <EmptyState Icon={Inbox}
                      title="No events yet"
                      hint="Advance the tick engine or transition mission phase to emit events."
                      size="sm" />
        )}
        {events.map((e, i) => {
          const rowKey = `${e.timestamp}-${e.topic}-${i}`;
          return (
            <div key={rowKey}
                 className={`group px-1.5 py-0.5 border-l-2 ${SEVERITY_STYLES[e.severity]} text-[10.5px] hover:bg-ui-bg-2/40`}>
              <div className="flex items-baseline gap-1.5">
                <span className="text-ui-text-faint w-12 text-right">{formatTs(e.timestamp)}</span>
                <span className="uppercase text-[8px] w-7">{e.severity}</span>
                <span className="flex-1 text-ui-accent truncate">
                  {/* Clickable topic segments — pivot the filter with
                      a single click so operators can drill into a
                      subsystem without typing.  Click the final
                      (leaf) segment to match the event exactly. */}
                  <TopicSegments topic={e.topic} onPick={setTopic} />
                </span>
                <span className="text-ui-text-faint">{e.source}</span>
                <button
                  onClick={() => copyToClipboard(JSON.stringify(e, null, 2), rowKey)}
                  title="Copy event JSON"
                  className="opacity-0 group-hover:opacity-100 px-1 text-ui-text-dim hover:text-ui-accent">
                  {copiedAt === rowKey ? '✓' : '⎘'}
                </button>
              </div>
              {Object.keys(e.payload).length > 0 && (
                <div className="ml-14 text-[9px] text-ui-text-dim">
                  {JSON.stringify(e.payload)}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Render a dotted topic as clickable segments.  Clicking "eclss" in
 *  `eclss.contaminant.ethylene.alarm` pivots the filter to `eclss`,
 *  clicking `contaminant` pivots to `eclss.contaminant`, etc. */
function TopicSegments({ topic, onPick }: { topic: string; onPick: (s: string) => void }) {
  const parts = topic.split('.');
  return (
    <>
      {parts.map((seg, i) => {
        const prefix = parts.slice(0, i + 1).join('.');
        return (
          <span key={i}>
            {i > 0 && <span className="text-ui-text-faint">.</span>}
            <button
              onClick={() => onPick(prefix)}
              className="hover:underline hover:text-ui-accent"
              title={`Filter to ${prefix}.*`}>
              {seg}
            </button>
          </span>
        );
      })}
    </>
  );
}

function formatTs(unixSec: number): string {
  const d = new Date(unixSec * 1000);
  return d.toLocaleTimeString('en-GB', { hour12: false });
}
