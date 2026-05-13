import { useState, useEffect } from 'react';
import { CrewPopulationChart } from './CrewPopulationChart';
import { AgricultureDashboard } from './AgricultureDashboard';
import { SubTabBar } from './SubTabBar';

type Sub = 'crewpop' | 'agri';

const SUBS = [
  { id: 'crewpop' as Sub, label: 'Crew Health' },
  { id: 'agri'    as Sub, label: 'Agriculture' },
];

interface Props {
  initialSub?: Sub;
}

export function CrewLifePanel({ initialSub }: Props) {
  const [sub, setSub] = useState<Sub>(initialSub ?? 'crewpop');
  useEffect(() => { if (initialSub) setSub(initialSub); }, [initialSub]);
  return (
    <div className="flex flex-col h-full min-h-0">
      <SubTabBar tabs={SUBS} active={sub} onSelect={setSub} />
      <div className="flex-1 relative min-h-0 overflow-auto">
        {sub === 'crewpop' && <CrewPopulationChart />}
        {sub === 'agri'    && <AgricultureDashboard />}
      </div>
    </div>
  );
}

export default CrewLifePanel;
