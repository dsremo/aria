/**
 * Top-level layout:
 *   ┌────────────┬─────────────────────────────┬─────────────┐
 *   │ Parts List │ MAIN VIEW (tabbed):         │ Part Panel  │
 *   │ (by subsys)│  · 3D viewport              │             │
 *   │            │  · Dependency graph         │             │
 *   │            │  · Event log                │             │
 *   │            │  · Subsystem diagnostics    │             │
 *   ├────────────┴─────────────────────────────┴─────────────┤
 *   │ Mission Panel  │ Startup Panel                         │
 *   └────────────────┴───────────────────────────────────────┘
 */

import React, { useEffect, useState } from 'react';
import { safeStorage } from './safeStorage';
import { Ship3D } from './components/Ship3D';
import { PartPanel } from './components/PartPanel';
import { PartsList } from './components/PartsList';
import { MissionPanel } from './components/MissionPanel';
import { StartupPanel } from './components/StartupPanel';
import { MissionControlPanel } from './components/MissionControlPanel';
import { ViewerToolbar, type CameraPreset, type ZoomAction } from './components/ViewerToolbar';
import { TelemetryDashboard } from './components/TelemetryDashboard';
import { ToastNotifications } from './components/ToastNotifications';
import { KeyboardShortcuts } from './components/KeyboardShortcuts';
import { MissionExport } from './components/MissionExport';
import { LoginPanel } from './components/LoginPanel';
import { AIConsolePanel } from './components/AIConsolePanel';
import { OperationsLogPanel } from './components/OperationsLogPanel';
import { FailureAnalysisPanel } from './components/FailureAnalysisPanel';
import { ChronologyPanel } from './components/ChronologyPanel';
import { TrajectoryDesignerPanel } from './components/TrajectoryDesignerPanel';
import { ShipBuildPanel } from './components/ShipBuildPanel';
import { MassSizingPanel } from './components/MassSizingPanel';
import { StructurePanel } from './components/StructurePanel';
import { EecomConsolePanel } from './components/EecomConsolePanel';
import { CrewLifePanel } from './components/CrewLifePanel';
import { AstroPanel } from './components/AstroPanel';
import { TrackingPanel } from './components/TrackingPanel';
import { GovernancePanel } from './components/GovernancePanel';
import KnowledgePanel from './components/KnowledgePanel';
import { HomePanel } from './components/HomePanel';
import { StatusStrip } from './components/StatusStrip';
import { CommandPalette } from './components/CommandPalette';
import { ariaApi } from './api/aria';
import { Save, FolderOpen, Sun, Moon, Activity, Maximize2, Minimize2, X, PanelRightOpen, PanelRightClose, ChevronDown, ChevronUp, Settings as SettingsIcon, Pin, HelpCircle } from 'lucide-react';
import { HeaderButton } from './components/HeaderButton';
import { ErrorBoundary, WebGLUnavailableFallback } from './components/ErrorBoundary';
import { SettingsPanel, useSettings } from './components/SettingsPanel';
import { DrillMenu } from './components/DrillMenu';

export type Tab =
  | 'home' | '3d' | 'mc' | 'telemetry' | 'export' | 'login' | 'knowledge'
  | 'chronology' | 'traj_design' | 'ship_build' | 'mass_sizing' | 'structure'
  | 'eecom' | 'crew_life' | 'astro' | 'tracking' | 'governance'
  | 'aiconsole' | 'opslog' | 'failures';

export type Role = 'CAPTAIN' | 'EECOM' | 'FDO+GNC' | 'INCO' | 'SURGEON' | 'VEHICLE';
export type RoleFilter = 'ALL' | Role;
export const ROLES: Role[] = ['CAPTAIN', 'EECOM', 'FDO+GNC', 'INCO', 'SURGEON', 'VEHICLE'];
export const ROLE_DESC: Record<RoleFilter, string> = {
  ALL:       'Show every tab in the strip.',
  CAPTAIN:   'Mission command — tasking, decisions, log keeping.',
  EECOM:     'Electrical, Environmental, Consumables, Mechanical (NASA flight controller).',
  'FDO+GNC': 'Flight Dynamics + Guidance, Navigation, Control — trajectory work.',
  INCO:      'Instrumentation & Communications — comms, ground network.',
  SURGEON:   'Crew health and biomedical risk monitoring.',
  VEHICLE:   'Spacecraft engineering — design, mass, BoM, structure.',
};

