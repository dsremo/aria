import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ChevronDown, Check, Search } from 'lucide-react';
import { ariaApi, type FailureScenarioInfo } from '../api/aria';

const SEV_COLOR: Record<string, string> = {
  info:      'text-sev-info',
  warning:   'text-sev-warn',
  critical:  'text-sev-crit',
  emergency: 'text-sev-crit',
};

export function DrillMenu() {
  const [open, setOpen] = useState(false);
  const [list, setList] = useState<FailureScenarioInfo[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [last, setLast] = useState<{ id: string; ok: boolean; ts: number } | null>(null);
  const [query, setQuery] = useState('');
  const ref = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  const filtered = useMemo(() => {
    if (!query.trim()) return list;
    const q = query.trim().toLowerCase();
    return list.filter((sc) =>
      sc.label.toLowerCase().includes(q) ||
      sc.id.toLowerCase().includes(q) ||
      sc.description.toLowerCase().includes(q) ||
      sc.severity.toLowerCase().includes(q)
    );
  }, [list, query]);

  useEffect(() => {
    if (!open) return;
    if (list.length > 0) return;
    ariaApi.failureScenarios().then((r) => setList(r.scenarios)).catch(() => {});
  }, [open, list.length]);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('mousedown', onClick);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', onClick);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const fire = async (id: string) => {
    setBusy(id);
    try {
      await ariaApi.failureTrigger(id);
      setLast({ id, ok: true, ts: Date.now() });
    } catch {
      setLast({ id, ok: false, ts: Date.now() });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        title="Drill — inject a failure scenario for testing AI / alarms / cascade"
        aria-haspopup="menu"
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-sev-warn bg-sev-warn/15 text-ui-text hover:bg-sev-warn/25 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sev-warn focus-visible:ring-offset-1 focus-visible:ring-offset-ui-bg-1"
      >
        <AlertTriangle size={14} aria-hidden />
        <span className="hidden md:inline">Drill</span>
        <ChevronDown size={12} aria-hidden />
      </button>

      {open && (
        <div role="menu"
             className="absolute right-0 top-full mt-1 w-80 max-h-96 overflow-y-auto rounded-lg border border-ui-border-strong bg-ui-bg-1 shadow-2xl z-50">
          <div className="px-3 py-2 border-b border-ui-border-soft">
            <div className="text-[10px] uppercase tracking-wider text-sev-warn font-bold">Failure Drill</div>
            <div className="text-[10px] text-ui-text-faint mt-0.5">
              Click a scenario to inject. Fires alarms + advisory + (if anomalous) AI action.
            </div>
          </div>
          {list.length > 4 && (
            <div className="px-2 py-1.5 border-b border-ui-border-soft sticky top-0 bg-ui-bg-1 z-10">
              <div className="relative">
                <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-ui-text-faint pointer-events-none" aria-hidden />
                <input ref={inputRef}
                       type="text"
                       value={query}
                       onChange={(e) => setQuery(e.target.value)}
                       placeholder={`Filter ${list.length} scenarios…`}
                       className="w-full pl-7 pr-2 py-1 text-[11px] rounded bg-ui-bg-2 border border-ui-border text-ui-text placeholder:text-ui-text-faint focus:border-ui-accent focus:outline-none" />
              </div>
            </div>
          )}
          {list.length === 0 ? (
            <div className="px-3 py-4 text-xs text-ui-text-faint">Loading scenarios…</div>
          ) : filtered.length === 0 ? (
            <div className="px-3 py-4 text-xs text-ui-text-faint italic">No scenarios match "{query}".</div>
          ) : (
            <ul role="menu" className="divide-y divide-ui-border-soft">
              {filtered.map((sc) => {
                const wasJust = last?.id === sc.id && Date.now() - last.ts < 4000;
                return (
                  <li key={sc.id} role="none">
                    <button
                      role="menuitem"
                      onClick={() => fire(sc.id)}
                      disabled={busy === sc.id}
                      className="w-full text-left px-3 py-2 hover:bg-ui-bg-2/60 disabled:opacity-50 transition-colors group"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-ui-text">{sc.label}</span>
                        <span className={`text-[9px] uppercase tracking-wider ${SEV_COLOR[sc.severity] ?? 'text-ui-text-faint'}`}>
                          {sc.severity}
                        </span>
                      </div>
                      <div className="text-[10px] text-ui-text-dim mt-0.5">{sc.description}</div>
                      <div className="text-[10px] text-ui-text-faint mt-0.5 italic">→ {sc.impact}</div>
                      {wasJust && (
                        <div className={`flex items-center gap-1 text-[10px] mt-1 ${last.ok ? 'text-sev-ok' : 'text-sev-crit'}`}>
                          <Check size={10} aria-hidden /> {last.ok ? 'injected — see Alarms / AI tabs' : 'inject failed'}
                        </div>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          <div className="px-3 py-2 text-[10px] text-ui-text-faint border-t border-ui-border-soft">
            Effects show up in Ops Log → Alarms / Event Log, AI Console → Advisor / Decisions / Actions.
          </div>
        </div>
      )}
    </div>
  );
}

export default DrillMenu;
