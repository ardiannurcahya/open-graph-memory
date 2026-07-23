import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Sigma from "sigma";
import { agentMemoryApi } from "../api/endpoints";
import type { MemoryGraphView, MemoryGraphNode, MemoryEdgeType, MemoryNodeType } from "../api/types";

const NODE_COLORS: Record<MemoryNodeType, string> = {
  episode: "#3b82f6",
  attempt: "#f59e0b",
  outcome: "#10b981",
  pattern: "#8b5cf6",
  verifier: "#14b8a6",
  evidence: "#6b7280",
};

const EDGE_COLORS: Record<MemoryEdgeType, string> = {
  has_attempt: "#f59e0b",
  has_outcome: "#10b981",
  matches_pattern: "#8b5cf6",
  verified_by: "#14b8a6",
  has_evidence: "#6b7280",
  supersedes: "#ef4444",
};

const RESERVED_NODE_KEYS = new Set([
  "x", "y", "size", "color", "label", "nodeType", "status", "domain",
  "hidden", "highlighted", "forceLabel", "type", "zIndex",
]);

function seedPositions(nodes: MemoryGraphNode[]): Record<string, { x: number; y: number }> {
  const groups = new Map<string, MemoryGraphNode[]>();
  for (const node of nodes) {
    const key = node.type;
    const arr = groups.get(key) ?? [];
    arr.push(node);
    groups.set(key, arr);
  }

  const groupKeys = [...groups.keys()].sort((a, b) => (groups.get(b)?.length ?? 0) - (groups.get(a)?.length ?? 0));
  const centers: Record<string, { x: number; y: number }> = {};
  const radius = 10 + Math.sqrt(nodes.length) * 2;

  groupKeys.forEach((key, i) => {
    if (i === 0) {
      centers[key] = { x: 0, y: 0 };
    } else {
      const angle = ((i - 1) / Math.max(1, groupKeys.length - 1)) * Math.PI * 2;
      centers[key] = { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
    }
  });

  const positions: Record<string, { x: number; y: number }> = {};
  for (const [groupKey, members] of groups) {
    const center = centers[groupKey] ?? { x: 0, y: 0 };
    const branchRadius = 3 + Math.sqrt(members.length) * 0.8;
    members.forEach((node, i) => {
      const angle = (i / Math.max(1, members.length)) * Math.PI * 2 * 3;
      const r = branchRadius * Math.sqrt((i + 0.5) / members.length);
      positions[node.id] = {
        x: center.x + r * Math.cos(angle),
        y: center.y + r * Math.sin(angle),
      };
    });
  }
  return positions;
}

function buildGraph(data: MemoryGraphView): Graph {
  const graph = new Graph({ multi: true });
  const positions = seedPositions(data.nodes);

  for (const node of data.nodes) {
    const pos = positions[node.id] ?? { x: 0, y: 0 };
    const safeMeta: Record<string, unknown> = {};
    if (node.metadata) {
      for (const [k, v] of Object.entries(node.metadata)) {
        if (!RESERVED_NODE_KEYS.has(k)) safeMeta[k] = v;
      }
    }
    graph.addNode(node.id, {
      x: pos.x,
      y: pos.y,
      label: node.label,
      size: node.type === "episode" ? 14 : node.type === "pattern" ? 12 : node.type === "outcome" ? 10 : 6,
      color: NODE_COLORS[node.type] ?? "#6b7280",
      nodeType: node.type,
      status: node.status ?? "",
      domain: node.domain ?? "",
      ...safeMeta,
    });
  }

  for (const edge of data.edges) {
    if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) continue;
    if (edge.source === edge.target) continue;
    graph.addEdgeWithKey(edge.id, edge.source, edge.target, {
      size: edge.type === "supersedes" ? 2 : 1,
      color: EDGE_COLORS[edge.type] ?? "#d1d5db",
      edgeType: edge.type,
    });
  }

  return graph;
}

function getConnectedNodes(graph: Graph, nodeId: string): Set<string> {
  const connected = new Set<string>();
  connected.add(nodeId);
  graph.forEachNeighbor(nodeId, (neighbor) => connected.add(neighbor));
  return connected;
}

