import { useState, useEffect } from 'react';
import { AIAdvisorPanel } from './AIAdvisorPanel';
import { AIDecisionsPanel } from './AIDecisionsPanel';
import { AiActionsPanel } from './AiActionsPanel';
import { SubTabBar } from './SubTabBar';

type Sub = 'advisor' | 'decisions' | 'actions';

const SUBS = [
  { id: 'advisor'   as Sub, label: 'Advisor' },
  { id: 'decisions' as Sub, label: 'Decisions' },
  { id: 'actions'   as Sub, label: 'Actions' },
];

interface Props {
  initialSub?: Sub;
}

export function AIConsolePanel({ initialSub }: Props) {
  const [sub, setSub] = useState<Sub>(initialSub ?? 'advisor');
  useEffect(() => {
    if (initialSub) setSub(initialSub);
  }, [initialSub]);
  return (
    <div className="flex flex-col h-full min-h-0">
      <SubTabBar tabs={SUBS} active={sub} onSelect={setSub} />
      <div className="flex-1 relative min-h-0 overflow-auto">
        {sub === 'advisor'   && <AIAdvisorPanel />}
        {sub === 'decisions' && <AIDecisionsPanel />}
        {sub === 'actions'   && <AiActionsPanel />}
      </div>
    </div>
  );
}

export default AIConsolePanel;