const TAB_ALIASES: Record<string, { tab: Tab; sub: string }> = {
  advisor:       { tab: 'aiconsole',   sub: 'advisor' },
  aidecisions:   { tab: 'aiconsole',   sub: 'decisions' },
  decisions:     { tab: 'aiconsole',   sub: 'decisions' },
  aiactions:     { tab: 'aiconsole',   sub: 'actions' },
  actions:       { tab: 'aiconsole',   sub: 'actions' },
  events:        { tab: 'opslog',      sub: 'events' },
  incidents:     { tab: 'opslog',      sub: 'incidents' },
  alarms:        { tab: 'opslog',      sub: 'alarms' },
  log:           { tab: 'opslog',      sub: 'log' },
  objectives:    { tab: 'opslog',      sub: 'objectives' },
  fmea:          { tab: 'failures',    sub: 'fmea' },
  cascade:       { tab: 'failures',    sub: 'cascade' },
  randevents:    { tab: 'failures',    sub: 'randevents' },
  timeline:      { tab: 'chronology',  sub: 'timeline' },
  replay:        { tab: 'chronology',  sub: 'replay' },
  moonmission:   { tab: 'chronology',  sub: 'moonmission' },
  trajectory:    { tab: 'traj_design', sub: 'trajectory' },
  lunar:         { tab: 'traj_design', sub: 'lunar' },
  mars:          { tab: 'traj_design', sub: 'mars' },
  planner:       { tab: 'traj_design', sub: 'planner' },
  missiondesign: { tab: 'traj_design', sub: 'missiondesign' },
  porkchop:      { tab: 'traj_design', sub: 'porkchop' },
  studio:        { tab: 'traj_design', sub: 'studio' },
  builder:       { tab: 'ship_build',  sub: 'builder' },
  assembler:     { tab: 'ship_build',  sub: 'assembler' },
  crosssection:  { tab: 'ship_build',  sub: 'crosssection' },
  graph:         { tab: 'ship_build',  sub: 'graph' },
  bom:           { tab: 'mass_sizing', sub: 'bom' },
  mass:          { tab: 'mass_sizing', sub: 'mass' },
  sizing:        { tab: 'mass_sizing', sub: 'sizing' },
  massest:       { tab: 'mass_sizing', sub: 'massest' },
  massbom:       { tab: 'mass_sizing', sub: 'bom' },
  hull:          { tab: 'structure',   sub: 'hull' },
  shield:        { tab: 'structure',   sub: 'shield' },
  subsystems:    { tab: 'eecom',       sub: 'subsystems' },
  powerflow:     { tab: 'eecom',       sub: 'powerflow' },
  propellant:    { tab: 'eecom',       sub: 'propellant' },
  reactor:       { tab: 'eecom',       sub: 'reactor' },
  atmosphere:    { tab: 'eecom',       sub: 'atmosphere' },
  bearing:       { tab: 'eecom',       sub: 'bearing' },
  commslink:     { tab: 'eecom',       sub: 'commslink' },
  radiation:     { tab: 'eecom',       sub: 'radiation' },
  ops:           { tab: 'eecom',       sub: 'ops' },
  crewpop:       { tab: 'crew_life',   sub: 'crewpop' },
  agri:          { tab: 'crew_life',   sub: 'agri' },
  planetarium:   { tab: 'astro',       sub: 'planetarium' },
  orbits3d:      { tab: 'astro',       sub: 'orbits3d' },
  skytonight:    { tab: 'astro',       sub: 'skytonight' },
  astroevents:   { tab: 'astro',       sub: 'astroevents' },
  catalogs:      { tab: 'astro',       sub: 'catalogs' },
  sats3d:        { tab: 'tracking',    sub: 'sats3d' },
  groundtrack:   { tab: 'tracking',    sub: 'groundtrack' },
  tleparser:     { tab: 'tracking',    sub: 'tleparser' },
  dsn:           { tab: 'tracking',    sub: 'dsn' },
  spaceweather:  { tab: 'tracking',    sub: 'spaceweather' },
  constellation: { tab: 'tracking',    sub: 'constellation' },
  safety:        { tab: 'governance',  sub: 'safety' },
  admin:         { tab: 'governance',  sub: 'admin' },
};

