import { useState, useEffect } from 'react';
import { EventLogPanel } from './EventLogPanel';
import { IncidentPanel } from './IncidentPanel';
import { AlarmsPanel } from './AlarmsPanel';
import { CaptainsLogPanel } from './CaptainsLogPanel';
import { ObjectivesPanel } from './ObjectivesPanel';
import { SubTabBar } from './SubTabBar';

type Sub = 'events' | 'incidents' | 'alarms' | 'log' | 'objectives';

const SUBS = [
  { id: 'events'     as Sub, label: 'Event Log' },
  { id: 'incidents'  as Sub, label: 'Incidents' },
  { id: 'alarms'     as Sub, label: 'Alarms' },
  { id: 'log'        as Sub, label: "Captain's Log" },
  { id: 'objectives' as Sub, label: 'Objectives' },
];

interface Props {
  initialSub?: Sub;
}

export function OperationsLogPanel({ initialSub }: Props) {
  const [sub, setSub] = useState<Sub>(initialSub ?? 'events');
  useEffect(() => { if (initialSub) setSub(initialSub); }, [initialSub]);
  return (
    <div className="flex flex-col h-full min-h-0">
      <SubTabBar tabs={SUBS} active={sub} onSelect={setSub} />
      <div className="flex-1 relative min-h-0 overflow-auto">
        {sub === 'events'     && <EventLogPanel />}
        {sub === 'incidents'  && <IncidentPanel />}
        {sub === 'alarms'     && <AlarmsPanel />}
        {sub === 'log'        && <CaptainsLogPanel />}
        {sub === 'objectives' && <ObjectivesPanel />}
      </div>
    </div>
  );
}

export default OperationsLogPanel;
