import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  resetKey: number;
}

export default class AppErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, resetKey: 0 };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[AppErrorBoundary] Uncaught error:', error, errorInfo);
  }

  handleReload = () => {
    this.setState((prev) => ({ hasError: false, error: null, resetKey: prev.resetKey + 1 }));
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background px-4">
          <div className="flex max-w-md flex-col items-center gap-3 rounded-2xl border border-amber-500/25 bg-card/80 px-6 py-5 text-center shadow-2xl">
            <AlertTriangle className="h-8 w-8 text-amber-400" />
            <div className="text-sm font-semibold uppercase tracking-[0.18em] text-amber-300">
              Something went wrong
            </div>
            <div className="text-xs text-muted-foreground">
              The application encountered an unexpected error. Try reloading to recover.
            </div>
            {this.state.error && (
              <div className="mt-1 w-full rounded-lg border border-border/50 bg-secondary/20 p-2 text-left">
                <code className="text-[10px] font-mono text-muted-foreground">
                  Error ID: {this.state.resetKey}
                </code>
              </div>
            )}
            <button
              type="button"
              onClick={this.handleReload}
              className="mt-1 inline-flex items-center gap-2 rounded-full border border-border/70 bg-card/80 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-foreground transition-colors hover:bg-card"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Try again
            </button>
          </div>
        </div>
      );
    }

    return <div key={this.state.resetKey}>{this.props.children}</div>;
  }
}