// Single source of truth for tab labels, ordering, and Cmd-K keywords.
// Rename a tab here, not in the tab bar JSX.
//
// 2026-04-24: renamed 5 ambiguously-labelled tabs so users can tell them
// apart without clicking.  Three-way overlap on "Moon" was the main pain
// point; Mass Estimator vs Mass Budget was second.
const TABS: readonly { id: Tab; label: string; group: string; hints?: string; roles: (Role | 'ALL')[] }[] = [
  { id: 'home',        label: 'Home',              group: 'start',      roles: ['ALL'], hints: 'welcome landing overview getting started' },
  { id: 'mc',          label: 'Mission Control',   group: 'ops',        roles: ['CAPTAIN', 'EECOM'], hints: 'play pause speed fail inject scenario live' },
  { id: 'telemetry',   label: 'Telemetry',         group: 'ops',        roles: ['CAPTAIN', 'EECOM'], hints: 'live metrics sparklines cards' },
  { id: 'chronology',  label: 'Chronology',        group: 'ops',        roles: ['CAPTAIN', 'FDO+GNC', 'INCO'], hints: 'timeline replay apollo 13 11 mir spektr sts gantt phase events history audit doctrine moonmission' },
  { id: 'opslog',      label: 'Ops Log',           group: 'ops',        roles: ['CAPTAIN', 'EECOM'], hints: 'events incidents alarms captain log objectives bus history warning critical severity rca root cause audit trace hash chain' },
  { id: 'aiconsole',   label: 'AI Console',        group: 'ops',        roles: ['CAPTAIN', 'EECOM', 'INCO'], hints: 'ai advisor decisions actions recommendation severity llm gemini rule citations executed advisory dispatch shed_load safe_mode set_setpoint' },
  { id: 'knowledge',   label: 'Knowledge',         group: 'ops',        roles: ['ALL'], hints: 'doctrine flight rule lessons learned llis ecss search retrieval citation' },
  { id: 'traj_design', label: 'Trajectory Design', group: 'flight',     roles: ['FDO+GNC', 'CAPTAIN'], hints: 'trajectory orbit transfer mars moon lunar planner porkchop lambert c3 monte carlo studio multi-rev aerocapture light lag interstellar route legs delta-v fuel feasibility' },
  { id: 'astro',       label: 'Astro',             group: 'flight',     roles: ['FDO+GNC'], hints: 'planetarium solar system 3d sky tonight stars planets eclipse perigee opposition conjunction messier asteroid comet meteor catalog' },
  { id: 'tracking',    label: 'Tracking',          group: 'inco',       roles: ['INCO', 'FDO+GNC'], hints: 'satellites 3d ground track tle parser dsn deep space network goldstone madrid canberra space weather kp flare solar walker constellation iridium gps starlink celestrak sgp4' },
  { id: '3d',          label: '3D Model',          group: 'vehicle',    roles: ['VEHICLE'], hints: 'ship 3d viewer model parts explode isolate wireframe' },
  { id: 'ship_build',  label: 'Ship Build',        group: 'vehicle',    roles: ['VEHICLE'], hints: 'builder assembler cross section dependency graph parts rebuild interior slice deck kerbal simple rockets palette' },
  { id: 'mass_sizing', label: 'Mass & Sizing',     group: 'vehicle',    roles: ['VEHICLE'], hints: 'bill of materials mass budget subsystem sizing phase-a smad fractions payload scaling forward backward bom' },
  { id: 'structure',   label: 'Structure',         group: 'vehicle',    roles: ['VEHICLE', 'EECOM'], hints: 'hull damage impact mmod shield stack whipple radiation micrometeoroid repair' },
  { id: 'eecom',       label: 'EECOM',             group: 'eecom',      roles: ['EECOM'], hints: 'subsystems power flow sankey reactor load shed propellant fuel tank isp atmosphere eclss co2 o2 scrubber bearing maglev comms link budget antenna radiation dose gcr spe operations procedure workflow' },
  { id: 'failures',    label: 'Failure Analysis',  group: 'eecom',      roles: ['EECOM', 'VEHICLE'], hints: 'fmea cascade random events failure mode effects analysis rpn propagation dependency stochastic generator seed' },
  { id: 'crew_life',   label: 'Crew & Life',       group: 'surgeon',    roles: ['SURGEON', 'CAPTAIN'], hints: 'crew population health bone cohesion vestibular sans agriculture food hydroponics crops melissa' },
  { id: 'governance',  label: 'Governance',        group: 'governance', roles: ['CAPTAIN'], hints: 'safety failsafe kill switch constitution two-person approval cooling-off budget proposals operator admin user management principals roles permissions custom rbac escalation' },
  { id: 'login',       label: 'Login',             group: 'governance', roles: ['ALL'], hints: 'login auth identity captain crew session bearer signin signout logout principal role rbac' },
  { id: 'export',      label: 'Export',            group: 'utility',    roles: ['ALL'], hints: 'export download save report json' },
];

// R10 (2026-04-24, walkthrough): tabs where the left parts-list and
// right part-inspector sidebars are relevant.  Everywhere else the
// "Click a part in the 3D view or parts list to inspect" placeholder
// appeared on Home / Telemetry / Moon Mission / etc. — visual clutter
// that implied functionality those tabs don't have.
const PART_RELEVANT_TABS: Set<Tab> = new Set([
  '3d', 'ship_build', 'mass_sizing', 'structure', 'eecom',
]);

// R10: footer (current phase + cold-start sequence) is useful on
// Mission Control and live-sim adjacent tabs, and just eats vertical
// space on design / analysis / astro tabs.  On Moon · Vehicle Design
// specifically, the Warnings banner was being clipped by the footer.
const FOOTER_RELEVANT_TABS: Set<Tab> = new Set<Tab>([
  'mc', '3d', 'telemetry', 'chronology', 'traj_design', 'ship_build',
  'aiconsole', 'opslog', 'eecom', 'crew_life', 'structure', 'failures',
  'tracking',
]);

