import { useState, useEffect } from 'react';
import { FMEAPanel } from './FMEAPanel';
import { CascadeSimulator } from './CascadeSimulator';
import { RandomEventsPanel } from './RandomEventsPanel';
import { SubTabBar } from './SubTabBar';

type Sub = 'fmea' | 'cascade' | 'randevents';

const SUBS = [
  { id: 'fmea'       as Sub, label: 'FMEA' },
  { id: 'cascade'    as Sub, label: 'Cascade Sim' },
  { id: 'randevents' as Sub, label: 'Random Events' },
];

interface Props {
  initialSub?: Sub;
}

export function FailureAnalysisPanel({ initialSub }: Props) {
  const [sub, setSub] = useState<Sub>(initialSub ?? 'fmea');
  useEffect(() => { if (initialSub) setSub(initialSub); }, [initialSub]);
  return (
    <div className="flex flex-col h-full min-h-0">
      <SubTabBar tabs={SUBS} active={sub} onSelect={setSub} />
      <div className="flex-1 relative min-h-0 overflow-auto">
        {sub === 'fmea'       && <FMEAPanel />}
        {sub === 'cascade'    && <CascadeSimulator />}
        {sub === 'randevents' && <RandomEventsPanel />}
      </div>
    </div>
  );
}

export default FailureAnalysisPanel;
