import type { ReactNode } from 'react';

export type Severity = 'info' | 'ok' | 'warn' | 'crit' | 'neutral';

interface Props {
  severity: Severity;
  children: ReactNode;
  className?: string;
  variant?: 'soft' | 'solid' | 'dot';
}

const SOFT: Record<Severity, string> = {
  info:    'border-sev-info bg-sev-info/15 text-sev-info',
  ok:      'border-sev-ok   bg-sev-ok/15   text-sev-ok',
  warn:    'border-sev-warn bg-sev-warn/15 text-sev-warn',
  crit:    'border-sev-crit bg-sev-crit/20 text-sev-crit',
  neutral: 'border-ui-border bg-ui-bg-2/40 text-ui-text-dim',
};

const SOLID: Record<Severity, string> = {
  info:    'border-sev-info bg-sev-info text-white',
  ok:      'border-sev-ok   bg-sev-ok   text-white',
  warn:    'border-sev-warn bg-sev-warn text-white',
  crit:    'border-sev-crit bg-sev-crit text-white',
  neutral: 'border-ui-border bg-ui-bg-2 text-ui-text',
};

const DOT_COLOR: Record<Severity, string> = {
  info:    'bg-sev-info',
  ok:      'bg-sev-ok',
  warn:    'bg-sev-warn',
  crit:    'bg-sev-crit',
  neutral: 'bg-ui-text-faint',
};

export function SeverityBadge({ severity, children, className = '', variant = 'soft' }: Props) {
  if (variant === 'dot') {
    return (
      <span className={`inline-flex items-center gap-1.5 text-[10px] ${className}`}>
        <span className={`w-1.5 h-1.5 rounded-full ${DOT_COLOR[severity]}`} aria-hidden />
        {children}
      </span>
    );
  }
  const tone = variant === 'solid' ? SOLID[severity] : SOFT[severity];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] uppercase tracking-wider rounded border font-semibold ${tone} ${className}`}>
      {children}
    </span>
  );
}

export default SeverityBadge;
