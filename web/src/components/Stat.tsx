import type { ReactNode } from 'react';

interface Props {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  tone?: 'default' | 'ok' | 'warn' | 'crit' | 'accent';
  className?: string;
}

const TONE_TEXT: Record<NonNullable<Props['tone']>, string> = {
  default: 'text-ui-text',
  ok:      'text-sev-ok',
  warn:    'text-sev-warn',
  crit:    'text-sev-crit',
  accent:  'text-ui-accent',
};

export function Stat({ label, value, unit, tone = 'default', className = '' }: Props) {
  return (
    <div className={className}>
      <div className="text-[9px] uppercase tracking-wide text-ui-text-faint">{label}</div>
      <div className={`font-mono ${TONE_TEXT[tone]}`}>
        {value}
        {unit && <span className="text-xs text-ui-text-dim ml-1">{unit}</span>}
      </div>
    </div>
  );
}

export default Stat;
