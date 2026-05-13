import { useState, useEffect } from 'react';
import { ShipBuilder } from './ShipBuilder';
import { ShipAssembler } from './ShipAssembler';
import { ShipCrossSection } from './ShipCrossSection';
import { DepGraphViz } from './DepGraphViz';
import { SubTabBar } from './SubTabBar';

type Sub = 'builder' | 'assembler' | 'crosssection' | 'graph';

const SUBS = [
  { id: 'builder'      as Sub, label: 'Ship Builder' },
  { id: 'assembler'    as Sub, label: 'Ship Assembler' },
  { id: 'crosssection' as Sub, label: 'Cross-Section' },
  { id: 'graph'        as Sub, label: 'Dependency Map' },
];

interface Props {
  initialSub?: Sub;
  onRebuilt: () => void;
  selectedPartId: string | null;
  onSelectPart: (id: string | null) => void;
}

export function ShipBuildPanel({ initialSub, onRebuilt, selectedPartId, onSelectPart }: Props) {
  const [sub, setSub] = useState<Sub>(initialSub ?? 'builder');
  useEffect(() => { if (initialSub) setSub(initialSub); }, [initialSub]);
  return (
    <div className="flex flex-col h-full min-h-0">
      <SubTabBar tabs={SUBS} active={sub} onSelect={setSub} />
      <div className="flex-1 relative min-h-0 overflow-auto">
        {sub === 'builder'      && <ShipBuilder onRebuilt={onRebuilt} />}
        {sub === 'assembler'    && <ShipAssembler />}
        {sub === 'crosssection' && <ShipCrossSection onSelectPart={onSelectPart} />}
        {sub === 'graph'        && <DepGraphViz selectedPartId={selectedPartId} onSelectPart={onSelectPart} />}
      </div>
    </div>
  );
}

export default ShipBuildPanel;