export default function AgentMemoryPage() {
  const [data, setData] = useState<MemoryGraphView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [domainFilter, setDomainFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [selectedNode, setSelectedNode] = useState<MemoryGraphNode | null>(null);
  const [layoutPct, setLayoutPct] = useState(0);

  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const selectedNodeRef = useRef<string | null>(null);
  const highlightedRef = useRef<Set<string>>(new Set());
  const layoutFramesRef = useRef<Set<number>>(new Set());
  const dataRef = useRef<MemoryGraphView | null>(null);
  const selectedNodeDataRef = useRef<MemoryGraphNode | null>(null);

  dataRef.current = data;
  selectedNodeDataRef.current = selectedNode;

  const cancelLayoutFrames = useCallback(() => {
    for (const frame of layoutFramesRef.current) cancelAnimationFrame(frame);
    layoutFramesRef.current.clear();
  }, []);

  const scheduleLayoutFrame = useCallback((callback: () => void) => {
    const frame = requestAnimationFrame(() => {
      layoutFramesRef.current.delete(frame);
      callback();
    });
    layoutFramesRef.current.add(frame);
  }, []);

  // Fetch graph data with AbortController
  const fetchGraph = useCallback(async () => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = {};
      if (domainFilter) params.domain = domainFilter;
      if (statusFilter) params.status = statusFilter;
      const result = await agentMemoryApi.getGraph(params);
      if (!controller.signal.aborted) {
        setData(result);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : "Failed to load Agent Memory graph");
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
    return () => controller.abort();
  }, [domainFilter, statusFilter]);

  useEffect(() => {
    const cleanup = fetchGraph();
    return () => { void cleanup.then((abort) => abort()); };
  }, [fetchGraph]);

  const graph = useMemo(() => (data ? buildGraph(data) : null), [data]);

  // Sigma lifecycle: init, layout, cleanup
  useEffect(() => {
    const container = containerRef.current;
    if (!graph || !container) return;
    if (sigmaRef.current) {
      sigmaRef.current.kill();
      sigmaRef.current = null;
    }
    if (graph.order === 0) return;

    let disposed = false;

    try {
      const N = graph.order;
      const dark = document.documentElement.classList.contains("dark");

      const sigma = new Sigma(graph, container, {
        allowInvalidContainer: true,
        renderEdgeLabels: false,
        labelRenderedSizeThreshold: 6,
        defaultEdgeColor: dark ? "#2a2a3a" : "#c8c6c0",
        labelColor: { color: dark ? "#a8a8b8" : "#404050" },
        minCameraRatio: 0.05,
        maxCameraRatio: 10,
        nodeReducer: (_node, data) => {
          const sel = selectedNodeRef.current;
          const highlighted = highlightedRef.current;
          if (sel) {
            if (_node === sel) return { ...data, highlighted: true };
            if (highlighted.has(_node)) return { ...data, highlighted: true };
            return { ...data, color: dark ? "#1a1a2a" : "#d8d6d0", zIndex: 0 };
          }
          return data;
        },
        edgeReducer: (edge) => {
          const sel = selectedNodeRef.current;
          if (!sel) return {};
          const src = graph.source(edge);
          const tgt = graph.target(edge);
          if (src !== sel && tgt !== sel) {
            return { color: dark ? "#292936" : "#d2d0ca", size: 0.15 };
          }
          return {};
        },
      });
      sigmaRef.current = sigma;

      // Chunked async ForceAtlas2
      const settings = forceAtlas2.inferSettings(graph);
      const totalIter = N > 500 ? 60 : N > 100 ? 80 : 120;
      let iter = 0;
      const runChunk = () => {
        if (disposed) return;
        const remaining = totalIter - iter;
        if (remaining <= 0) {
          setLayoutPct(100);
          return;
        }
        forceAtlas2.assign(graph, { iterations: Math.min(5, remaining), settings });
        iter += Math.min(5, remaining);
        setLayoutPct(20 + Math.floor((iter / totalIter) * 75));
        sigma.refresh();
        scheduleLayoutFrame(runChunk);
      };
      scheduleLayoutFrame(runChunk);

      // Click interactions
      sigma.on("clickNode", ({ node }) => {
        const currentData = dataRef.current;
        if (!currentData) return;
        const found = currentData.nodes.find((n) => n.id === node);
        if (!found) return;
        selectedNodeRef.current = node;
        highlightedRef.current = getConnectedNodes(graph, node);
        sigma.refresh();
        setSelectedNode(found);
      });

      sigma.on("clickStage", () => {
        selectedNodeRef.current = null;
        highlightedRef.current = new Set();
        sigma.refresh();
        setSelectedNode(null);
      });

      sigma.on("enterNode", () => { container.style.cursor = "pointer"; });
      sigma.on("leaveNode", () => { container.style.cursor = "default"; });

      return () => {
        disposed = true;
        cancelLayoutFrames();
        sigma.kill();
        sigmaRef.current = null;
      };
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to initialize graph renderer");
    }
  }, [graph, cancelLayoutFrames, scheduleLayoutFrame]);

  const handleRefresh = useCallback(() => {
    void fetchGraph();
  }, [fetchGraph]);

  const handleCloseInspector = useCallback(() => {
    selectedNodeRef.current = null;
    highlightedRef.current = new Set();
    sigmaRef.current?.refresh();
    setSelectedNode(null);
  }, []);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-ui-border bg-ui-surface px-4 py-2">
        <h2 className="text-lg font-semibold text-ui-text">Agent Memory</h2>
        <div className="ml-auto flex items-center gap-2">
          <select
            value={domainFilter}
            onChange={(e) => setDomainFilter(e.target.value)}
            className="rounded-md border border-ui-border bg-ui-surface px-2 py-1 text-sm text-ui-text"
          >
            <option value="">All Domains</option>
            <option value="engineering">Engineering</option>
            <option value="research">Research</option>
            <option value="trading">Trading</option>
            <option value="operations">Operations</option>
            <option value="custom">Custom</option>
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-md border border-ui-border bg-ui-surface px-2 py-1 text-sm text-ui-text"
          >
            <option value="">All Status</option>
            <option value="open">Open</option>
            <option value="active">Active</option>
            <option value="degraded">Degraded</option>
            <option value="superseded">Superseded</option>
            <option value="rejected">Rejected</option>
          </select>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={loading}
            className="rounded-md border border-stone-200 px-3 py-1 text-xs text-stone-600 disabled:opacity-40"
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="relative flex min-h-0 flex-1">
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-ui-canvas/80">
            <span className="text-sm text-ui-subdued">Loading Agent Memory graph...</span>
          </div>
        )}
        {error && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-ui-canvas/80">
            <span className="text-sm text-red-500">{error}</span>
            <button
              type="button"
              onClick={handleRefresh}
              className="rounded-md border border-ui-border px-3 py-1 text-xs text-ui-text hover:bg-ui-muted"
            >
              Retry
            </button>
          </div>
        )}
        {!loading && !error && data && data.nodes.length === 0 && (
          <div className="absolute inset-0 z-10 flex items-center justify-center">
            <div className="text-center">
              <p className="text-sm text-ui-subdued">No Agent Memory episodes found.</p>
              <p className="mt-1 text-xs text-ui-subdued">
                Create episodes using the OGM MCP tools or API.
              </p>
            </div>
          </div>
        )}

        <div ref={containerRef} className="absolute inset-0 h-full w-full bg-ui-canvas" />

        {selectedNode && (
          <div className="absolute right-0 top-0 z-20 h-full w-80 overflow-y-auto border-l border-ui-border bg-ui-surface p-4 shadow-lg">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-ui-text">Inspector</h3>
              <button
                type="button"
                onClick={handleCloseInspector}
                className="rounded p-1 text-ui-subdued hover:bg-ui-muted"
              >
                ✕
              </button>
            </div>

            <div className="mb-3">
              <span
                className="inline-block rounded-full px-2 py-0.5 text-xs font-medium text-white"
                style={{ backgroundColor: NODE_COLORS[selectedNode.type] }}
              >
                {selectedNode.type}
              </span>
              {selectedNode.status && (
                <span className="ml-2 text-xs text-ui-subdued">{selectedNode.status}</span>
              )}
              {selectedNode.domain && (
                <span className="ml-2 text-xs text-ui-subdued">({selectedNode.domain})</span>
              )}
            </div>

            <h4 className="mb-2 text-sm font-medium text-ui-text">{selectedNode.label}</h4>

            <dl className="space-y-2 text-xs">
              {Object.entries(selectedNode.metadata ?? {}).map(([key, value]) => (
                <div key={key}>
                  <dt className="font-medium text-ui-subdued">{key}</dt>
                  <dd className="mt-0.5 whitespace-pre-wrap text-ui-text">
                    {typeof value === "object" ? JSON.stringify(value, null, 2) : String(value ?? "")}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        {data && data.nodes.length > 0 && (
          <div className="absolute bottom-2 left-2 z-10 rounded-lg border border-ui-border bg-ui-surface/95 p-3 shadow-sm">
            <div className="mb-2 text-xs font-medium text-ui-subdued">Node Types</div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              {(Object.entries(NODE_COLORS) as [MemoryNodeType, string][]).map(([type, color]) => (
                <div key={type} className="flex items-center gap-1.5">
                  <div className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
                  <span className="text-xs text-ui-text capitalize">{type}</span>
                </div>
              ))}
            </div>
            {data.stats && (
              <div className="mt-2 border-t border-ui-border pt-2 text-xs text-ui-subdued">
                {data.stats.episodes} episodes, {data.stats.attempts} attempts, {data.stats.patterns} patterns
              </div>
            )}
          </div>
        )}

        {layoutPct > 0 && layoutPct < 100 && (
          <div className="pointer-events-none absolute inset-0 z-5 flex flex-col items-center justify-center">
            <div className="font-mono text-[11px] text-ui-subdued">Computing layout...</div>
            <div className="mt-2.5 h-0.5 w-40 overflow-hidden rounded bg-ui-border">
              <div className="h-full bg-amber-500 transition-[width] duration-150" style={{ width: `${layoutPct}%` }} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
