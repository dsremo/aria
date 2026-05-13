import { useState, useEffect } from 'react';
import { Satellites3D } from './Satellites3D';
import { GroundTrackPanel } from './GroundTrackPanel';
import { TLEParserPanel } from './TLEParserPanel';
import { DsnNowPanel } from './DsnNowPanel';
import { SpaceWeatherPanel } from './SpaceWeatherPanel';
import { ConstellationVisualizer } from './ConstellationVisualizer';
import { SubTabBar } from './SubTabBar';

type Sub = 'sats3d' | 'groundtrack' | 'tleparser' | 'dsn' | 'spaceweather' | 'constellation';

const SUBS = [
  { id: 'sats3d'        as Sub, label: 'Satellites 3D' },
  { id: 'groundtrack'   as Sub, label: 'Ground Track' },
  { id: 'tleparser'     as Sub, label: 'TLE Parser' },
  { id: 'dsn'           as Sub, label: 'DSN Live' },
  { id: 'spaceweather'  as Sub, label: 'Space Weather' },
  { id: 'constellation' as Sub, label: 'Constellation' },
];

interface Props {
  initialSub?: Sub;
}

export function TrackingPanel({ initialSub }: Props) {
  const [sub, setSub] = useState<Sub>(initialSub ?? 'sats3d');
  useEffect(() => { if (initialSub) setSub(initialSub); }, [initialSub]);
  return (
    <div className="flex flex-col h-full min-h-0">
      <SubTabBar tabs={SUBS} active={sub} onSelect={setSub} scrollable />
      <div className="flex-1 relative min-h-0 overflow-auto">
        {sub === 'sats3d'        && <Satellites3D />}
        {sub === 'groundtrack'   && <GroundTrackPanel />}
        {sub === 'tleparser'     && <TLEParserPanel />}
        {sub === 'dsn'           && <DsnNowPanel />}
        {sub === 'spaceweather'  && <SpaceWeatherPanel />}
        {sub === 'constellation' && <ConstellationVisualizer />}
      </div>
    </div>
  );
}

export default TrackingPanel;
