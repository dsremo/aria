import type { ButtonHTMLAttributes, ReactNode } from 'react';

export type HeaderButtonTone = 'default' | 'success' | 'info' | 'toggleOn' | 'toggleOff';

const TONE_CLASSES: Record<HeaderButtonTone, string> = {
  default:   'border-ui-border text-ui-text hover:bg-ui-bg-2',
  success:   'border-sev-ok bg-sev-ok/15 text-ui-text hover:bg-sev-ok/25',
  info:      'border-sev-info bg-sev-info/15 text-ui-text hover:bg-sev-info/25',
  toggleOn:  'border-ui-accent-strong bg-ui-bg-2 text-ui-accent',
  toggleOff: 'border-ui-border text-ui-text-dim hover:bg-ui-bg-2 hover:text-ui-text',
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  tone?: HeaderButtonTone;
  children: ReactNode;
}

export function HeaderButton({ tone = 'default', className = '', children, ...rest }: Props) {
  return (
    <button
      {...rest}
      className={`inline-flex items-center gap-1.5 px-2 py-1 rounded border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ui-accent focus-visible:ring-offset-1 focus-visible:ring-offset-ui-bg-1 ${TONE_CLASSES[tone]} ${className}`}
    >
      {children}
    </button>
  );
}

export default HeaderButton;
