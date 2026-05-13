import type { ComponentType } from 'react';
import {
  Play, Moon, Wrench, Sparkles, Target, Box, Activity,
  BrainCircuit, AlertTriangle, Zap, HeartPulse, Radio, Satellite, Scale,
  type LucideProps,
} from 'lucide-react';
import type { Tab, RoleFilter, Role } from '../App';

type Group = 'live' | 'mission' | 'design' | 'engineering' | 'awareness';

interface Card {
  title: string;
  blurb: string;
  target: Tab | string;
  Icon: ComponentType<LucideProps>;
  accent: string;
  iconColor: string;
  group: Group;
  roles: (Role | 'ALL')[];
}

const GROUP_LABEL: Record<Group, string> = {
  live:        'Live operations',
  mission:     'Mission planning',
  design:      'Vehicle & subsystems',
  engineering: 'Engineering ledger',
  awareness:   'Situational awareness',
};

const CARDS: Card[] = [
  {
    title: 'Watch a live mission',
    blurb: 'Play the simulation, watch telemetry sparklines, inject faults and see ARIA respond.',
    target: 'mc',
    Icon: Play,
    accent: 'border-emerald-500',
    iconColor: 'text-emerald-400',
    group: 'live',
    roles: ['CAPTAIN', 'EECOM'],
  },
  {
    title: 'Live Telemetry',
    blurb: 'Every subsystem metric as a sparkline. Unit-aware (kg auto-promotes to tonnes).',
    target: 'telemetry',
    Icon: Activity,
    accent: 'border-teal-500',
    iconColor: 'text-teal-300',
    group: 'live',
    roles: ['CAPTAIN', 'EECOM'],
  },
  {
    title: 'AI Console',
    blurb: 'Onboard AI advisor, decisions log, and dispatched actions in one place.',
    target: 'aiconsole',
    Icon: BrainCircuit,
    accent: 'border-rose-500',
    iconColor: 'text-rose-300',
    group: 'live',
    roles: ['CAPTAIN', 'EECOM', 'INCO'],
  },
  {
    title: 'Ops Log',
    blurb: 'Events, incidents, alarms, captain notes, objectives — the unified operations record.',
    target: 'opslog',
    Icon: AlertTriangle,
    accent: 'border-sev-crit',
    iconColor: 'text-sev-crit',
    group: 'live',
    roles: ['CAPTAIN', 'EECOM'],
  },
  {
    title: 'Moon · Apollo Replay',
    blurb: 'Replay Apollo 11 / Artemis 3 phase-by-phase. Validates TLI → LOI → descent → ascent physics.',
    target: 'moonmission',
    Icon: Moon,
    accent: 'border-blue-500',
    iconColor: 'text-blue-400',
    group: 'mission',
    roles: ['CAPTAIN', 'FDO+GNC'],
  },
  {
    title: 'Moon · Vehicle Design',
    blurb: 'Slider-driven design loop. Tweak cabin, propellant, shielding. Get Δv / FEA / dose GO-NOGO.',
    target: 'lunar',
    Icon: Wrench,
    accent: 'border-ui-accent',
    iconColor: 'text-ui-accent',
    group: 'mission',
    roles: ['CAPTAIN', 'FDO+GNC', 'VEHICLE'],
  },
  {
    title: 'Interstellar Route Planner',
    blurb: 'Build a multi-leg destination list. Auto-execute legs, refuel on arrival, track propellant.',
    target: 'planner',
    Icon: Sparkles,
    accent: 'border-purple-500',
    iconColor: 'text-purple-400',
    group: 'mission',
    roles: ['CAPTAIN', 'FDO+GNC'],
  },
  {
    title: 'Transfer Designer (Porkchop)',
    blurb: 'Lambert / C3 / porkchop for any planet-to-planet window. Find optimal Δv and TOF.',
    target: 'missiondesign',
    Icon: Target,
    accent: 'border-sev-warn',
    iconColor: 'text-sev-warn',
    group: 'mission',
    roles: ['FDO+GNC'],
  },
  {
    title: '3D Ship Model',
    blurb: 'Explode / isolate / rotate the spacecraft. Click a part for its mass, Isp, material data.',
    target: '3d',
    Icon: Box,
    accent: 'border-ui-border-strong',
    iconColor: 'text-ui-text-dim',
    group: 'design',
    roles: ['VEHICLE'],
  },
  {
    title: 'EECOM Console',
    blurb: 'Power, propellant, reactor, atmosphere, bearing, comms, radiation — one EECOM workstation.',
    target: 'eecom',
    Icon: Zap,
    accent: 'border-sev-warn',
    iconColor: 'text-sev-warn',
    group: 'design',
    roles: ['EECOM'],
  },
  {
    title: 'Failure Analysis',
    blurb: 'FMEA worksheet, cascade simulator, and random-event injector for resilience studies.',
    target: 'failures',
    Icon: AlertTriangle,
    accent: 'border-orange-500',
    iconColor: 'text-orange-400',
    group: 'design',
    roles: ['EECOM', 'VEHICLE'],
  },
  {
    title: 'Mass & Sizing',
    blurb: 'BoM, mass budget, subsystem sizing, Phase-A scaling — vehicle engineering ledger.',
    target: 'mass_sizing',
    Icon: Scale,
    accent: 'border-stone-500',
    iconColor: 'text-stone-300',
    group: 'engineering',
    roles: ['VEHICLE'],
  },
  {
    title: 'Crew & Life',
    blurb: 'Bone density, cohesion, vestibular, SANS, agriculture — population over mission years.',
    target: 'crew_life',
    Icon: HeartPulse,
    accent: 'border-pink-500',
    iconColor: 'text-pink-300',
    group: 'engineering',
    roles: ['SURGEON', 'CAPTAIN'],
  },
  {
    title: 'Tracking & Ground',
    blurb: 'Live SGP4 satellites, ground tracks, TLE parser, DSN contacts, space weather, constellations.',
    target: 'tracking',
    Icon: Radio,
    accent: 'border-indigo-500',
    iconColor: 'text-indigo-300',
    group: 'awareness',
    roles: ['INCO', 'FDO+GNC'],
  },
  {
    title: 'Astro',
    blurb: 'Planetarium, Solar System 3D, Sky Tonight, astro events, deep-sky catalogs.',
    target: 'astro',
    Icon: Satellite,
    accent: 'border-violet-500',
    iconColor: 'text-violet-300',
    group: 'awareness',
    roles: ['FDO+GNC'],
  },
];

