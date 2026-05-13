/**
 * Save / Load / Share for assembled ships.
 *
 * Saves the current assembly to /api/ship/assembly/save which writes
 * the JSON to data/assemblies/<uid>.json and returns a 12-char hex uid
 * the user can share via ?assembly=<uid>.
 *
 * Loading on mount: if the URL carries ?assembly=<uid>, hydrate the
 * store from /api/ship/assembly/load/<uid>.
 *
 * Roadmap Track 2 Phase 5.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type AssemblyListEntry, type AssemblyPartRecord } from '../../api/aria';
import { useAssembly } from './AssemblyStore';

function copyToClipboard(s: string): Promise<void> {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(s);
  // Fallback for very old browsers
  return Promise.resolve();
}

export function SaveLoadBar() {
  const placed = useAssembly((s) => s.placed);
  const loadFromRecord = useAssembly((s) => s.loadFromRecord);
  const [name, setName] = useState('');
  const [list, setList] = useState<AssemblyListEntry[]>([]);
  const [hint, setHint] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshList = async () => {
    try {
      const r = await ariaApi.assemblyList();
      setList(r.assemblies);
    } catch {
      setList([]);
    }
  };

  // Deep-link: hydrate from ?assembly=<uid> on mount.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const uid = params.get('assembly');
    if (uid) {
      ariaApi
        .assemblyLoad(uid)
        .then((rec) => {
          loadFromRecord(rec.parts as AssemblyPartRecord[]);
          setHint(`loaded "${rec.name}"`);
          window.setTimeout(() => setHint(null), 2500);
        })
        .catch((e: Error) => setHint(`load failed: ${e.message}`));
    }
    refreshList();
  }, [loadFromRecord]);

  const onSave = async () => {
    if (placed.length === 0 || busy) return;
    setBusy(true);
    try {
      const r = await ariaApi.assemblySave(name || 'untitled', placed as AssemblyPartRecord[]);
      const url = `${window.location.origin}${window.location.pathname}?assembly=${r.uid}`;
      await copyToClipboard(url);
      setHint(`saved as ${r.uid} — share link copied`);
      window.history.replaceState(null, '', `?assembly=${r.uid}`);
      await refreshList();
    } catch (e) {
      setHint(`save failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
      window.setTimeout(() => setHint(null), 3500);
    }
  };

  const onLoad = async (uid: string) => {
    if (busy) return;
    setBusy(true);
    try {
      const rec = await ariaApi.assemblyLoad(uid);
      loadFromRecord(rec.parts as AssemblyPartRecord[]);
      setName(rec.name);
      setHint(`loaded "${rec.name}"`);
      window.history.replaceState(null, '', `?assembly=${uid}`);
    } catch (e) {
      setHint(`load failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
      window.setTimeout(() => setHint(null), 2500);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1">
        <input
          type="text"
          value={name}
          placeholder="assembly name"
          onChange={(e) => setName(e.target.value)}
          className="flex-1 min-w-0 bg-ui-bg-0 border border-ui-border rounded text-xs text-ui-text px-2 py-1"
        />
        <button
          type="button"
          onClick={onSave}
          disabled={placed.length === 0 || busy}
          className="text-xs px-2 py-1 rounded border border-sev-ok/40 text-sev-ok hover:bg-sev-ok/40 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Save
        </button>
      </div>
      {hint && <div className="text-[10px] text-ui-accent">{hint}</div>}
      {list.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-widest text-ui-text-faint mb-1">
            Saved ({list.length})
          </div>
          <ul className="space-y-0.5 max-h-28 overflow-y-auto text-[11px]">
            {list.slice(0, 12).map((a) => (
              <li
                key={a.uid}
                className="flex items-center justify-between gap-2 hover:bg-ui-bg-2/40 rounded px-1 cursor-pointer"
                onClick={() => onLoad(a.uid)}
                title={`load ${a.uid}`}
              >
                <span className="truncate text-ui-text">{a.name || a.uid}</span>
                <span className="text-[10px] text-ui-text-faint font-mono">
                  {a.parts_count}p
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default SaveLoadBar;
