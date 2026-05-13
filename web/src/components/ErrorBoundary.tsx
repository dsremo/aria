/**
 * Shared React error boundary — contains render-time failures so they don't
 * blank the whole dashboard.
 *
 * Why this exists
 * ---------------
 * When a tab uses WebGL (Three.js) and the browser cannot create a WebGL
 * context (headless Chrome with `--disable-gpu`, Chrome's remote-debug
 * sandbox, a crashed GPU process, or a driver bug), the Canvas component
 * throws during render.  Without a boundary, the error propagates to the
 * nearest React root, which tears down the entire component tree and leaves
 * the user with a blank page.  Before this shared boundary landed, opening
 * Solar System 3D in a headless-Chrome walkthrough blanked every tab and
 * required a hard page reload to recover (see docs/UI_WALKTHROUGH_BUGS.md
 * BUG-004).
 *
 * Usage
 * -----
 *   import { ErrorBoundary } from './ErrorBoundary';
 *
 *   <ErrorBoundary fallback={(err) => <Fallback error={err} />}>
 *     <WebGLHeavyComponent />
 *   </ErrorBoundary>
 *
 * A default fallback is exported for the common "3D view unavailable" case;
 * callers can pass their own for richer copy.
 */

import { Component, type ReactNode } from 'react';

type FallbackRender = (err: unknown, reset: () => void) => ReactNode;

export class ErrorBoundary extends Component<
  { children: ReactNode; fallback: FallbackRender; label?: string },
  { err: unknown | null }
> {
  state = { err: null as unknown };

  static getDerivedStateFromError(err: unknown) {
    return { err };
  }

  componentDidCatch(err: unknown, info: unknown) {
    // Log for devs; keep the UI path simple.
    const tag = this.props.label ?? 'ErrorBoundary';
    // eslint-disable-next-line no-console
    console.error(`[${tag}]`, err, info);
  }

  reset = () => this.setState({ err: null });

  render() {
    if (this.state.err !== null) {
      return this.props.fallback(this.state.err, this.reset);
    }
    return this.props.children;
  }
}

/**
 * Default fallback styled for the dark ARIA dashboard — used by WebGL tabs
 * so they degrade gracefully when GPU acceleration is unavailable.
 */
export function WebGLUnavailableFallback({
  error,
  onReset,
  label = 'this 3D view',
}: {
  error: unknown;
  onReset?: () => void;
  label?: string;
}) {
  const message = error instanceof Error ? error.message : String(error ?? '');
  const isWebGL = /webgl/i.test(message);

  return (
    <div className="flex flex-col items-center justify-center h-full w-full p-6 bg-ui-bg-1/40 border border-ui-border rounded">
      <div className="text-lg text-sev-warn font-semibold mb-2">
        {isWebGL ? '3D view unavailable' : 'Render error'}
      </div>
      <div className="text-sm text-ui-text max-w-md text-center mb-3">
        {isWebGL
          ? `Your browser could not initialise a WebGL context for ${label}. This usually means GPU acceleration is disabled (headless Chrome, VM without a GPU, or the --disable-gpu flag). The rest of the dashboard keeps working.`
          : `Something went wrong rendering ${label}. The rest of the dashboard keeps working.`}
      </div>
      {message && (
        <div className="text-xs text-ui-text-dim font-mono max-w-lg text-center mb-3 whitespace-pre-wrap break-words">
          {message.slice(0, 300)}
        </div>
      )}
      {onReset && (
        <button
          onClick={onReset}
          className="px-3 py-1 text-xs border border-ui-border-strong rounded hover:bg-ui-bg-2 text-ui-text"
        >
          Retry
        </button>
      )}
    </div>
  );
}
