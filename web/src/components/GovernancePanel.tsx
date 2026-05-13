import { useState, useEffect } from 'react';
import { SafetyConsole } from './SafetyConsole';
import { AdminPanel } from './AdminPanel';
import { SubTabBar } from './SubTabBar';

type Sub = 'safety' | 'admin';

const SUBS = [
  { id: 'safety' as Sub, label: 'Safety Console' },
  { id: 'admin'  as Sub, label: 'Admin' },
];

interface Props {
  initialSub?: Sub;
}

export function GovernancePanel({ initialSub }: Props) {
  const [sub, setSub] = useState<Sub>(initialSub ?? 'safety');
  useEffect(() => { if (initialSub) setSub(initialSub); }, [initialSub]);
  return (
    <div className="flex flex-col h-full min-h-0">
      <SubTabBar tabs={SUBS} active={sub} onSelect={setSub} />
      <div className="flex-1 relative min-h-0 overflow-auto">
        {sub === 'safety' && <SafetyConsole />}
        {sub === 'admin'  && <AdminPanel />}
      </div>
    </div>
  );
}

export default GovernancePanel;
