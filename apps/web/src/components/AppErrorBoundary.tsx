/**
 * Root error boundary — the anti-blank-page guard.
 *
 * React 18 unmounts the ENTIRE app when any component throws during render,
 * which the user experiences as a blank white page with no explanation. This
 * boundary catches that crash at the root and renders an honest error screen
 * with the actual message and a reload action instead.
 *
 * It never swallows the failure silently: the error text is shown on screen
 * and logged through console.error for the browser console / DevTools.
 */
import { Component, type ErrorInfo, type ReactNode } from 'react';

import { Icon } from './Icon';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class AppErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // Keep the crash visible in the browser console for diagnosis.
    console.error('[METRASIGHT] Uncaught UI error:', error, info.componentStack);
  }

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="state state--error" role="alert" style={{ minHeight: '100vh' }}>
        <span className="state__icon">
          <Icon name="alert" size={22} />
        </span>
        <p className="state__title">The application hit an unexpected error</p>
        <p className="state__msg">
          {error.message || 'Unknown error'} — the page was not lost; reload to recover. If this
          keeps happening after a reload, the dev server may have restarted under a stale tab
          (hard refresh with Ctrl+Shift+R).
        </p>
        <button
          type="button"
          className="btn btn--subtle"
          onClick={() => window.location.reload()}
        >
          <Icon name="reset" size={15} />
          Reload application
        </button>
      </div>
    );
  }
}
