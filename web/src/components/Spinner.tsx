interface Props {
  size?: number;
  className?: string;
  label?: string;
}

export function Spinner({ size = 14, className = '', label }: Props) {
  return (
    <span className={`inline-flex items-center gap-2 text-ui-text-dim ${className}`} role="status" aria-live="polite">
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
           xmlns="http://www.w3.org/2000/svg" className="animate-spin"
           aria-hidden>
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" />
        <path d="M22 12a10 10 0 0 1-10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      </svg>
      {label && <span className="text-xs">{label}</span>}
    </span>
  );
}

export default Spinner;
