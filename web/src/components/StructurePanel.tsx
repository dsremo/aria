import { useState, useEffect } from 'react';
import { HullDamagePanel } from './HullDamagePanel';
import { ShieldVisualizer } from './ShieldVisualizer';
import { SubTabBar } from './SubTabBar';

type Sub = 'hull' | 'shield';

const SUBS = [
  { id: 'hull'   as Sub, label: 'Hull Damage' },
  { id: 'shield' as Sub, label: 'Shield Stack' },
];

interface Props {
  initialSub?: Sub;
}

export function StructurePanel({ initialSub }: Props) {
  const [sub, setSub] = useState<Sub>(initialSub ?? 'hull');
  useEffect(() => { if (initialSub) setSub(initialSub); }, [initialSub]);
  return (
    <div className="flex flex-col h-full min-h-0">
      <SubTabBar tabs={SUBS} active={sub} onSelect={setSub} />
      <div className="flex-1 relative min-h-0 overflow-auto">
        {sub === 'hull'   && <HullDamagePanel />}
        {sub === 'shield' && <ShieldVisualizer />}
      </div>
    </div>
  );
}

export default StructurePanel;
