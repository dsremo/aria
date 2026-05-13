import { useEffect, useState } from 'react';
import { X, Keyboard } from 'lucide-react';

const SHORTCUTS: { key: string; description: string; section: string }[] = [
  { key: '?',                description: 'Show this help panel',                                 section: 'General' },
  { key: '⌘K / Ctrl-K',      description: 'Jump to any tab (fuzzy search)',                       section: 'General' },
  { key: '⌘, / Ctrl-,',      description: 'Open Settings (notifications, default speed, …)',     section: 'General' },
  { key: 'Escape',           description: 'Close any modal / panel',                              section: 'General' },
  { key: '← / →',            description: 'Move to previous / next tab (when strip is focused)',  section: 'General' },
  { key: 'Home / End',       description: 'Jump to the first / last tab in the strip',            section: 'General' },

  { key: 'F',                description: 'Fit camera to model',                                  section: '3D Viewer' },
  { key: '1',                description: 'Front view',                                           section: '3D Viewer' },
  { key: '3',                description: 'Right view',                                           section: '3D Viewer' },
  { key: '7',                description: 'Top view',                                             section: '3D Viewer' },
  { key: '0',                description: 'Isometric view',                                       section: '3D Viewer' },
  { key: 'R',                description: 'Reset camera orientation',                             section: '3D Viewer' },

  { key: 'Space',            description: 'Play / Pause simulation',                              section: 'Mission' },

  { key: 'Right-click tab',  description: 'Pin tab to the front of the strip (★ marker)',         section: 'Mouse' },
  { key: 'Drag chevron',     description: 'Resize sidebars; click to collapse / expand',          section: 'Mouse' },
];

interface Props {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function KeyboardShortcuts({ open: openProp, onOpenChange }: Props = {}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = openProp ?? internalOpen;
  const setOpen = (v: boolean) => {
    if (onOpenChange) onOpenChange(v);
    else setInternalOpen(v);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tgt = e.target as HTMLElement | null;
      if (tgt && (tgt.tagName === 'INPUT' || tgt.tagName === 'TEXTAREA' || tgt.isContentEditable)) return;
      if (e.key === '?') { setOpen(!open); e.preventDefault(); }
      if (e.key === 'Escape' && open) { setOpen(false); e.preventDefault(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const sections = [...new Set(SHORTCUTS.map(s => s.section))];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
         onClick={() => setOpen(false)}>
      <div className="bg-ui-bg-1 border border-ui-border-strong rounded-xl shadow-2xl w-[min(560px,94vw)] max-h-[86vh] flex flex-col overflow-hidden"
           onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-ui-border bg-ui-bg-1/80">
          <h2 className="text-base font-bold text-ui-accent inline-flex items-center gap-2">
            <Keyboard size={16} aria-hidden /> Keyboard shortcuts
          </h2>
          <button onClick={() => setOpen(false)}
                  aria-label="Close shortcuts"
                  className="text-ui-text-dim hover:text-ui-text p-1 rounded hover:bg-ui-bg-2 transition-colors">
            <X size={16} aria-hidden />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {sections.map(section => (
            <div key={section}>
              <div className="text-[10px] uppercase tracking-widest text-ui-text-faint font-semibold mb-2">
                {section}
              </div>
              <div className="space-y-1">
                {SHORTCUTS.filter(s => s.section === section).map(s => (
                  <div key={s.key + s.description}
                       className="flex items-center justify-between gap-3 px-2 py-1.5 rounded hover:bg-ui-bg-2/40 transition-colors">
                    <span className="text-sm text-ui-text">{s.description}</span>
                    <kbd className="px-2 py-0.5 rounded bg-ui-bg-2 border border-ui-border-strong text-[11px] font-mono text-ui-accent shrink-0 whitespace-nowrap">
                      {s.key}
                    </kbd>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="px-5 py-3 border-t border-ui-border bg-ui-bg-1/60 text-[10px] text-ui-text-faint">
          Press <kbd className="px-1 py-0.5 mx-0.5 text-[9px] border border-ui-border rounded bg-ui-bg-2 text-ui-text">?</kbd>
          to toggle this panel
          <span className="mx-2 opacity-50">·</span>
          <kbd className="px-1 py-0.5 mx-0.5 text-[9px] border border-ui-border rounded bg-ui-bg-2 text-ui-text">Esc</kbd> to close
        </div>
      </div>
    </div>
  );
}
