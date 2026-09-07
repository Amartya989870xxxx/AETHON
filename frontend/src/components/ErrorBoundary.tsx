import { Component, type ErrorInfo, type ReactNode } from "react";
import { GlassPanel } from "./GlassPanel";
import { Button } from "./controls";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Stops one screen's render crash from blanking the whole dashboard. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Left as console output — no telemetry backend in scope.
    console.error("Screen crashed:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mx-auto max-w-lg py-16">
        <GlassPanel>
          <h2 className="text-sm font-semibold text-ink-100">
            This screen hit an error
          </h2>
          <p className="mt-2 text-xs leading-relaxed text-ink-400">
            {this.state.error.message}
          </p>
          <Button
            className="mt-4"
            variant="primary"
            size="sm"
            onClick={() => this.setState({ error: null })}
          >
            Reload screen
          </Button>
        </GlassPanel>
      </div>
    );
  }
}
