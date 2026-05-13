import { useEffect, useState } from 'react';
import {
  X, Settings as SettingsIcon, Bell, Gauge, LayoutGrid,
  Users, Activity, RotateCcw, type LucideProps,
} from 'lucide-react';
import type { ComponentType, ReactNode } from 'react';
import { safeStorage } from '../safeStorage';
import type { Role } from '../App';

interface TabPreview {
  id: string;
  label: string;
  roles: (Role | 'ALL')[];
}

export type DefaultSpeed = 'paused' | '1' | '60' | '3600' | '86400' | '604800' | '2628000' | '31557600';
export type Density = 'compact' | 'comfortable' | 'spacious';

export interface AriaSettings {
  notificationsPaused: boolean;
  hideInfoToasts:      boolean;
  hideWarningToasts:   boolean;
  hideCriticalToasts:  boolean;
  reduceMotion:        boolean;
  fpsCounterDefault:   boolean;
  defaultSpeed:        DefaultSpeed;
  autostart:           boolean;
  telemetryDensity:    Density;
}

export const DEFAULT_SETTINGS: AriaSettings = {
  notificationsPaused: false,
  hideInfoToasts:      false,
  hideWarningToasts:   false,
  hideCriticalToasts:  false,
  reduceMotion:        false,
  fpsCounterDefault:   false,
  defaultSpeed:        '604800',
  autostart:           false,
  telemetryDensity:    'comfortable',
};

export const SPEED_LABELS: Record<DefaultSpeed, string> = {
  'paused':   'paused',
  '1':        '1× (real-time)',
  '60':       '1 min/s',
  '3600':     '1 hr/s',
  '86400':    '1 day/s',
  '604800':   '1 wk/s',
  '2628000':  '1 mo/s',
  '31557600': '1 yr/s',
};

const STORAGE_KEY = 'aria.settings.v1';

export function loadSettings(): AriaSettings {
  try {
    const raw = safeStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw);
    return { ...DEFAULT_SETTINGS, ...parsed };
  } catch { return DEFAULT_SETTINGS; }
}

export function saveSettings(s: AriaSettings): void {
  try { safeStorage.setItem(STORAGE_KEY, JSON.stringify(s)); } catch { /* quota */ }
}

const SETTINGS_EVENT = 'aria.settings.changed';

export function emitSettingsChanged(s: AriaSettings) {
  saveSettings(s);
  window.dispatchEvent(new CustomEvent<AriaSettings>(SETTINGS_EVENT, { detail: s }));
}

export function useSettings(): AriaSettings {
  const [s, setS] = useState<AriaSettings>(() => loadSettings());
  useEffect(() => {
    const onChange = (ev: Event) => setS((ev as CustomEvent<AriaSettings>).detail);
    window.addEventListener(SETTINGS_EVENT, onChange);
    return () => window.removeEventListener(SETTINGS_EVENT, onChange);
  }, []);
  return s;
}

interface Props {
  open: boolean;
  onClose: () => void;
  tabs?: ReadonlyArray<TabPreview>;
  roles?: ReadonlyArray<Role>;
  currentRole?: Role | 'ALL';
  onSetRole?: (r: Role | 'ALL') => void;
  roleDesc?: Record<string, string>;
}

type SectionKey = 'notifications' | 'simulation' | 'visual' | 'roles' | 'health';

const SECTIONS: { key: SectionKey; label: string; Icon: ComponentType<LucideProps> }[] = [
  { key: 'notifications', label: 'Notifications', Icon: Bell },
  { key: 'simulation',    label: 'Simulation',    Icon: Gauge },
  { key: 'visual',        label: 'Visual',        Icon: LayoutGrid },
  { key: 'roles',         label: 'Roles & tabs',  Icon: Users },
  { key: 'health',        label: 'Backend health', Icon: Activity },
];

