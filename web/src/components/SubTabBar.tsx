import { useEffect, useRef, useState } from 'react';

interface SubEntry<Id extends string> {
  id: Id;
  label: string;
}

interface Props<Id extends string> {
  tabs: ReadonlyArray<SubEntry<Id>>;
  active: Id;
  onSelect: (id: Id) => void;
  scrollable?: boolean;
}

export function SubTabBar<Id extends string>({ tabs, active, onSelect, scrollable }: Props<Id>) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [overflow, setOverflow] = useState<{ left: boolean; right: boolean }>({ left: false, right: false });

  useEffect(() => {
    if (!scrollable) return;
    const el = containerRef.current;
    if (!el) return;
    const measure = () => {
      setOverflow({
        left:  el.scrollLeft > 4,
        right: el.scrollLeft + el.clientWidth < el.scrollWidth - 4,
      });
    };
    measure();
    el.addEventListener('scroll', measure, { passive: true });
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    ro?.observe(el);
    return () => { el.removeEventListener('scroll', measure); ro?.disconnect(); };
  }, [scrollable, tabs.length]);

  return (
    <div className="relative">
      <div ref={containerRef}
           className={`flex border-b border-ui-border bg-ui-bg-1/60 text-xs ${scrollable ? 'overflow-x-auto' : ''}`}>
        {tabs.map((entry) => (
          <button
            key={entry.id}
            onClick={() => onSelect(entry.id)}
            className={`px-3 py-1.5 border-b-2 transition-colors whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ui-accent focus-visible:ring-inset
              ${active === entry.id
                ? 'border-ui-accent text-ui-accent bg-ui-bg-2/60'
                : 'border-transparent text-ui-text-dim hover:text-ui-text hover:bg-ui-bg-2/30'}`}
          >
            {entry.label}
          </button>
        ))}
      </div>
      {scrollable && overflow.left && (
        <div className="pointer-events-none absolute inset-y-0 left-0 w-6 bg-gradient-to-r from-ui-bg-1 to-transparent" aria-hidden />
      )}
      {scrollable && overflow.right && (
        <div className="pointer-events-none absolute inset-y-0 right-0 w-6 bg-gradient-to-l from-ui-bg-1 to-transparent" aria-hidden />
      )}
    </div>
  );
}

export default SubTabBar;
