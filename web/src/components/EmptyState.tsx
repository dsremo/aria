import type { ComponentType, ReactNode } from 'react';
import { Inbox, type LucideProps } from 'lucide-react';

interface Props {
  Icon?: ComponentType<LucideProps>;
  title?: ReactNode;
  hint?: ReactNode;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

const PADDING: Record<NonNullable<Props['size']>, string> = {
  sm: 'p-4',
  md: 'p-6',
  lg: 'p-10',
};

const ICON_SIZE: Record<NonNullable<Props['size']>, number> = {
  sm: 20,
  md: 28,
  lg: 36,
};

export function EmptyState({ Icon = Inbox, title, hint, className = '', size = 'md' }: Props) {
  return (
    <div className={`flex flex-col items-center justify-center text-center text-ui-text-dim ${PADDING[size]} ${className}`}>
      <Icon size={ICON_SIZE[size]} className="text-ui-text-faint mb-2" aria-hidden />
      {title && <div className="text-sm text-ui-text">{title}</div>}
      {hint && <div className="text-xs text-ui-text-faint mt-1 max-w-md">{hint}</div>}
    </div>
  );
}

export default EmptyState;
