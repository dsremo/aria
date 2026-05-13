import { useState, useEffect } from 'react';
import { MissionTimeline } from './MissionTimeline';
import ReplayPanel from './ReplayPanel';
import { MoonMissionPanel } from './MoonMissionPanel';
import { SubTabBar } from './SubTabBar';

type Sub = 'timeline' | 'replay' | 'moonmission';

const SUBS = [
  { id: 'timeline'    as Sub, label: 'Live Timeline' },
  { id: 'replay'      as Sub, label: 'Replay' },
  { id: 'moonmission' as Sub, label: 'Apollo Replay' },
];

interface Props {
  initialSub?: Sub;
}

export function ChronologyPanel({ initialSub }: Props) {
  const [sub, setSub] = useState<Sub>(initialSub ?? 'timeline');
  useEffect(() => { if (initialSub) setSub(initialSub); }, [initialSub]);
  return (
    <div className="flex flex-col h-full min-h-0">
      <SubTabBar tabs={SUBS} active={sub} onSelect={setSub} />
      <div className="flex-1 relative min-h-0 overflow-auto">
        {sub === 'timeline'    && <MissionTimeline />}
        {sub === 'replay'      && <ReplayPanel />}
        {sub === 'moonmission' && <MoonMissionPanel />}
      </div>
    </div>
  );
}

export default ChronologyPanel;
