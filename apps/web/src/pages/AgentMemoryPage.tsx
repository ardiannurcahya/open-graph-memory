import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Sigma from "sigma";
import { agentMemoryApi } from "../api/endpoints";
import type { MemoryGraphView, MemoryGraphNode, MemoryEdgeType, MemoryNodeType } from "../api/types";
import { useTheme } from "../themeState";

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
      size: node.type === "episode" ? 14 : node.type === "pattern" ? 12 : node.type === "outcome" ? 10 : 7,
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

function ToolbarButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      data-active={active}
      onClick={onClick}
      className={`rounded-lg border px-3 py-1 text-xs font-medium transition-all shadow-sm ${
        active
          ? "border-mac-accent bg-mac-accent !text-white font-semibold"
          : "border-mac bg-surface/90 text-foreground hover:bg-surface-subtle"
      }`}
    >
      {children}
    </button>
  );
}

function Stat({ value }: { value: string }) {
  return <span className="px-2 py-1 font-mono text-[10px] text-foreground-muted">{value}</span>;
}

export default function AgentMemoryPage() {
  const { resolvedTheme } = useTheme();
  const [data, setData] = useState<MemoryGraphView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [domainFilter, setDomainFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [selectedNode, setSelectedNode] = useState<MemoryGraphNode | null>(null);
  const [layoutPct, setLayoutPct] = useState(0);
  const [showLegend, setShowLegend] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [physicsEnabled, setPhysicsEnabled] = useState(true);
  const [zoom, setZoom] = useState(1.0);

  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const selectedNodeRef = useRef<string | null>(null);
  const highlightedRef = useRef<Set<string>>(new Set());
  const layoutFramesRef = useRef<Set<number>>(new Set());
  const dataRef = useRef<MemoryGraphView | null>(null);

  dataRef.current = data;

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

  // Keyboard Shortcuts
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) return;
      if (event.key === "Escape") {
        selectedNodeRef.current = null;
        highlightedRef.current = new Set();
        sigmaRef.current?.refresh();
        setSelectedNode(null);
      } else if (event.key.toLowerCase() === "l") {
        setShowLegend((v) => !v);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

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
    const dark = resolvedTheme === "dark";

    // Custom High-Contrast Regular Label Renderer
    const drawLabel = (
      context: CanvasRenderingContext2D,
      dataNode: { label?: string; x: number; y: number; size: number; color: string; [key: string]: unknown },
      settings: { labelSize?: number; labelFont?: string; labelWeight?: string; [key: string]: unknown },
      isDark: boolean
    ) => {
      if (!dataNode.label) return;
      const size = settings.labelSize || 12;
      const font = settings.labelFont || "-apple-system, BlinkMacSystemFont, 'Inter', sans-serif";
      const weight = settings.labelWeight || "600";

      context.font = `${weight} ${size}px ${font}`;
      context.fillStyle = isDark ? "#ffffff" : "#0f172a";
      context.fillText(dataNode.label, dataNode.x + dataNode.size + 4, dataNode.y + size / 3);
    };

    // Custom High-Contrast macOS Hover & Selection Card Renderer
    const drawHover = (
      context: CanvasRenderingContext2D,
      dataNode: { label?: string; x: number; y: number; size: number; color: string; [key: string]: unknown },
      settings: { labelSize?: number; labelFont?: string; labelWeight?: string; [key: string]: unknown },
      isDark: boolean
    ) => {
      const size = settings.labelSize || 12;
      const font = settings.labelFont || "-apple-system, BlinkMacSystemFont, 'Inter', sans-serif";
      const weight = settings.labelWeight || "600";

      context.font = `${weight} ${size}px ${font}`;
      const label = dataNode.label;
      if (!label) return;

      const textWidth = context.measureText(label).width;
      const paddingX = 8;
      const paddingY = 4;
      const boxWidth = Math.round(textWidth + paddingX * 2);
      const boxHeight = Math.round(size + paddingY * 2);
      const radius = 6;

      const nodeRadius = dataNode.size || 5;
      const boxX = Math.round(dataNode.x + nodeRadius + 4);
      const boxY = Math.round(dataNode.y - boxHeight / 2);

      context.save();
      context.beginPath();
      context.fillStyle = isDark ? "#161b22" : "#ffffff";
      context.strokeStyle = isDark ? "#30363d" : "#cbd5e1";
      context.lineWidth = 1.5;
      context.shadowColor = isDark ? "rgba(0,0,0,0.6)" : "rgba(0,0,0,0.12)";
      context.shadowBlur = 6;
      context.shadowOffsetX = 0;
      context.shadowOffsetY = 2;

      if (typeof context.roundRect === "function") {
        context.roundRect(boxX, boxY, boxWidth, boxHeight, radius);
      } else {
        context.rect(boxX, boxY, boxWidth, boxHeight);
      }
      context.fill();
      context.shadowColor = "transparent";
      context.stroke();

      context.fillStyle = isDark ? "#ffffff" : "#0f172a";
      context.textBaseline = "middle";
      context.fillText(label, boxX + paddingX, boxY + boxHeight / 2);
      context.restore();
    };

    try {
      const N = graph.order;
      const sigma = new Sigma(graph, container, {
        allowInvalidContainer: true,
        renderLabels: showLabels,
        labelDensity: 1,
        labelRenderedSizeThreshold: 6,
        labelFont: "-apple-system, BlinkMacSystemFont, 'Inter', 'SF Pro Text', sans-serif",
        labelSize: 12,
        labelWeight: "600",
        defaultEdgeColor: dark ? "#38383a" : "#c8c6c0",
        labelColor: { color: dark ? "#ffffff" : "#0f172a" },
        defaultDrawNodeLabel: (context: CanvasRenderingContext2D, dataNode: any, settings: any) =>
          drawLabel(context, dataNode, settings, dark),
        defaultDrawNodeHover: (context: CanvasRenderingContext2D, dataNode: any, settings: any) =>
          drawHover(context, dataNode, settings, dark),
        minCameraRatio: 0.05,
        maxCameraRatio: 10,
        nodeReducer: (_node, nodeData) => {
          const sel = selectedNodeRef.current;
          const highlighted = highlightedRef.current;
          if (sel) {
            if (_node === sel || highlighted.has(_node)) {
              return {
                ...nodeData,
                highlighted: true,
                forceLabel: true,
                hidden: false,
                zIndex: _node === sel ? 2 : 1,
              };
            }
            return { ...nodeData, hidden: true, zIndex: 0 };
          }
          return nodeData;
        },
        edgeReducer: (edge) => {
          const sel = selectedNodeRef.current;
          if (!sel) return {};
          const src = graph.source(edge);
          const tgt = graph.target(edge);
          if (src === sel || tgt === sel) {
            return { hidden: false, size: 2 };
          }
          return { hidden: true };
        },
      });
      sigmaRef.current = sigma;

      // Chunked async ForceAtlas2
      if (physicsEnabled) {
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
      } else {
        setLayoutPct(100);
      }

      // Camera tracker
      const cam = sigma.getCamera();
      cam.on("updated", (camState) => {
        setZoom(1 / camState.ratio);
      });
      setZoom(1 / cam.getState().ratio);

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
  }, [graph, cancelLayoutFrames, scheduleLayoutFrame, resolvedTheme, physicsEnabled, showLabels]);

  const handleRefresh = useCallback(() => {
    void fetchGraph();
  }, [fetchGraph]);

  const handleCloseInspector = useCallback(() => {
    selectedNodeRef.current = null;
    highlightedRef.current = new Set();
    sigmaRef.current?.refresh();
    setSelectedNode(null);
  }, []);

  const handleFit = () => {
    sigmaRef.current?.getCamera().animatedReset({ duration: 300 });
  };

  return (
    <div className="relative h-screen min-h-[640px] overflow-hidden bg-ui-canvas">
      {/* Floating macOS Top Toolbar */}
      <div className="absolute left-3 right-3 top-3 z-10 flex flex-wrap items-center gap-2 rounded-2xl border border-mac bg-surface/90 px-3 py-2 shadow-xl backdrop-blur-md text-foreground">
        <div className="flex items-center gap-2 font-semibold text-sm mr-2 text-foreground">
          <span className="h-2.5 w-2.5 rounded-full bg-blue-500 shadow-sm animate-pulse" />
          Agent Memory Playground
        </div>

        {/* Domain Filter */}
        <select
          value={domainFilter}
          onChange={(e) => setDomainFilter(e.target.value)}
          className="min-w-36 rounded-lg border border-mac bg-surface px-2.5 py-1 text-xs font-medium text-foreground hover:bg-surface-subtle shadow-sm transition-colors"
        >
          <option value="">All Domains</option>
          <option value="engineering">Engineering</option>
          <option value="research">Research</option>
          <option value="trading">Trading</option>
          <option value="operations">Operations</option>
          <option value="custom">Custom</option>
        </select>

        {/* Status Filter */}
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="min-w-32 rounded-lg border border-mac bg-surface px-2.5 py-1 text-xs font-medium text-foreground hover:bg-surface-subtle shadow-sm transition-colors"
        >
          <option value="">All Status</option>
          <option value="open">Open</option>
          <option value="active">Active</option>
          <option value="degraded">Degraded</option>
          <option value="superseded">Superseded</option>
          <option value="rejected">Rejected</option>
        </select>

        <ToolbarButton active={showLegend} onClick={() => setShowLegend((v) => !v)}>
          Legend
        </ToolbarButton>

        <button
          type="button"
          onClick={handleRefresh}
          disabled={loading}
          className="rounded-lg border border-mac bg-surface/90 px-2.5 py-1 text-xs font-medium text-foreground hover:bg-surface-subtle disabled:opacity-40 shadow-sm ml-auto"
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {/* Main Canvas Area */}
      <div className="relative h-full w-full">
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-ui-canvas/80 backdrop-blur-sm">
            <span className="text-sm text-foreground-muted font-medium">Loading Agent Memory graph...</span>
          </div>
        )}
        {error && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-ui-canvas/80 backdrop-blur-sm">
            <span className="text-sm text-red-500 font-medium">{error}</span>
            <button
              type="button"
              onClick={handleRefresh}
              className="rounded-xl bg-mac-accent px-3 py-1 text-xs font-semibold !text-white shadow-sm"
            >
              Retry
            </button>
          </div>
        )}
        {!loading && !error && data && data.nodes.length === 0 && (
          <div className="absolute inset-0 z-10 flex items-center justify-center">
            <div className="text-center p-6 rounded-2xl border border-mac bg-surface shadow-xl">
              <p className="text-sm font-semibold text-foreground">No Agent Memory episodes found.</p>
              <p className="mt-1 text-xs text-foreground-muted">
                Create episodes using OGM MCP tools (<code className="font-mono text-mac-accent">ogm_memory_create_episode</code>).
              </p>
            </div>
          </div>
        )}

        <div ref={containerRef} id="agent-memory-canvas" className="absolute inset-0 h-full w-full bg-ui-canvas" />

        {/* Floating macOS Camera Toolbar */}
        {data && data.nodes.length > 0 && (
          <div className="absolute bottom-3 left-3 z-10 flex flex-wrap items-center gap-1 rounded-2xl border border-mac bg-surface/90 p-1.5 shadow-xl backdrop-blur-md text-foreground">
            <Stat value={`${data.nodes.length} nodes`} />
            <Stat value={`${data.edges.length} edges`} />
            <Stat value={`${zoom.toFixed(1)}x`} />
            <button
              type="button"
              onClick={handleFit}
              className="rounded-lg px-2 py-1 text-xs font-medium text-foreground hover:bg-surface-subtle transition-colors"
            >
              Fit
            </button>
            <button
              type="button"
              onClick={() => setPhysicsEnabled((v) => !v)}
              className={`rounded-lg px-2 py-1 text-xs font-medium transition-all ${
                physicsEnabled
                  ? "bg-mac-accent !text-white font-semibold shadow-sm"
                  : "text-foreground-muted hover:bg-surface-subtle"
              }`}
            >
              Physics {physicsEnabled ? "on" : "off"}
            </button>
            <button
              type="button"
              onClick={() => setShowLabels((v) => !v)}
              className="rounded-lg px-2 py-1 text-xs font-medium text-foreground-muted hover:bg-surface-subtle transition-colors"
            >
              Labels {showLabels ? "on" : "off"}
            </button>
          </div>
        )}

        {/* Floating macOS Inspector Drawer */}
        {selectedNode && (
          <div className="absolute right-3 top-16 z-20 flex max-h-[calc(100vh-5rem)] w-[min(26rem,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-2xl border border-mac bg-surface/95 shadow-2xl backdrop-blur-md text-foreground animate-in fade-in duration-200">
            <div className="flex items-center justify-between border-b border-mac p-4">
              <div className="flex items-center gap-2">
                <span
                  className="rounded-full px-2.5 py-0.5 text-xs font-semibold text-white shadow-sm"
                  style={{ backgroundColor: NODE_COLORS[selectedNode.type] }}
                >
                  {selectedNode.type}
                </span>
                {selectedNode.domain && (
                  <span className="text-xs font-medium text-foreground-muted">
                    {selectedNode.domain}
                  </span>
                )}
                {selectedNode.status && (
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-foreground-muted border border-mac">
                    {selectedNode.status}
                  </span>
                )}
              </div>
              <button
                type="button"
                onClick={handleCloseInspector}
                className="rounded-lg p-1.5 text-foreground-muted hover:bg-surface-subtle hover:text-foreground transition-colors"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 overflow-y-auto p-4">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-foreground-muted">Memory Node</div>
                <h4 className="mt-0.5 text-sm font-semibold text-foreground leading-snug">{selectedNode.label}</h4>
                <div className="mt-1 font-mono text-[10px] text-foreground-muted">{selectedNode.id}</div>
              </div>

              {Object.entries(selectedNode.metadata ?? {}).length > 0 && (
                <div className="space-y-2 border-t border-mac pt-3">
                  <div className="text-[10px] font-mono uppercase tracking-wider text-foreground-muted">Metadata & Attributes</div>
                  <dl className="space-y-2 text-xs">
                    {Object.entries(selectedNode.metadata ?? {}).map(([key, value]) => (
                      <div key={key} className="rounded-xl border border-mac bg-surface-subtle p-2.5">
                        <dt className="font-semibold text-foreground">{key}</dt>
                        <dd className="mt-1 whitespace-pre-wrap font-mono text-[11px] text-foreground-muted">
                          {typeof value === "object" ? JSON.stringify(value, null, 2) : String(value ?? "")}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Floating macOS Legend Panel */}
        {showLegend && data && data.nodes.length > 0 && (
          <div className="absolute bottom-3 right-3 z-10 min-w-48 rounded-2xl border border-mac bg-surface/95 p-3.5 shadow-xl backdrop-blur-md text-foreground">
            <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-foreground-muted">
              Memory Types ({data.nodes.length})
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              {(Object.entries(NODE_COLORS) as [MemoryNodeType, string][]).map(([type, color]) => (
                <div key={type} className="flex items-center gap-2 text-xs font-medium text-foreground">
                  <span className="h-2.5 w-2.5 rounded-full shrink-0 shadow-sm" style={{ backgroundColor: color }} />
                  <span className="capitalize">{type}</span>
                </div>
              ))}
            </div>
            {data.stats && (
              <div className="mt-2.5 border-t border-mac pt-2 font-mono text-[10px] text-foreground-muted">
                {data.stats.episodes} eps · {data.stats.attempts} att · {data.stats.patterns} pat
              </div>
            )}
          </div>
        )}

        {/* ForceAtlas2 Progress Bar */}
        {layoutPct > 0 && layoutPct < 100 && (
          <div className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center bg-ui-canvas/50 backdrop-blur-xs">
            <div className="font-mono text-[11px] text-foreground-muted font-medium">Computing memory layout…</div>
            <div className="mt-2.5 h-1 w-44 overflow-hidden rounded-full bg-muted border border-mac">
              <div className="h-full bg-mac-accent transition-[width] duration-150" style={{ width: `${layoutPct}%` }} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
