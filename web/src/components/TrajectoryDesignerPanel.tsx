import { useState, useEffect } from 'react';
import { TrajectoryPanel } from './TrajectoryPanel';
import { LunarMissionPanel } from './LunarMissionPanel';
import { MarsTransferPlanner } from './MarsTransferPlanner';
import { MissionPlannerPanel } from './MissionPlannerPanel';
import { MissionDesignPanel } from './MissionDesignPanel';
import { PorkchopPanel } from './PorkchopPanel';
import { MissionStudio } from './MissionStudio';
import { SubTabBar } from './SubTabBar';

type Sub = 'trajectory' | 'lunar' | 'mars' | 'planner' | 'missiondesign' | 'porkchop' | 'studio';

const SUBS = [
  { id: 'trajectory'    as Sub, label: 'Trajectory' },
  { id: 'lunar'         as Sub, label: 'Moon Vehicle' },
  { id: 'mars'          as Sub, label: 'Mars Transfer' },
  { id: 'planner'       as Sub, label: 'Route Planner' },
  { id: 'missiondesign' as Sub, label: 'Transfer Designer' },
  { id: 'porkchop'      as Sub, label: 'Porkchop' },
  { id: 'studio'        as Sub, label: 'Mission Studio' },
];

interface Props {
  initialSub?: Sub;
}

export function TrajectoryDesignerPanel({ initialSub }: Props) {
  const [sub, setSub] = useState<Sub>(initialSub ?? 'trajectory');
  useEffect(() => { if (initialSub) setSub(initialSub); }, [initialSub]);
  return (
    <div className="flex flex-col h-full min-h-0">
      <SubTabBar tabs={SUBS} active={sub} onSelect={setSub} scrollable />
      <div className="flex-1 relative min-h-0 overflow-auto">
        {sub === 'trajectory'    && <TrajectoryPanel />}
        {sub === 'lunar'         && <LunarMissionPanel />}
        {sub === 'mars'          && <MarsTransferPlanner />}
        {sub === 'planner'       && <MissionPlannerPanel />}
        {sub === 'missiondesign' && <MissionDesignPanel />}
        {sub === 'porkchop'      && <PorkchopPanel />}
        {sub === 'studio'        && <MissionStudio />}
      </div>
    </div>
  );
}

export default TrajectoryDesignerPanel;