async function saveSnapshot() {
  try {
    const data = await ariaApi.saveSnapshot();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `aria-mission-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert(`Save failed: ${e}`);
  }
}

async function loadSnapshotFromFile(ev: React.ChangeEvent<HTMLInputElement>) {
  const file = ev.target.files?.[0];
  if (!file) return;
  try {
    const text = await file.text();
    const data = JSON.parse(text);
    const r = await ariaApi.loadSnapshot(data);
    alert(`Loaded ${r.report.applied.length} subsystems · ${r.report.errors.length} errors`);
  } catch (e) {
    alert(`Load failed: ${e}`);
  } finally {
    ev.target.value = '';
  }
}

export default function App() {
  const [selectedPartId, setSelectedPartId] = useState<string | null>(null);
  const [hoveredPartId, setHoveredPartId]   = useState<string | null>(null);
  const [showStats, setShowStats]           = useState(false);
  // Persist the active tab across page reloads.  Without this, every
  // refresh / Cmd-R bounces the user back to Home, which is a frequent
  // pain point during long-running sim sessions.  Only restore values
  // that match the current Tab union (defensive against stale storage
  // after we rename tabs).
  const [tab, setTab] = useState<Tab>(() => {
    const saved = safeStorage.getItem('aria.activeTab');
    if (saved && TAB_ALIASES[saved]) return TAB_ALIASES[saved].tab;
    const valid = TABS.some((t) => t.id === saved);
    return valid ? (saved as Tab) : 'home';
  });
  const [initialSubs, setInitialSubs] = useState<Record<string, string | undefined>>(() => {
    const saved = safeStorage.getItem('aria.activeTab');
    if (saved && TAB_ALIASES[saved]) {
      const alias = TAB_ALIASES[saved];
      return { [alias.tab]: alias.sub };
    }
    return {};
  });
  useEffect(() => {
    safeStorage.setItem('aria.activeTab', tab);
  }, [tab]);

  const goToTab = (target: Tab | string) => {
    if (typeof target === 'string' && TAB_ALIASES[target]) {
      const alias = TAB_ALIASES[target];
      setInitialSubs((prev) => ({ ...prev, [alias.tab]: alias.sub }));
      setTab(alias.tab);
      return;
    }
    setTab(target as Tab);
  };

  const [role, setRole] = useState<RoleFilter>(() => {
    const saved = safeStorage.getItem('aria.activeRole');
    if (saved === 'ALL' || ROLES.includes(saved as Role)) return saved as RoleFilter;
    return 'ALL';
  });
  useEffect(() => {
    safeStorage.setItem('aria.activeRole', role);
  }, [role]);

  const [pinnedTabs, setPinnedTabs] = useState<Tab[]>(() => {
    try {
      const raw = safeStorage.getItem('aria.pinnedTabs');
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed.filter((id) => typeof id === 'string') as Tab[];
    } catch { /* fallthrough */ }
    return [];
  });
  useEffect(() => {
    try { safeStorage.setItem('aria.pinnedTabs', JSON.stringify(pinnedTabs)); } catch { /* quota */ }
  }, [pinnedTabs]);
  const togglePin = (id: Tab) => {
    setPinnedTabs((prev) => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const filteredTabs = role === 'ALL'
    ? TABS
    : TABS.filter((t) => t.roles.includes('ALL') || t.roles.includes(role));
  const visibleTabs = (() => {
    if (pinnedTabs.length === 0) return filteredTabs;
    const pinSet = new Set(pinnedTabs);
    const pinned = pinnedTabs
      .map((id) => filteredTabs.find((t) => t.id === id))
      .filter((t): t is typeof filteredTabs[number] => !!t);
    const rest = filteredTabs.filter((t) => !pinSet.has(t.id));
    return [...pinned, ...rest];
  })();
  // ── 3D viewer state (shared between toolbar + Ship3D + ShipBuilder) ──
  const [explode, setExplode]       = useState(0);
  const [isolate, setIsolate]       = useState<string | null>(null);
  const [wireframe, setWireframe]   = useState(false);
  const [reloadKey, setReloadKey]   = useState(0);   // bump after a rebuild
  const [showLabels, setShowLabels] = useState(true);
  const [cleanView, setCleanView]   = useState(false);
  // FX off by default — the ship renders as solid opaque primitives
  // (no additive glow shells, no plasma plume sprites, no strobe
  // beacons, no emissive pulsing). Flip on for the cinematic look.
  const [showFx, setShowFx]         = useState(false);
  const [zoom, setZoom]             = useState<{ a: ZoomAction; n: number } | null>(null);
  const [immersive, setImmersive]   = useState<boolean>(() => safeStorage.getItem('aria.immersive') === '1');
  useEffect(() => { safeStorage.setItem('aria.immersive', immersive ? '1' : '0'); }, [immersive]);
  const [partsCollapsed, setPartsCollapsed] = useState<boolean>(() => safeStorage.getItem('aria.partsCollapsed.v2') === '1');
  useEffect(() => { safeStorage.setItem('aria.partsCollapsed.v2', partsCollapsed ? '1' : '0'); }, [partsCollapsed]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [criticalAlarms, setCriticalAlarms] = useState(0);
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const r = await ariaApi.eventsRecent(50, undefined, 'critical');
        if (!alive) return;
        const n = (r?.events ?? []).filter((e: any) => {
          const sev = String(e.severity ?? '').toLowerCase();
          return sev === 'critical' || sev === 'emergency';
        }).length;
        setCriticalAlarms(n);
      } catch { /* silent */ }
    };
    poll();
    const t = setInterval(poll, 10_000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tgt = e.target as HTMLElement | null;
      const inField = !!tgt && (tgt.tagName === 'INPUT' || tgt.tagName === 'TEXTAREA' || tgt.isContentEditable);
      if (inField) return;
      if ((e.metaKey || e.ctrlKey) && e.key === ',') {
        setSettingsOpen(v => !v);
        e.preventDefault();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  const [partsListCollapsed, setPartsListCollapsed] = useState<boolean>(() => safeStorage.getItem('aria.partsListCollapsed.v2') === '1');
  useEffect(() => { safeStorage.setItem('aria.partsListCollapsed.v2', partsListCollapsed ? '1' : '0'); }, [partsListCollapsed]);
  const [footerCollapsed, setFooterCollapsed] = useState<boolean>(() => safeStorage.getItem('aria.footerCollapsed') === '1');
  useEffect(() => { safeStorage.setItem('aria.footerCollapsed', footerCollapsed ? '1' : '0'); }, [footerCollapsed]);
  const [deployment, setDeployment] = useState(1);        // 0 stowed → 1 deployed
  // Camera preset trigger: we toggle via `[preset, nonce]` so pressing the
  // same button twice (e.g. "fore" → user drifts → "fore") still re-centres
  // the camera. Only the nonce changes when the preset doesn't.
  const [cameraPreset, setCameraPreset] = useState<{ p: CameraPreset; n: number } | null>(null);

  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    const saved = safeStorage.getItem('aria-theme');
    return saved === 'light' ? 'light' : 'dark';
  });
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'light') root.classList.add('light');
    else root.classList.remove('light');
  }, [theme]);

  const settings = useSettings();
  useEffect(() => {
    const root = document.documentElement;
    if (settings.reduceMotion) root.classList.add('reduce-motion');
    else root.classList.remove('reduce-motion');
  }, [settings.reduceMotion]);
  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    safeStorage.setItem('aria-theme', next);
  };

  const [backendOk, setBackendOk] = useState(true);
  const [backendDownSince, setBackendDownSince] = useState<number | null>(null);
  useEffect(() => {
    const check = async () => {
      try {
        const r = await fetch('/api/status');
        if (r.ok) {
          setBackendOk(true);
          setBackendDownSince(null);
        } else {
          setBackendOk(false);
          setBackendDownSince((prev) => prev ?? Date.now());
        }
      } catch {
        setBackendOk(false);
        setBackendDownSince((prev) => prev ?? Date.now());
      }
    };
    check();
    const t = setInterval(check, 5_000);
    return () => clearInterval(t);
  }, []);
  const showBackendBanner = !backendOk && backendDownSince !== null && Date.now() - backendDownSince > 8_000;

  return (
    <div className="flex flex-col h-screen bg-ui-bg-0 text-ui-text">
      <header className="flex items-center justify-between px-4 py-2 border-b border-ui-border bg-ui-bg-1/80">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${backendOk ? 'bg-sev-ok' : 'bg-sev-crit animate-pulse'}`}
               title={backendOk ? 'Backend connected' : 'Backend unreachable'} />
          <span className="text-sm font-bold tracking-widest text-ui-accent">
            <span className="hidden sm:inline">ARIA ENGINEERING LAB</span>
            <span className="sm:hidden">ARIA</span>
          </span>
        </div>
        <div className="flex gap-2 text-xs">
          <HeaderButton tone="success" onClick={saveSnapshot}>
            <Save size={14} aria-hidden /> Save
          </HeaderButton>
          <label className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-blue-700 bg-blue-900/30 text-ui-text hover:bg-blue-700/50 cursor-pointer transition-colors">
            <FolderOpen size={14} aria-hidden /> Load
            <input type="file" accept=".json" className="hidden" onChange={loadSnapshotFromFile} />
          </label>
          <HeaderButton onClick={toggleTheme}
                        title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
                        aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}>
            {theme === 'dark' ? <Sun size={14} aria-hidden /> : <Moon size={14} aria-hidden />}
          </HeaderButton>
          <a href="/lab" className="inline-flex items-center px-2 py-1 rounded border border-ui-border text-ui-text hover:bg-ui-bg-2 transition-colors">HTML Lab →</a>
          <HeaderButton onClick={() => setSettingsOpen(true)}
                        title="Settings — notifications, motion, etc."
                        aria-label="Open settings">
            <SettingsIcon size={14} aria-hidden /> <span className="hidden sm:inline">Settings</span>
          </HeaderButton>
          <HeaderButton tone={showStats ? 'toggleOn' : 'toggleOff'} onClick={() => setShowStats(v => !v)}>
            <Activity size={14} aria-hidden /> FPS
          </HeaderButton>
        </div>
      </header>

      {showBackendBanner && (
        <div role="alert" className="flex items-center gap-2 px-3 py-1.5 text-xs bg-sev-crit text-white border-b border-sev-crit">
          <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" aria-hidden />
          <span className="font-semibold">Dashboard backend unreachable.</span>
          <span className="font-mono opacity-90">/api/status failed for {Math.round((Date.now() - (backendDownSince || Date.now())) / 1000)}s</span>
          <span className="hidden sm:inline opacity-80">— restart it: <code className="bg-black/30 px-1 rounded">python -m aria.simulator.web_dashboard --port 8090</code></span>
        </div>
      )}

      <div className="flex items-center gap-3 px-3 h-9 text-xs border-b border-ui-border bg-ui-bg-1">
        <span className="text-ui-text-dim font-semibold">Role:</span>
        <div className="relative inline-block">
          <select value={role}
                  onChange={(ev) => setRole(ev.target.value as RoleFilter)}
                  title={ROLE_DESC[role]}
                  className="appearance-none pl-3 pr-8 py-1 rounded border border-ui-border-strong bg-ui-bg-0 text-ui-text font-medium cursor-pointer hover:border-ui-accent focus:border-ui-accent focus:outline-none">
            <option value="ALL" title={ROLE_DESC.ALL}>All ({TABS.length} tabs)</option>
            {ROLES.map((roleOption) => {
              const count = TABS.filter((t) => t.roles.includes('ALL') || t.roles.includes(roleOption)).length;
              return <option key={roleOption} value={roleOption} title={ROLE_DESC[roleOption]}>{roleOption} ({count})</option>;
            })}
          </select>
          <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-ui-text-dim pointer-events-none" aria-hidden />
        </div>
        {role !== 'ALL' && (
          <span className="hidden xl:inline text-ui-text-faint">
            {visibleTabs.length}/{TABS.length}
          </span>
        )}
        <div className="hidden md:block w-px h-5 bg-ui-border-soft" />
        <StatusStrip onGoto={(t) => goToTab(t)} />
        <div className="ml-auto flex items-center gap-2">
          <DrillMenu />
          <HeaderButton onClick={() => setShortcutsOpen(v => !v)}
                        title="Keyboard shortcuts (press ?)"
                        aria-label="Open keyboard shortcuts">
            <HelpCircle size={12} aria-hidden />
          </HeaderButton>
          <HeaderButton tone={immersive ? 'toggleOn' : 'toggleOff'}
                        onClick={() => setImmersive(v => !v)}
                        title={immersive ? 'Exit fullscreen — restore sidebars and footer' : 'Fullscreen — hide sidebars and footer'}
                        aria-pressed={immersive}>
            {immersive ? <Minimize2 size={12} aria-hidden /> : <Maximize2 size={12} aria-hidden />}
            <span className="hidden sm:inline">{immersive ? 'Exit Full' : 'Fullscreen'}</span>
          </HeaderButton>
        </div>
      </div>

      <main className="flex flex-1 min-h-0">
        {!immersive && PART_RELEVANT_TABS.has(tab) && (
          <aside className={`hidden md:flex flex-col border-r border-ui-border bg-ui-bg-1/60 ${partsListCollapsed ? 'w-7' : 'w-64'}`}>
            <button onClick={() => setPartsListCollapsed(v => !v)}
                    title={partsListCollapsed ? 'Expand parts list' : 'Collapse parts list'}
                    aria-label={partsListCollapsed ? 'Expand parts list' : 'Collapse parts list'}
                    aria-pressed={partsListCollapsed}
                    className="h-7 inline-flex items-center justify-center text-ui-text-dim hover:text-ui-text hover:bg-ui-bg-2 border-b border-ui-border-soft transition-colors">
              {partsListCollapsed ? <PanelRightClose size={14} aria-hidden /> : <PanelRightOpen size={14} aria-hidden />}
            </button>
            {!partsListCollapsed && (
              <div className="flex-1 min-h-0 overflow-y-auto">
                <PartsList selectedPartId={selectedPartId}
                           hoveredPartId={hoveredPartId}
                           onSelect={setSelectedPartId}
                           onHover={setHoveredPartId} />
              </div>
            )}
          </aside>
        )}

        <section className="flex-1 flex flex-col min-w-0">
          {/* Tab strip — single source of truth: TABS registry at top.
              Auto-centers the active tab on click / Cmd-K jump so users
              can always see what's adjacent without losing their place
              in a 20-wide strip (was 50+ pre-R49 consolidation). */}
          <TabStrip tabs={visibleTabs} activeId={tab} onSelect={setTab}
                    pinnedSet={new Set(pinnedTabs)} onTogglePin={togglePin}
                    badges={{ opslog: criticalAlarms > 0 ? { count: criticalAlarms, severity: 'crit' } : undefined }} />

          <ErrorBoundary
            label={`tab=${tab}`}
            fallback={(err, reset) => <WebGLUnavailableFallback error={err} onReset={reset} label={`the ${tab} panel`} />}
          >
          <div className="flex-1 relative min-h-0 min-w-0 overflow-hidden">
            {tab === 'home' && <HomePanel onPick={(t) => goToTab(t)} role={role} />}
            {tab === '3d' && (
              <>
                <Ship3D onPartClick={(id) => { setSelectedPartId(id); if (isolate) setIsolate(id); }}
                        hoveredPartId={hoveredPartId}
                        setHoveredPart={setHoveredPartId}
                        showStats={showStats}
                        explodeAmount={explode}
                        isolatePartId={isolate}
                        wireframe={wireframe}
                        reloadKey={reloadKey}
                        showLabels={showLabels}
                        cameraPreset={cameraPreset?.p ?? null}
                        cameraPresetNonce={cameraPreset?.n ?? 0}
                        cleanView={cleanView}
                        showFx={showFx}
                        zoomAction={zoom?.a ?? null}
                        zoomActionNonce={zoom?.n ?? 0}
                        deployment={deployment} />
                <ViewerToolbar
                  explode={explode}       setExplode={setExplode}
                  isolate={isolate}       setIsolate={setIsolate}
                  wireframe={wireframe}   setWireframe={setWireframe}
                  showLabels={showLabels} setShowLabels={setShowLabels}
                  cleanView={cleanView}   setCleanView={setCleanView}
                  showFx={showFx}         setShowFx={setShowFx}
                  deployment={deployment} setDeployment={setDeployment}
                  hoveredPartId={hoveredPartId}
                  onReset={() => { setExplode(0); setIsolate(null); setWireframe(false); setShowLabels(true); setCleanView(false); setShowFx(false); setDeployment(1); }}
                  onPreset={(p) => setCameraPreset({ p, n: (cameraPreset?.n ?? 0) + 1 })}
                  onZoom={(a) => setZoom({ a, n: (zoom?.n ?? 0) + 1 })}
                />
                {hoveredPartId && (
                  <div className="absolute bottom-3 left-3 px-2 py-1 text-xs bg-ui-bg-0/90 border border-ui-accent-strong rounded pointer-events-none text-ui-text">
                    {hoveredPartId}
                  </div>
                )}
                <button onClick={() => setImmersive(v => !v)}
                        title={immersive ? 'Exit fullscreen' : 'Fullscreen 3D viewer'}
                        className="absolute top-3 left-3 z-10 pointer-events-auto inline-flex items-center gap-1.5 px-2 py-1 text-[10px] rounded border border-ui-border bg-ui-bg-1/85 backdrop-blur text-ui-text hover:bg-ui-bg-2 hover:border-ui-accent transition-colors">
                  {immersive ? <X size={12} aria-hidden /> : <Maximize2 size={12} aria-hidden />}
                  {immersive ? 'Exit fullscreen' : 'Fullscreen'}
                </button>
              </>
            )}
            {tab === 'mc'          && <MissionControlPanel />}
            {tab === 'telemetry'   && <TelemetryDashboard />}
            {tab === 'export'      && <MissionExport />}
            {tab === 'login'       && <LoginPanel />}
            {tab === 'knowledge'   && <KnowledgePanel />}
            {tab === 'aiconsole'   && <AIConsolePanel   initialSub={initialSubs.aiconsole as never} />}
            {tab === 'opslog'      && <OperationsLogPanel initialSub={initialSubs.opslog as never} />}
            {tab === 'failures'    && <FailureAnalysisPanel initialSub={initialSubs.failures as never} />}
            {tab === 'chronology'  && <ChronologyPanel  initialSub={initialSubs.chronology as never} />}
            {tab === 'traj_design' && <TrajectoryDesignerPanel initialSub={initialSubs.traj_design as never} />}
            {tab === 'ship_build'  && <ShipBuildPanel
                                        initialSub={initialSubs.ship_build as never}
                                        onRebuilt={() => setReloadKey(k => k + 1)}
                                        selectedPartId={selectedPartId}
                                        onSelectPart={setSelectedPartId} />}
            {tab === 'mass_sizing' && <MassSizingPanel initialSub={initialSubs.mass_sizing as never} onSelectPart={setSelectedPartId} />}
            {tab === 'structure'   && <StructurePanel  initialSub={initialSubs.structure as never} />}
            {tab === 'eecom'       && <EecomConsolePanel initialSub={initialSubs.eecom as never} />}
            {tab === 'crew_life'   && <CrewLifePanel   initialSub={initialSubs.crew_life as never} />}
            {tab === 'astro'       && <AstroPanel      initialSub={initialSubs.astro as never} />}
            {tab === 'tracking'    && <TrackingPanel   initialSub={initialSubs.tracking as never} />}
            {tab === 'governance'  && <GovernancePanel initialSub={initialSubs.governance as never} />}
          </div>
          </ErrorBoundary>
        </section>

        {!immersive && PART_RELEVANT_TABS.has(tab) && (
          <aside className={`hidden lg:flex flex-col border-l border-ui-border bg-ui-bg-1/60 ${partsCollapsed ? 'w-7' : 'w-80'}`}>
            <button onClick={() => setPartsCollapsed(v => !v)}
                    title={partsCollapsed ? 'Expand inspector' : 'Collapse inspector'}
                    aria-label={partsCollapsed ? 'Expand inspector' : 'Collapse inspector'}
                    aria-pressed={partsCollapsed}
                    className="h-7 inline-flex items-center justify-center text-ui-text-dim hover:text-ui-text hover:bg-ui-bg-2 border-b border-ui-border-soft transition-colors">
              {partsCollapsed ? <PanelRightOpen size={14} aria-hidden /> : <PanelRightClose size={14} aria-hidden />}
            </button>
            {!partsCollapsed && (
              <div className="flex-1 min-h-0 overflow-y-auto">
                <PartPanel partId={selectedPartId} onSelectPart={setSelectedPartId} />
              </div>
            )}
          </aside>
        )}
      </main>

      {!immersive && FOOTER_RELEVANT_TABS.has(tab) && (
        <footer className={`hidden sm:flex flex-col border-t border-ui-border bg-ui-bg-1/60 ${footerCollapsed ? '' : 'max-h-[35vh]'}`}>
          <button onClick={() => setFooterCollapsed(v => !v)}
                  title={footerCollapsed ? 'Expand mission panel' : 'Collapse mission panel'}
                  aria-label={footerCollapsed ? 'Expand mission panel' : 'Collapse mission panel'}
                  aria-pressed={footerCollapsed}
                  className="h-6 inline-flex items-center justify-center gap-1.5 text-[10px] uppercase tracking-wider text-ui-text-dim hover:text-ui-text hover:bg-ui-bg-2 border-b border-ui-border-soft transition-colors">
            {footerCollapsed
              ? <><ChevronUp size={12} aria-hidden /> Mission Panel · Cold-Start Sequence</>
              : <><ChevronDown size={12} aria-hidden /> Hide</>}
          </button>
          {!footerCollapsed && (
            <div className="flex flex-1 min-h-0">
              <div className="flex-1 border-r border-ui-border-soft min-w-0 overflow-y-auto">
                <MissionPanel />
              </div>
              <div className="flex-1 min-w-0 overflow-y-auto">
                <StartupPanel />
              </div>
            </div>
          )}
        </footer>
      )}
      <ToastNotifications />
      <KeyboardShortcuts open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
      <CommandPalette tabs={TABS} onPick={(t) => goToTab(t)} />
      <SettingsPanel open={settingsOpen}
                     onClose={() => setSettingsOpen(false)}
                     tabs={TABS.map(t => ({ id: t.id, label: t.label, roles: t.roles }))}
                     roles={ROLES}
                     currentRole={role}
                     onSetRole={setRole}
                     roleDesc={ROLE_DESC} />
    </div>
  );
}