export function SettingsPanel({ open, onClose, tabs = [], roles = [], currentRole, onSetRole, roleDesc }: Props) {
  const [s, setS] = useState<AriaSettings>(() => loadSettings());
  const [section, setSection] = useState<SectionKey>('notifications');

  useEffect(() => {
    if (open) setS(loadSettings());
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const [health, setHealth] = useState<{ apiStatus: number; advisorBackend: string; advisorCount: number; chainOk: boolean } | null>(null);
  useEffect(() => {
    if (!open) return;
    if (section !== 'health') return;
    let alive = true;
    setHealth(null);
    (async () => {
      try {
        const status = await fetch('/api/status');
        const decisions = await fetch('/api/ai/decisions').then(r => r.ok ? r.json() : null).catch(() => null);
        const chain = await fetch('/api/audit/chain_status').then(r => r.ok ? r.json() : null).catch(() => null);
        const recent: any[] = (decisions?.entries ?? []).slice(0, 8);
        const allRule = recent.length > 0 && recent.every((e: any) => e.backend === 'rule');
        if (!alive) return;
        setHealth({
          apiStatus: status.status,
          advisorBackend: recent.length === 0 ? 'no advisories yet' : (allRule ? 'rule-only (no LLM key)' : 'llm + rule'),
          advisorCount: decisions?.count ?? 0,
          chainOk: !!chain?.chain_intact,
        });
      } catch {
        if (alive) setHealth(null);
      }
    })();
    return () => { alive = false; };
  }, [open, section]);

  if (!open) return null;

  const update = <K extends keyof AriaSettings>(key: K, value: AriaSettings[K]) => {
    const next = { ...s, [key]: value };
    setS(next);
    emitSettingsChanged(next);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
         onClick={onClose}>
      <div className="bg-ui-bg-1 border border-ui-border-strong rounded-xl shadow-2xl w-[min(900px,94vw)] h-[min(640px,82vh)] flex flex-col overflow-hidden"
           onClick={(e) => e.stopPropagation()}>

        <div className="flex items-center justify-between px-5 py-3 border-b border-ui-border bg-ui-bg-1/80">
          <h2 className="text-base font-bold text-ui-accent inline-flex items-center gap-2">
            <SettingsIcon size={16} aria-hidden /> Settings
          </h2>
          <button onClick={onClose}
                  aria-label="Close settings"
                  className="text-ui-text-dim hover:text-ui-text p-1 rounded hover:bg-ui-bg-2 transition-colors">
            <X size={16} aria-hidden />
          </button>
        </div>

        <div className="flex flex-1 min-h-0">
          <nav className="w-48 shrink-0 border-r border-ui-border bg-ui-bg-1/60 overflow-y-auto py-2">
            {SECTIONS.map(({ key, label, Icon }) => {
              if (key === 'roles' && (tabs.length === 0 || roles.length === 0)) return null;
              const active = section === key;
              return (
                <button key={key}
                        onClick={() => setSection(key)}
                        className={`w-full text-left px-4 py-2 text-xs inline-flex items-center gap-2 border-l-2 transition-colors
                          ${active
                            ? 'border-ui-accent bg-ui-bg-2/60 text-ui-accent'
                            : 'border-transparent text-ui-text-dim hover:text-ui-text hover:bg-ui-bg-2/40'}`}>
                  <Icon size={14} aria-hidden />
                  {label}
                </button>
              );
            })}
          </nav>

          <div className="flex-1 min-w-0 overflow-y-auto px-6 py-5">
            {section === 'notifications' && (
              <Section title="Notifications"
                       blurb="Toast popups appear in the bottom-right when warning or critical events fire. Alarms always remain in Ops Log → Alarms regardless of these settings.">
                <Toggle label="Pause all notifications"
                        hint="Silence every toast popup."
                        checked={s.notificationsPaused}
                        onChange={(v) => update('notificationsPaused', v)} />
                <div className="pl-6 space-y-2 mt-2">
                  <Toggle label="Hide info-level toasts"
                          checked={s.hideInfoToasts}
                          onChange={(v) => update('hideInfoToasts', v)}
                          disabled={s.notificationsPaused} />
                  <Toggle label="Hide warning toasts"
                          checked={s.hideWarningToasts}
                          onChange={(v) => update('hideWarningToasts', v)}
                          disabled={s.notificationsPaused} />
                  <Toggle label="Hide critical toasts"
                          hint="Not recommended — critical events stay in Ops Log either way."
                          checked={s.hideCriticalToasts}
                          onChange={(v) => update('hideCriticalToasts', v)}
                          disabled={s.notificationsPaused} />
                </div>
              </Section>
            )}

            {section === 'simulation' && (
              <Section title="Simulation"
                       blurb="The voyage takes years of sim-time. At 1× speed (real-time) almost nothing visible changes; pick a fast preset so the trajectory unfolds in seconds.">
                <Field label="Default speed when ▶ Play is pressed"
                       hint="The speed used when nothing is staged. Default 1 wk/s.">
                  <select value={s.defaultSpeed}
                          onChange={(e) => update('defaultSpeed', e.target.value as DefaultSpeed)}
                          className="bg-ui-bg-2 border border-ui-border-strong rounded px-3 py-1.5 text-xs text-ui-text font-medium cursor-pointer hover:border-ui-accent focus:border-ui-accent focus:outline-none">
                    {(Object.keys(SPEED_LABELS) as DefaultSpeed[]).map((k) => (
                      <option key={k} value={k}>{SPEED_LABELS[k]}</option>
                    ))}
                  </select>
                </Field>
                <Toggle label="Auto-start simulation on dashboard load"
                        hint="When the page mounts, immediately call Play at the default speed above."
                        checked={s.autostart}
                        onChange={(v) => update('autostart', v)} />
              </Section>
            )}

            {section === 'visual' && (
              <Section title="Visual"
                       blurb="Tunable layout density and motion. The Ctrl-/ Cmd-, shortcut opens this dialog from anywhere.">
                <Field label="Telemetry density"
                       hint="Affects card sizing on Telemetry / EECOM / Crew & Life. Compact uses 6 cols on wide displays; spacious uses 3.">
                  <SegmentedControl
                    options={[
                      { value: 'compact',     label: 'Compact' },
                      { value: 'comfortable', label: 'Comfortable' },
                      { value: 'spacious',    label: 'Spacious' },
                    ]}
                    value={s.telemetryDensity}
                    onChange={(v) => update('telemetryDensity', v as Density)} />
                </Field>
                <Toggle label="Reduce motion"
                        hint="Disable hover-lift transitions and animated icons."
                        checked={s.reduceMotion}
                        onChange={(v) => update('reduceMotion', v)} />
                <Toggle label="Show FPS counter by default"
                        hint="Affects new sessions only — toggle on the FPS button to change now."
                        checked={s.fpsCounterDefault}
                        onChange={(v) => update('fpsCounterDefault', v)} />
              </Section>
            )}

            {section === 'roles' && (
              <Section title="Roles & tabs"
                       blurb="Pick a role to filter the tab strip. Cmd-K still reaches every tab regardless. Click a role card to switch immediately.">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {(['ALL', ...roles] as (Role | 'ALL')[]).map((r) => {
                    const visible = r === 'ALL'
                      ? tabs
                      : tabs.filter((t) => t.roles.includes('ALL') || t.roles.includes(r));
                    const active = currentRole === r;
                    const desc = roleDesc?.[r as string];
                    const Wrap: React.ElementType = onSetRole ? 'button' : 'div';
                    return (
                      <Wrap
                        key={r}
                        {...(onSetRole ? { onClick: () => onSetRole(r), type: 'button' } : {})}
                        className={`text-left rounded-lg border p-3 transition-colors ${
                          active
                            ? 'border-ui-accent bg-ui-accent/15'
                            : onSetRole
                              ? 'border-ui-border bg-ui-bg-2/30 hover:bg-ui-bg-2/60 cursor-pointer'
                              : 'border-ui-border bg-ui-bg-2/30'
                        }`}>
                        <div className="flex items-baseline justify-between mb-1">
                          <span className={`text-xs font-mono font-semibold ${active ? 'text-ui-accent' : 'text-ui-text'}`}>
                            {r} {active && <span className="text-[9px] uppercase tracking-wider text-ui-accent ml-1">active</span>}
                          </span>
                          <span className="text-[10px] text-ui-text-faint">{visible.length} tabs</span>
                        </div>
                        {desc && <div className="text-[11px] text-ui-text-dim mb-2 leading-snug">{desc}</div>}
                        <div className="flex flex-wrap gap-1">
                          {visible.map((t) => (
                            <span key={t.id}
                                  className="inline-block px-1.5 py-0.5 text-[10px] rounded bg-ui-bg-1 border border-ui-border text-ui-text-dim">
                              {t.label}
                            </span>
                          ))}
                        </div>
                      </Wrap>
                    );
                  })}
                </div>
              </Section>
            )}

            {section === 'health' && (
              <Section title="Backend health"
                       blurb="Live snapshot of the dashboard backend. If something is red, the corresponding feature won't behave correctly until you fix it.">
                {!health ? (
                  <div className="text-xs text-ui-text-faint">checking…</div>
                ) : (
                  <div className="space-y-2">
                    <HealthRow ok={health.apiStatus === 200}
                               label="HTTP API"
                               detail={`/api/status → ${health.apiStatus}`} />
                    <HealthRow ok={health.advisorBackend !== 'rule-only (no LLM key)'}
                               label="AI Advisor"
                               detail={`${health.advisorBackend} (${health.advisorCount} decisions)`} />
                    <HealthRow ok={health.chainOk}
                               label="Audit chain"
                               detail={health.chainOk ? 'intact' : 'broken or unavailable'} />
                  </div>
                )}
                <div className="mt-4 p-3 rounded-lg border border-sev-info/40 bg-sev-info/10 text-[11px] text-ui-text-dim leading-relaxed">
                  <strong className="text-sev-info">For LLM advisories</strong>, restart the
                  dashboard with{' '}
                  <code className="text-ui-accent">ANTHROPIC_API_KEY</code> exported in the
                  shell environment. The rule fallback keeps working either way.
                </div>
              </Section>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between gap-2 px-5 py-3 border-t border-ui-border bg-ui-bg-1/60">
          <button onClick={() => { setS(DEFAULT_SETTINGS); emitSettingsChanged(DEFAULT_SETTINGS); }}
                  className="inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded border border-ui-border text-ui-text-dim hover:bg-ui-bg-2 hover:text-ui-text transition-colors">
            <RotateCcw size={12} aria-hidden /> Reset to defaults
          </button>
          <div className="text-[10px] text-ui-text-faint">
            Saved as <code className="text-ui-text-dim">aria.settings.v1</code>
            <span className="mx-2 opacity-50">·</span>
            <kbd className="px-1 py-0.5 text-[9px] border border-ui-border rounded bg-ui-bg-2 text-ui-text">Esc</kbd> to close
          </div>
        </div>
      </div>
    </div>
  );
}

function Section({ title, blurb, children }: { title: string; blurb?: string; children: ReactNode }) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-ui-text">{title}</h3>
        {blurb && <p className="text-[11px] text-ui-text-faint mt-1 max-w-prose leading-relaxed">{blurb}</p>}
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-sm text-ui-text">{label}</div>
      {hint && <div className="text-[11px] text-ui-text-faint mt-0.5 max-w-prose leading-relaxed">{hint}</div>}
      <div className="mt-2">{children}</div>
    </div>
  );
}

function Toggle({ label, hint, checked, onChange, disabled }: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className={`flex items-start gap-3 py-1 ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}>
      <input type="checkbox"
             checked={checked}
             disabled={disabled}
             onChange={(e) => onChange(e.target.checked)}
             className="mt-0.5 accent-ui-accent w-4 h-4" />
      <div className="flex-1 min-w-0">
        <div className="text-sm text-ui-text">{label}</div>
        {hint && <div className="text-[11px] text-ui-text-faint mt-0.5 leading-relaxed">{hint}</div>}
      </div>
    </label>
  );
}

function SegmentedControl<V extends string>({ options, value, onChange }: {
  options: { value: V; label: string }[];
  value: V;
  onChange: (v: V) => void;
}) {
  return (
    <div className="inline-flex rounded-lg border border-ui-border overflow-hidden">
      {options.map((opt) => (
        <button key={opt.value}
                onClick={() => onChange(opt.value)}
                className={`px-3 py-1.5 text-xs transition-colors ${value === opt.value
                  ? 'bg-ui-accent/20 text-ui-accent font-medium'
                  : 'bg-ui-bg-1 text-ui-text-dim hover:bg-ui-bg-2 hover:text-ui-text'}`}>
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function HealthRow({ ok, label, detail }: { ok: boolean; label: string; detail: string }) {
  return (
    <div className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg border border-ui-border bg-ui-bg-2/40">
      <div className="flex items-center gap-2 min-w-0">
        <span className={`w-2 h-2 rounded-full shrink-0 ${ok ? 'bg-sev-ok' : 'bg-sev-crit'}`} aria-hidden />
        <span className="text-sm text-ui-text">{label}</span>
      </div>
      <span className={`text-[11px] font-mono truncate ${ok ? 'text-ui-text-dim' : 'text-sev-crit'}`}>{detail}</span>
    </div>
  );
}

export default SettingsPanel;
