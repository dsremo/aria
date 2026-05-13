/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'bg-primary':    '#0a0e17',
        'bg-panel':      '#111827',
        'bg-card':       '#1a2332',
        'border':        '#1e3a5f',
        'accent-cyan':   '#06b6d4',
        'accent-blue':   '#3b82f6',
        'accent-green':  '#10b981',
        'accent-red':    '#ef4444',
        'accent-orange': '#f97316',

        'ui-bg-0':          'rgb(var(--ui-bg-0)          / <alpha-value>)',
        'ui-bg-1':          'rgb(var(--ui-bg-1)          / <alpha-value>)',
        'ui-bg-2':          'rgb(var(--ui-bg-2)          / <alpha-value>)',
        'ui-bg-3':          'rgb(var(--ui-bg-3)          / <alpha-value>)',
        'ui-border-soft':   'rgb(var(--ui-border-soft)   / <alpha-value>)',
        'ui-border':        'rgb(var(--ui-border)        / <alpha-value>)',
        'ui-border-strong': 'rgb(var(--ui-border-strong) / <alpha-value>)',
        'ui-accent':        'rgb(var(--ui-accent)        / <alpha-value>)',
        'ui-accent-strong': 'rgb(var(--ui-accent-strong) / <alpha-value>)',
        'ui-text':          'rgb(var(--ui-text)          / <alpha-value>)',
        'ui-text-dim':      'rgb(var(--ui-text-dim)      / <alpha-value>)',
        'ui-text-faint':    'rgb(var(--ui-text-faint)    / <alpha-value>)',
        'sev-info':         'rgb(var(--sev-info)         / <alpha-value>)',
        'sev-ok':           'rgb(var(--sev-ok)           / <alpha-value>)',
        'sev-warn':         'rgb(var(--sev-warn)         / <alpha-value>)',
        'sev-crit':         'rgb(var(--sev-crit)         / <alpha-value>)',
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
      },
    },
  },
  plugins: [],
};