type Badge = { count: number; severity: 'info' | 'ok' | 'warn' | 'crit' };
const BADGE_DOT: Record<Badge['severity'], string> = {
  info: 'bg-sev-info',
  ok:   'bg-sev-ok',
  warn: 'bg-sev-warn',
  crit: 'bg-sev-crit',
};

function TabBtn({ label, active, pinned, badge, onClick, onContextMenu, btnRef }: {
  label: string; active: boolean; pinned: boolean; badge?: Badge;
  onClick: () => void;
  onContextMenu: (e: React.MouseEvent<HTMLButtonElement>) => void;
  btnRef?: React.Ref<HTMLButtonElement>;
}) {
  const titleParts: string[] = [pinned ? 'Pinned · right-click to unpin' : 'Right-click to pin to the front of the strip'];
  if (badge) titleParts.push(`${badge.count} active ${badge.severity}`);
  return (
    <button ref={btnRef}
            onClick={onClick}
            onContextMenu={onContextMenu}
            title={titleParts.join(' · ')}
            className={`inline-flex items-center gap-1 px-3 py-1.5 border-b-2 transition-colors whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ui-accent focus-visible:ring-inset
              ${active ? 'border-ui-accent text-ui-accent bg-ui-bg-2/60'
                       : 'border-transparent text-ui-text-dim hover:text-ui-text hover:bg-ui-bg-2/30'}`}>
      {pinned && <Pin size={10} className="text-ui-accent shrink-0" aria-hidden />}
      <span>{label}</span>
      {badge && (
        <span className={`ml-1 w-1.5 h-1.5 rounded-full ${BADGE_DOT[badge.severity]} ${badge.severity === 'crit' ? 'animate-pulse' : ''}`}
              aria-label={`${badge.count} active ${badge.severity}`} />
      )}
    </button>
  );
}