const ROLE_BLURB: Record<RoleFilter, string> = {
  ALL:        'All workflows visible. Switch the role dropdown above to focus the deck.',
  CAPTAIN:    'Mission command — tasking, telemetry, decisions, log keeping.',
  EECOM:      'Electrical, environmental, mechanical, and consumables monitoring.',
  'FDO+GNC':  'Flight dynamics, guidance, navigation, control, trajectory design.',
  INCO:       'Communications, data links, ground network coordination.',
  SURGEON:    'Crew health and biomedical risk monitoring.',
  VEHICLE:    'Spacecraft design, mass, BoM, structure, dependency analysis.',
};

export function HomePanel({ onPick, role }: { onPick: (t: Tab | string) => void; role: RoleFilter }) {
  const visible = role === 'ALL'
    ? CARDS
    : CARDS.filter((card) => card.roles.includes('ALL') || card.roles.includes(role));

  const groupOrder: Group[] = ['live', 'mission', 'design', 'engineering', 'awareness'];
  const grouped = groupOrder
    .map((g) => ({ group: g, cards: visible.filter((c) => c.group === g) }))
    .filter((s) => s.cards.length > 0);

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-6xl mx-auto">
        <header>
          <h1 className="text-2xl font-bold text-ui-accent tracking-wide">ARIA — Autonomous Reasoning &amp; Intelligence for Astronautics</h1>
          <p className="text-xs text-ui-text-faint mt-1 max-w-3xl leading-relaxed">
            Operations dashboard for the live spacecraft simulator. ARIA also covers a digital-twin
            engine, anomaly-detection (Dsremo), conjunction screening, autonomy / safety architecture,
            cFS bridge, replay engine, and product-tier services — most are reachable from the tabs
            below; the rest live as Python modules and CLI tools alongside this dashboard.
          </p>
          <div className="mt-3 flex items-center gap-2 flex-wrap">
            <span className="inline-flex items-center gap-2 px-2 py-0.5 rounded border border-ui-accent/60 bg-ui-accent/15 text-xs text-ui-accent">
              <span className="font-semibold">Role:</span>
              <span>{role}</span>
            </span>
            <span className="text-xs text-ui-text-faint">
              Press
              <kbd className="mx-1 px-1.5 py-0.5 text-[10px] border border-ui-border rounded bg-ui-bg-2 text-ui-text">Cmd-K</kbd>
              to jump to any tab.
            </span>
          </div>
          <p className="text-sm text-ui-text-dim mt-3 max-w-3xl">{ROLE_BLURB[role]}</p>
        </header>

        {grouped.length === 0 && (
          <div className="mt-8 text-sm text-ui-text-dim">
            No featured workflows for this role. Use the tab strip or Cmd-K to navigate.
          </div>
        )}

        {grouped.map((section) => (
          <section key={section.group} className="mt-8">
            <div className="flex items-baseline gap-3 mb-3">
              <h2 className="text-[11px] uppercase tracking-[0.18em] text-ui-text-dim font-semibold">
                {GROUP_LABEL[section.group]}
              </h2>
              <div className="flex-1 h-px bg-ui-border/60" />
              <span className="text-[10px] text-ui-text-faint">{section.cards.length}</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {section.cards.map((card) => {
                const Icon = card.Icon;
                return (
                  <button
                    key={card.target}
                    onClick={() => onPick(card.target)}
                    className={`group relative text-left p-4 rounded-lg border ${card.accent} bg-ui-bg-1/60 hover:bg-ui-bg-2/70 hover:-translate-y-0.5 hover:shadow-lg transition-all`}
                  >
                    <div className="flex items-start gap-3">
                      <Icon size={22} className={`${card.iconColor} mt-0.5 shrink-0`} aria-hidden />
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-ui-text">{card.title}</div>
                        <div className="text-xs text-ui-text-dim mt-1 leading-relaxed">{card.blurb}</div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>
        ))}

        <div className="mt-12 pt-4 border-t border-ui-border/60 text-xs text-ui-text-faint leading-relaxed">
          <div className="font-semibold text-ui-text-dim mb-1">Tips</div>
          <div>• Status strip up top shows mission phase, sim clock, speed, and active-alarm count.</div>
          <div>• Red alarm badge = at least one CRITICAL event live. Click it to jump to Ops Log.</div>
          <div>• Every panel is self-contained — opening one never cancels work in another.</div>
          <div>• <kbd className="mx-0.5 px-1 py-0.5 text-[10px] border border-ui-border rounded bg-ui-bg-2 text-ui-text">Fullscreen</kbd> in the role bar hides sidebars + footer for a single-panel view.</div>
        </div>
      </div>
    </div>
  );
}
