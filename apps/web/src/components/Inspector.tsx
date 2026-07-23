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
      className="absolute right-0 top-0 bottom-0 z-20 flex w-80 flex-col gap-3 overflow-y-auto border-l border-ui-border bg-ui-surface p-4"
    >
      <button
        onClick={onClose}
        className="absolute right-3 top-3 flex h-7 w-7 items-center justify-center rounded border border-ui-border text-ui-subdued hover:bg-ui-muted"
      >
        ×
      </button>

      <div className="rounded-lg border border-ui-border bg-ui-muted p-4">
        <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-ui-subdued">
          {node.type} · {commName}
        </div>
        <div className="text-lg font-semibold leading-tight text-ui-text">{node.label}</div>
        <div className="mt-2 text-sm leading-relaxed text-ui-subdued">
          {node.description || "No description available."}
        </div>
        {node.isExpired && (
          <div className="mt-2 inline-block rounded bg-amber-100 px-2 py-0.5 font-mono text-[10px] text-amber-700">
            EXPIRED
          </div>
        )}
      </div>

      <div className="rounded-lg border border-ui-border bg-ui-muted p-4">
        <div className="mb-2.5 font-mono text-[10px] uppercase tracking-wider text-stone-400">
          Temporal
        </div>
        <div className="space-y-1 text-[11px]">
          <div className="flex justify-between">
            <span className="text-stone-400">Valid from</span>
            <span className="font-mono text-stone-600">{formatDate(node.validFrom)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-stone-400">Valid until</span>
            <span className="font-mono text-stone-600">
              {node.validUntil ? formatDate(node.validUntil) : "current"}
            </span>
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-ui-border bg-ui-muted p-4">
        <div className="mb-2.5 font-mono text-[10px] uppercase tracking-wider text-stone-400">
          Connectivity
        </div>
        <div className="flex items-center gap-2.5">
          <span className="font-mono text-[10px] whitespace-nowrap text-stone-400">Degree</span>
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-stone-200">
            <div
              className="h-full rounded-full bg-stone-700 transition-all duration-300"
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="min-w-[30px] text-right font-mono text-[11px] font-semibold text-stone-700">
            {node.degree}/{state.maxDegree}
          </span>
        </div>
        <div className="mt-1 text-right font-mono text-[9px] text-stone-400">
          {pct}th percentile · Community {node.community}
        </div>
      </div>

      <div className="rounded-lg border border-ui-border bg-ui-muted p-4">
        <div className="mb-2.5 font-mono text-[10px] uppercase tracking-wider text-stone-400">
          Relationships ({rels.length})
        </div>
        {rels.length === 0 ? (
          <p className="text-sm text-stone-400">No connections.</p>
        ) : (
          rels.map((e) => {
            const oId = e.source === node.id ? e.target : e.source;
            const o = state.nodes.find((n) => n.id === oId);
            if (!o) return null;
            const dir = e.source === node.id ? "→" : "←";
            const oCol = state.communities.get(o.community)?.color ?? "#78716c";
            return (
              <div
                key={e.id}
                onClick={() => onSelectNode(o)}
                className="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 transition-colors hover:bg-stone-100"
              >
                <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center font-mono text-[9px] text-stone-500">
                  {dir}
                </span>
                <div className="min-w-0 flex-1">
                  <div
                    className="truncate text-[11px] font-semibold"
                    style={{ color: oCol }}
                  >
                    {o.label}
                    {e.isExpired && (
                      <span className="ml-1 text-[9px] text-amber-500">(expired)</span>
                    )}
                  </div>
                  <div className="font-mono text-[9px] text-stone-400">
                    {e.label.replace(/_/g, " ")}
                  </div>
                </div>
                <span className="flex-shrink-0 font-mono text-[9px] text-stone-400">
                  d{o.degree}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
