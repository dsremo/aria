/**
 * Cmd-K / Ctrl-K fuzzy tab switcher.
 *
 * Opens a modal with a search box. Typing filters the 50 tabs by label
 * and hint keywords. Arrow keys move the cursor, Enter picks. Escape
 * closes. Follows the same input-field guard as KeyboardShortcuts so it
 * doesn't hijack typing inside form controls.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import type { Tab } from '../App';

interface Entry {
  id: Tab;
  label: string;
  group: string;
  hints?: string;
}

// Very light subsequence match — "ppf" finds "PowerFlow", "msnctl"
// finds "Mission Control". Scores higher for hits in label than hints.
// BUG-029 (2026-04-24, walkthrough): hand-maintained synonyms so typing
// a common term ranks the semantically-correct panel at the top.  Was:
// `fuel` ranked "Interstellar Route Planner" and "Porkchop" above
// "Propellant" because both subsequence-match `f...u...e...l` in their
// hints.  Now: explicit synonym → label match gets the highest score.
const SYNONYMS: Record<string, string[]> = {
  fuel:     ['EECOM'],
  tank:     ['EECOM'],
  sankey:   ['EECOM'],
  dose:     ['EECOM'],
  rem:      ['EECOM'],
  sievert:  ['EECOM'],
  co2:      ['EECOM'],
  o2:       ['EECOM'],
  scrubber: ['EECOM'],
  heart:    ['Crew & Life'],
  bone:     ['Crew & Life'],
  eva:      ['Crew & Life', 'EECOM'],
  food:     ['Crew & Life'],
  crop:     ['Crew & Life'],
  eclipse:  ['Astro'],
  perigee:  ['Astro'],
  flare:    ['Tracking'],
  storm:    ['Tracking'],
  iss:      ['Tracking'],
  launch:   ['Mission Control'],
  play:     ['Mission Control'],
  pause:    ['Mission Control'],
  burn:     ['EECOM', 'Mission Control'],
  apollo:   ['Chronology'],
  artemis:  ['Chronology'],
  lander:   ['Trajectory Design'],
  porkchop: ['Trajectory Design'],
};

function score(entry: Entry, q: string): number {
  if (!q) return 0;
  const needle = q.toLowerCase();
  const label = entry.label.toLowerCase();
  const hints = (entry.hints ?? '').toLowerCase();
  const hay = `${label} ${entry.group.toLowerCase()} ${hints}`;

  // Synonym boost — exact needle → synonym-target wins unconditionally.
  const synTargets = SYNONYMS[needle];
  if (synTargets && synTargets.some(t => t.toLowerCase() === label)) {
    return 150;
  }

  // Exact substring = high
  if (label.startsWith(needle)) return 100;
  if (label.includes(needle))   return 70;
  if (hay.includes(needle))     return 50;

  // Subsequence: every char in needle appears in label in order
  let j = 0;
  for (let i = 0; i < label.length && j < needle.length; i++) {
    if (label[i] === needle[j]) j++;
  }
  if (j === needle.length) return 25;

  // Fallback: subsequence in full hay
  j = 0;
  for (let i = 0; i < hay.length && j < needle.length; i++) {
    if (hay[i] === needle[j]) j++;
  }
  return j === needle.length ? 10 : 0;
}

export function CommandPalette({
  tabs, onPick,
}: {
  tabs: readonly Entry[];
  onPick: (t: Tab) => void;
}) {
  const [open, setOpen]     = useState(false);
  const [query, setQuery]   = useState('');
  const [cursor, setCursor] = useState(0);
  const inputRef            = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tgt = e.target as HTMLElement | null;
      const inField = !!tgt && (tgt.tagName === 'INPUT' || tgt.tagName === 'TEXTAREA' || tgt.isContentEditable);

      // Cmd-K or Ctrl-K opens from anywhere, even inside an input.
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        setOpen((v) => !v);
        setQuery('');
        setCursor(0);
        e.preventDefault();
        return;
      }
      if (!open) return;
      if (e.key === 'Escape') { setOpen(false); e.preventDefault(); return; }

      // Navigation inside the palette.
      if (inField && tgt === inputRef.current) {
        // Allow typing; handle nav keys explicitly.
      }
      if (e.key === 'ArrowDown') {
        setCursor((c) => Math.min(c + 1, results.length - 1));
        e.preventDefault();
      } else if (e.key === 'ArrowUp') {
        setCursor((c) => Math.max(c - 1, 0));
        e.preventDefault();
      } else if (e.key === 'Enter') {
        if (results[cursor]) {
          onPick(results[cursor].id);
          setOpen(false);
        }
        e.preventDefault();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, cursor, query, tabs]);

  // Focus the input whenever the palette opens.
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  const results = useMemo(() => {
    if (!query.trim()) return tabs.slice(0, 15) as Entry[];
    return tabs
      .map((t) => ({ t, s: score(t, query.trim()) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 15)
      .map((x) => x.t);
  }, [query, tabs]);

  // Keep cursor in-bounds when result set shrinks.
  useEffect(() => { setCursor(0); }, [query]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/50 backdrop-blur-sm"
      onClick={() => setOpen(false)}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-[92vw] max-w-xl bg-ui-bg-1 border border-ui-border rounded-lg shadow-2xl overflow-hidden"
      >
        <div className="flex items-center gap-2 px-3 py-2 border-b border-ui-border">
          <span className="text-ui-text-faint text-xs">⌘K</span>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Jump to tab — type to search ${tabs.length} panels…`}
            className="flex-1 bg-transparent outline-none text-sm text-ui-text placeholder:text-ui-text-faint"
          />
          <span className="text-[10px] text-ui-text-faint">Esc to close</span>
        </div>
        <div className="max-h-80 overflow-y-auto">
          {results.length === 0 && (
            <div className="px-4 py-6 text-center text-xs text-ui-text-faint">No matching panels.</div>
          )}
          {results.map((t, i) => (
            <button
              key={t.id}
              onMouseEnter={() => setCursor(i)}
              onClick={() => { onPick(t.id); setOpen(false); }}
              className={`w-full flex items-center justify-between px-3 py-2 text-left text-sm transition-colors ${
                i === cursor ? 'bg-ui-accent/20 text-ui-accent' : 'text-ui-text hover:bg-ui-bg-2'
              }`}
            >
              <span className="truncate">{t.label}</span>
              <span className="text-[10px] text-ui-text-faint uppercase tracking-wider">{t.group}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
