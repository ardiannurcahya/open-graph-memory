import { Component, lazy, Suspense, useEffect } from "react";
import type { ErrorInfo, ReactNode } from "react";
import type { GraphNode, GraphState } from "../lib/graphTypes";

const SigmaGraphCanvas = lazy(() => import("./SigmaGraphCanvas"));

interface GraphCanvasProps {
  state: GraphState;
  physicsEnabled: boolean;
  showLabels: boolean;
  activeFilters: Set<string>;
  selectedNodeId: string | null;
  onNodeSelect: (node: GraphNode | null) => void;
  onCameraChange?: (zoom: number) => void;
  onLayoutProgress?: (pct: number) => void;
}

export function GraphCanvas(props: GraphCanvasProps) {
  useEffect(() => undefined, [props.state]);
  return (
    <GraphErrorBoundary resetKey={props.state} fallback={(error) => <RendererUnavailable error={error} />}>
      <Suspense fallback={<div className="absolute inset-0 flex items-center justify-center text-sm text-ui-subdued">Loading renderer…</div>}>
        <SigmaGraphCanvas {...props} />
      </Suspense>
    </GraphErrorBoundary>
  );
}

function RendererUnavailable({ error }: { error: Error | null }) {
  return (
    <div className="absolute inset-0 flex items-center justify-center p-8 text-center text-sm text-ui-subdued">
      <div>
        <p>The graph renderer crashed. Reload the page to try again.</p>
        {error && <p className="mt-2 max-w-xl font-mono text-xs text-red-700">{error.message}</p>}
      </div>
    </div>
  );
}

interface GraphErrorBoundaryProps {
  resetKey: GraphState;
  fallback: (error: Error | null) => ReactNode;
  children: ReactNode;
}

class GraphErrorBoundary extends Component<GraphErrorBoundaryProps, { error: Error | null }> {
  state = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Graph renderer failed; showing unavailable message.", error, info.componentStack);
  }

  componentDidUpdate(previous: GraphErrorBoundaryProps) {
    if (this.state.error && previous.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    return this.state.error ? this.props.fallback(this.state.error) : this.props.children;
  }
}
