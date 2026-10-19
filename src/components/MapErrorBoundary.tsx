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

export default class MapErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, resetKey: 0 };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[MapErrorBoundary] AvalancheMap crashed:', error, errorInfo);
  }

  handleReload = () => {
    this.setState((prev) => ({ hasError: false, error: null, resetKey: prev.resetKey + 1 }));
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-full w-full flex-col items-center justify-center gap-4 bg-[radial-gradient(circle_at_top_left,_hsl(156_74%_45%_/_0.14),_transparent_28%),linear-gradient(180deg,hsl(224_28%_8%),hsl(224_24%_6%))] px-4">
          <div className="flex max-w-md flex-col items-center gap-3 rounded-2xl border border-amber-500/25 bg-black/65 px-6 py-5 text-center shadow-2xl shadow-black/25 backdrop-blur-xl">
            <AlertTriangle className="h-8 w-8 text-amber-400" />
            <div className="text-sm font-semibold uppercase tracking-[0.18em] text-amber-300">
              Map failed to load
            </div>
            <div className="text-xs text-muted-foreground">
              The avalanche map encountered an unexpected error. Try reloading the map surface.
            </div>
            <button
              type="button"
              onClick={this.handleReload}
              className="mt-1 inline-flex items-center gap-2 rounded-full border border-border/70 bg-card/80 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-foreground transition-colors hover:bg-card"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Reload map
            </button>
          </div>
        </div>
      );
    }

    return <div key={this.state.resetKey} className="h-full w-full">{this.props.children}</div>;
  }
}