/** Tab strip with auto-center behaviour + edge-fade overflow indicators.
 *
 *  When the active tab changes (whether via click, Cmd-K, or a
 *  programmatic setTab() from deep inside the app) the active TabBtn
 *  is scrolled into the horizontal centre of the strip. Even at 20
 *  tabs the role filter can produce strips with overflow on small
 *  screens; before this, clicking a tab in the middle shifted the
 *  label out of view the moment the underline changed.
 *
 *  Uses `scrollIntoView({ block: 'nearest', inline: 'center' })` which
 *  modern Chromium/Firefox/WebKit all support; the `block: 'nearest'`
 *  avoids any vertical page scroll. */
function TabStrip({ tabs, activeId, onSelect, pinnedSet, onTogglePin, badges }: {
  tabs: ReadonlyArray<{ id: Tab; label: string; group: string; hints?: string; roles: (Role | 'ALL')[] }>;
  activeId: Tab; onSelect: (id: Tab) => void;
  pinnedSet: Set<Tab>;
  onTogglePin: (id: Tab) => void;
  badges?: Partial<Record<Tab, Badge>>;
}) {
  const refs = React.useRef<Record<string, HTMLButtonElement | null>>({});
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const [overflow, setOverflow] = React.useState<{ left: boolean; right: boolean }>({ left: false, right: false });

  React.useEffect(() => {
    const el = refs.current[activeId];
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
    }
  }, [activeId]);

  React.useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => {
      setOverflow({
        left:  el.scrollLeft > 4,
        right: el.scrollLeft + el.clientWidth < el.scrollWidth - 4,
      });
    };
    measure();
    el.addEventListener('scroll', measure, { passive: true });
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    ro?.observe(el);
    return () => { el.removeEventListener('scroll', measure); ro?.disconnect(); };
  }, [tabs.length]);

  return (
    <div className="relative">
      <div ref={containerRef}
           className="flex border-b border-ui-border bg-ui-bg-1/40 text-xs overflow-x-auto scroll-smooth"
           role="tablist"
           onKeyDown={(ev) => {
             const idx = tabs.findIndex(t => t.id === activeId);
             if (idx === -1) return;
             if (ev.key === 'ArrowRight') {
               const next = tabs[(idx + 1) % tabs.length];
               onSelect(next.id as Tab);
               refs.current[next.id]?.focus();
               ev.preventDefault();
             } else if (ev.key === 'ArrowLeft') {
               const prev = tabs[(idx - 1 + tabs.length) % tabs.length];
               onSelect(prev.id as Tab);
               refs.current[prev.id]?.focus();
               ev.preventDefault();
             } else if (ev.key === 'Home') {
               const first = tabs[0];
               onSelect(first.id as Tab);
               refs.current[first.id]?.focus();
               ev.preventDefault();
             } else if (ev.key === 'End') {
               const last = tabs[tabs.length - 1];
               onSelect(last.id as Tab);
               refs.current[last.id]?.focus();
               ev.preventDefault();
             }
           }}>
        {tabs.map((t) => (
          <TabBtn key={t.id}
                  label={t.label}
                  active={activeId === t.id}
                  pinned={pinnedSet.has(t.id)}
                  badge={badges?.[t.id]}
                  onClick={() => onSelect(t.id as Tab)}
                  onContextMenu={(ev) => { ev.preventDefault(); onTogglePin(t.id); }}
                  btnRef={(el) => { refs.current[t.id] = el; }} />
        ))}
      </div>
      {overflow.left && (
        <div className="pointer-events-none absolute inset-y-0 left-0 w-8 bg-gradient-to-r from-ui-bg-0 to-transparent" aria-hidden />
      )}
      {overflow.right && (
        <div className="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-ui-bg-0 to-transparent" aria-hidden />
      )}
    </div>
  );
}
