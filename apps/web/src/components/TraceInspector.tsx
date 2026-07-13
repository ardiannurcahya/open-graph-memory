import { Activity, AlertTriangle, CheckCircle, Clock, GitBranch, Layers, Route } from "lucide-react";

import type { QueryResponse, RetrievalMode } from "../lib/types";

interface TraceInspectorProps {
  result: QueryResponse | null;
  currentMode: RetrievalMode;
}

const GRAPH_STATUS_META: Record<string, { label: string; variant: string }> = {
  ok: { label: "Graph OK", variant: "ok" },
  fallback: { label: "Fallback", variant: "fallback" },
  not_requested: { label: "Not requested", variant: "idle" },
};

export function TraceInspector({ result, currentMode }: TraceInspectorProps) {
  const trace = result?.retrieval_trace;
  const graphTrace = trace?.graph;
  const graphStatus = graphTrace?.status ?? "not_requested";
  const statusMeta = GRAPH_STATUS_META[graphStatus] ?? {
    label: graphStatus,
    variant: "idle",
  };

  return (
    <section className="panel" id="trace" aria-labelledby="trace-heading">
      <div className="panel-header">
        <div>
          <span className="panel-eyebrow">Retrieval Trace</span>
          <h2 id="trace-heading" className="panel-title">
            Run Inspector
          </h2>
        </div>
        <span className={`trace-status trace-${statusMeta.variant}`}>
          {statusMeta.variant === "ok" && <CheckCircle size={12} strokeWidth={2} />}
          {statusMeta.variant === "fallback" && <AlertTriangle size={12} strokeWidth={2} />}
          {statusMeta.label}
        </span>
      </div>

      <div className="trace-metrics">
        <Metric
          icon={<Clock size={14} strokeWidth={2} />}
          label="Server Latency"
          value={trace ? `${trace.latency_ms.toFixed(1)} ms` : "—"}
        />
        <Metric
          icon={<Activity size={14} strokeWidth={2} />}
          label="Mode"
          value={trace?.mode ?? currentMode}
        />
        <Metric
          icon={<GitBranch size={14} strokeWidth={2} />}
          label="Trace ID"
          value={trace ? trace.trace_id.slice(0, 8) : "—"}
          mono
        />
      </div>

      <div className="trace-metrics">
        <Metric
          icon={<Layers size={14} strokeWidth={2} />}
          label="Prompt Tokens"
          value={result ? String(result.usage.prompt_tokens) : "—"}
        />
        <Metric
          icon={<Layers size={14} strokeWidth={2} />}
          label="Completion Tokens"
          value={result ? String(result.usage.completion_tokens) : "—"}
        />
        <Metric
          icon={<Layers size={14} strokeWidth={2} />}
          label="Est. Cost"
          value={result ? `$${result.usage.estimated_cost_usd.toFixed(6)}` : "—"}
        />
      </div>

      <div className="pipeline">
        <PipelineStage
          step="01"
          label="Vector Search"
          detail={trace ? `${trace.channel_candidates.vector.length} candidates` : "waiting"}
          done={Boolean(trace)}
        />
        <PipelineStage
          step="02"
          label="Graph Traversal"
          detail={
            graphTrace
              ? `${graphTrace.paths.length} paths${graphTrace.reason ? ` (${graphTrace.reason})` : ""}`
              : "waiting"
          }
          done={Boolean(graphTrace) && graphStatus !== "not_requested"}
          fallback={graphStatus === "fallback"}
        />
        <PipelineStage
          step="03"
          label="Fusion & Ranking"
          detail={trace ? `${trace.fusion.length} fused` : "waiting"}
          done={trace != null && trace.fusion.length > 0}
        />
        <PipelineStage
          step="04"
          label="Generation"
          detail={result ? "cited" : "waiting"}
          done={Boolean(result)}
        />
      </div>

      {graphTrace && graphTrace.paths.length > 0 && (
        <div className="trace-paths">
          <p className="trace-paths-label">
            <Route size={13} strokeWidth={2} />
            Retrieval Paths
          </p>
          {graphTrace.paths.slice(0, 8).map((path, i) => (
            <div key={`${path.chunk_id}-${i}`} className="trace-path">
              <span className="trace-path-index">{i + 1}</span>
              <span className="trace-path-chain">
                {path.path.length > 0 ? path.path.join(" → ") : path.chunk_id.slice(0, 12)}
              </span>
              <span className="trace-path-chunks">{path.evidence_chunk_ids.length} evidence</span>
            </div>
          ))}
        </div>
      )}

      <details className="raw-trace">
        <summary>Raw trace payload</summary>
        <pre className="raw-trace-body">{JSON.stringify(trace ?? {}, null, 2)}</pre>
      </details>
    </section>
  );
}

function Metric({
  icon,
  label,
  value,
  mono,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="metric">
      <div className="metric-label">
        {icon}
        {label}
      </div>
      <div className={`metric-value ${mono ? "mono" : ""}`}>{value}</div>
    </div>
  );
}

function PipelineStage({
  step,
  label,
  detail,
  done,
  fallback,
}: {
  step: string;
  label: string;
  detail: string;
  done: boolean;
  fallback?: boolean;
}) {
  return (
    <div className={`pipeline-stage ${done ? "is-done" : ""} ${fallback ? "is-fallback" : ""}`}>
      <span className="pipeline-step">{step}</span>
      <span className="pipeline-label">{label}</span>
      <span className="pipeline-detail">{detail}</span>
    </div>
  );
}
