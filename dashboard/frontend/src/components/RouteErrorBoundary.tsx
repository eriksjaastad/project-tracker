import { Component, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';

interface Props {
  children: ReactNode;
}

interface State {
  failed: boolean;
}

/**
 * Catches a page that fails to load or render, so the rest of the app stays.
 *
 * The chart pages load as separate chunks, and a rebuild replaces those
 * chunks. A tab opened before a redeploy (or offline) can't fetch them; without
 * this the whole app, navigation included, would unmount to a blank page.
 */
class RouteErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error('Page failed to load:', error);
  }

  render() {
    if (!this.state.failed) {
      return this.props.children;
    }
    return (
      <div className="route-error" role="alert">
        <p>This page couldn't load. The dashboard may have been updated since this tab was opened.</p>
        <button type="button" onClick={() => window.location.reload()}>
          Reload
        </button>
      </div>
    );
  }
}

/** One boundary per path, so moving to another page clears a failure. */
export function PageBoundary({ children }: Props) {
  const location = useLocation();
  return <RouteErrorBoundary key={location.pathname}>{children}</RouteErrorBoundary>;
}
