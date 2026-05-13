import type { ReactNode } from 'react';

interface Props {
  title?: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export function Card({ title, subtitle, right, children, className = '', bodyClassName = '' }: Props) {
  return (
    <div className={`bg-ui-bg-1/60 border border-ui-border rounded-lg ${className}`}>
      {(title || right) && (
        <div className="flex items-start justify-between gap-2 px-3 pt-2 pb-1">
          <div className="min-w-0">
            {title && (
              <div className="text-[10px] uppercase tracking-wider text-ui-accent font-semibold truncate">
                {title}
              </div>
            )}
            {subtitle && <div className="text-[10px] text-ui-text-faint mt-0.5">{subtitle}</div>}
          </div>
          {right && <div className="shrink-0">{right}</div>}
        </div>
      )}
      <div className={`px-3 ${title ? 'pb-3' : 'py-3'} ${bodyClassName}`}>
        {children}
      </div>
    </div>
  );
}

export default Card;
