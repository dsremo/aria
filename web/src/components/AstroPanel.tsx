import { useState, useEffect } from 'react';
import { Planetarium } from './Planetarium';
import { SolarSystem3D } from './SolarSystem3D';
import { SkyTonightPanel } from './SkyTonightPanel';
import { AstroEventsPanel } from './AstroEventsPanel';
import { CatalogsPanel } from './CatalogsPanel';
import { SubTabBar } from './SubTabBar';

type Sub = 'planetarium' | 'orbits3d' | 'skytonight' | 'astroevents' | 'catalogs';

const SUBS = [
  { id: 'planetarium' as Sub, label: 'Planetarium' },
  { id: 'orbits3d'    as Sub, label: 'Solar System 3D' },
  { id: 'skytonight'  as Sub, label: 'Sky Tonight' },
  { id: 'astroevents' as Sub, label: 'Astro Events' },
  { id: 'catalogs'    as Sub, label: 'Catalogs' },
];

interface Props {
  initialSub?: Sub;
}

export function AstroPanel({ initialSub }: Props) {
  const [sub, setSub] = useState<Sub>(initialSub ?? 'planetarium');
  useEffect(() => { if (initialSub) setSub(initialSub); }, [initialSub]);
  return (
    <div className="flex flex-col h-full min-h-0">
      <SubTabBar tabs={SUBS} active={sub} onSelect={setSub} />
      <div className="flex-1 relative min-h-0 overflow-auto">
        {sub === 'planetarium' && <Planetarium />}
        {sub === 'orbits3d'    && <SolarSystem3D />}
        {sub === 'skytonight'  && <SkyTonightPanel />}
        {sub === 'astroevents' && <AstroEventsPanel />}
        {sub === 'catalogs'    && <CatalogsPanel />}
      </div>
    </div>
  );
}

export default AstroPanel;
