import { useState, useEffect } from 'react';
import { SubsystemPanels } from './SubsystemPanels';
import { PowerFlowDiagram } from './PowerFlowDiagram';
import { PropellantGraph } from './PropellantGraph';
import { ReactorDisplay } from './ReactorDisplay';
import { AtmosphereMonitor } from './AtmosphereMonitor';
import { BearingVisualizer } from './BearingVisualizer';
import { CommsLinkBudget } from './CommsLinkBudget';
import { RadiationTracker } from './RadiationTracker';
import { OperationsPanel } from './OperationsPanel';
import { SubTabBar } from './SubTabBar';

type Sub = 'subsystems' | 'powerflow' | 'propellant' | 'reactor' | 'atmosphere' | 'bearing' | 'commslink' | 'radiation' | 'ops';

const SUBS = [
  { id: 'subsystems' as Sub, label: 'Subsystems' },
  { id: 'powerflow'  as Sub, label: 'Power Flow' },
  { id: 'propellant' as Sub, label: 'Propellant' },
  { id: 'reactor'    as Sub, label: 'Reactor' },
  { id: 'atmosphere' as Sub, label: 'Atmosphere' },
  { id: 'bearing'    as Sub, label: 'Bearing' },
  { id: 'commslink'  as Sub, label: 'Comms Link' },
  { id: 'radiation'  as Sub, label: 'Radiation' },
  { id: 'ops'        as Sub, label: 'Operations' },
];

interface Props {
  initialSub?: Sub;
}

export function EecomConsolePanel({ initialSub }: Props) {
  const [sub, setSub] = useState<Sub>(initialSub ?? 'subsystems');
  useEffect(() => { if (initialSub) setSub(initialSub); }, [initialSub]);
  return (
    <div className="flex flex-col h-full min-h-0">
      <SubTabBar tabs={SUBS} active={sub} onSelect={setSub} scrollable />
      <div className="flex-1 relative min-h-0 overflow-auto">
        {sub === 'subsystems' && <SubsystemPanels />}
        {sub === 'powerflow'  && <PowerFlowDiagram />}
        {sub === 'propellant' && <PropellantGraph />}
        {sub === 'reactor'    && <ReactorDisplay />}
        {sub === 'atmosphere' && <AtmosphereMonitor />}
        {sub === 'bearing'    && <BearingVisualizer />}
        {sub === 'commslink'  && <CommsLinkBudget />}
        {sub === 'radiation'  && <RadiationTracker />}
        {sub === 'ops'        && <OperationsPanel />}
      </div>
    </div>
  );
}

export default EecomConsolePanel;
