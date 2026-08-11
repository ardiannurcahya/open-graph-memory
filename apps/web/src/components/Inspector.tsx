import { X, Network, Calendar, GitFork, AlertTriangle } from "lucide-react";
import type { GraphState, GraphNode } from "../lib/graphTypes";

interface InspectorProps {
  node: GraphNode | null;
  state: GraphState;
  onSelectNode: (node: GraphNode) => void;
  onClose: () => void;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function Inspector({ node, state, onSelectNode, onClose }: InspectorProps) {
  if (!node) return null;

  const rels = state.adj.get(node.id) ?? [];
  const pct = Math.round(node.degFrac * 100);
  const commName = state.communities.get(node.community)?.name ?? node.community;

  return (
    <div
      id="inspector"
      className="absolute right-3 top-16 bottom-3 z-30 flex w-88 flex-col gap-3.5 overflow-y-auto rounded-2xl border border-mac bg-surface p-4 shadow-xl backdrop-blur-md text-main animate-in slide-in-from-right duration-200"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-mac pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-mac-accent text-white font-bold text-xs">
            <Network className="h-3.5 w-3.5" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-main uppercase tracking-wider">Node Inspector</h3>
            <p className="text-[10px] font-medium text-subdued truncate max-w-[180px]">{node.id}</p>
          </div>
        </div>
        <button
          onClick={onClose}
          type="button"
          aria-label="Close Inspector"
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-mac bg-muted text-subdued hover:text-main hover:bg-canvas transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Main Symbol Details Card */}
      <div className="rounded-xl border border-mac bg-muted p-4 space-y-2">
        <div className="flex items-center justify-between">
          <span className="rounded-full bg-mac-accent px-2.5 py-0.5 font-mono text-[10px] font-bold text-white shadow-sm">
            {node.type}
          </span>
          <span className="text-[11px] font-semibold text-subdued">
            {commName}
          </span>
        </div>

        <h2 className="text-base font-bold leading-tight text-main break-words">
          {node.label}
        </h2>

        <p className="text-xs leading-relaxed text-subdued">
          {node.description || "No description provided for this code symbol."}
        </p>

        {node.isExpired && (
          <div className="flex items-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-950/40 px-2.5 py-1 text-[11px] font-bold text-amber-700 dark:text-amber-300">
            <AlertTriangle className="h-3.5 w-3.5" />
            <span>EXPIRED ENTITY</span>
          </div>
        )}
      </div>

      {/* Connectivity & Degree Metric Card */}
      <div className="rounded-xl border border-mac bg-muted p-4 space-y-2.5">
        <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-subdued">
          <GitFork className="h-3.5 w-3.5 text-mac-accent" />
          <span>Graph Connectivity</span>
        </div>

        <div className="flex items-center gap-2.5">
          <span className="font-mono text-[10px] text-subdued">Degree</span>
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-canvas border border-mac">
            <div
              className="h-full rounded-full bg-mac-accent transition-all duration-300"
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="min-w-[40px] text-right font-mono text-xs font-bold text-main">
            {node.degree}/{state.maxDegree}
          </span>
        </div>

        <div className="text-right font-mono text-[10px] text-subdued">
          {pct}th percentile degree · Community {node.community}
        </div>
      </div>

      {/* Temporal Validity Card */}
      <div className="rounded-xl border border-mac bg-muted p-4 space-y-2">
        <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-subdued">
          <Calendar className="h-3.5 w-3.5 text-mac-accent" />
          <span>Temporal Validity</span>
        </div>

        <div className="space-y-1.5 text-xs">
          <div className="flex justify-between">
            <span className="text-subdued">Valid From</span>
            <span className="font-mono font-semibold text-main">{formatDate(node.validFrom)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-subdued">Valid Until</span>
            <span className="font-mono font-semibold text-main">
              {node.validUntil ? formatDate(node.validUntil) : "Current (Active)"}
            </span>
          </div>
        </div>
      </div>

      {/* Relationships List */}
      <div className="rounded-xl border border-mac bg-muted p-4 space-y-2.5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-wider text-subdued">
            Connected Graph Edges ({rels.length})
          </span>
        </div>

        {rels.length === 0 ? (
          <p className="text-xs text-subdued italic">No connections for this node.</p>
        ) : (
          <div className="space-y-1 max-h-60 overflow-y-auto pr-1">
            {rels.map((e) => {
              const oId = e.source === node.id ? e.target : e.source;
              const o = state.nodes.find((n) => n.id === oId);
              if (!o) return null;
              const dir = e.source === node.id ? "→" : "←";
              return (
                <button
                  key={e.id}
                  type="button"
                  onClick={() => onSelectNode(o)}
                  className="flex w-full items-center justify-between rounded-lg border border-mac bg-surface px-2.5 py-2 text-left hover:border-mac-accent transition-all duration-150 group"
                >
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded bg-muted font-mono text-xs font-bold text-mac-accent">
                      {dir}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-xs font-bold text-main group-hover:text-mac-accent transition-colors">
                        {o.label}
                      </div>
                      <div className="font-mono text-[10px] text-subdued truncate">
                        {e.label.replace(/_/g, " ")}
                      </div>
                    </div>
                  </div>
                  <span className="flex-shrink-0 font-mono text-[10px] font-semibold text-subdued ml-2">
                    d{o.degree}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
