import { useState, useEffect } from 'react';
import { BomTab } from './BomTab';
import { MassBudgetPanel } from './MassBudgetPanel';
import { SubsystemSizingPanel } from './SubsystemSizingPanel';
import { MassEstimator } from './MassEstimator';
import { SubTabBar } from './SubTabBar';

type Sub = 'bom' | 'mass' | 'sizing' | 'massest';

const SUBS = [
  { id: 'bom'     as Sub, label: 'Bill of Materials' },
  { id: 'mass'    as Sub, label: 'Mass Budget' },
  { id: 'sizing'  as Sub, label: 'Subsystem Sizing' },
  { id: 'massest' as Sub, label: 'Mass Sizing (Phase-A)' },
];

interface Props {
  initialSub?: Sub;
  onSelectPart?: (id: string | null) => void;
}

export function MassSizingPanel({ initialSub, onSelectPart }: Props) {
  const [sub, setSub] = useState<Sub>(initialSub ?? 'bom');
  useEffect(() => { if (initialSub) setSub(initialSub); }, [initialSub]);
  return (
    <div className="flex flex-col h-full min-h-0">
      <SubTabBar tabs={SUBS} active={sub} onSelect={setSub} />
      <div className="flex-1 relative min-h-0 overflow-auto">
        {sub === 'bom'     && <BomTab onSelectPart={onSelectPart ?? (() => {})} />}
        {sub === 'mass'    && <MassBudgetPanel />}
        {sub === 'sizing'  && <SubsystemSizingPanel />}
        {sub === 'massest' && <MassEstimator />}
      </div>
    </div>
  );
}

export default MassSizingPanel;
