import { useEffect, useRef, useState } from "react";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Sigma from "sigma";
import type { GraphNode, GraphState } from "../lib/graphTypes";
import { highlightConnected } from "../lib/graphPhysics";
import { vividNodeColorForCommunity } from "../lib/colorPalette";
import { useTheme } from "../themeState";

export interface SigmaGraphCanvasProps {
  state: GraphState;
  physicsEnabled: boolean;
  showLabels: boolean;
  activeFilters: Set<string>;
  selectedNodeId: string | null;
  onNodeSelect: (node: GraphNode | null) => void;
  onCameraChange?: (zoom: number) => void;
  onLayoutProgress?: (pct: number) => void;
}

const CACHE_PREFIX = "ogm-sigma-fa2-v2";

interface SeedResult {
  positions: Record<string, { x: number; y: number }>;
  centers: Record<string, { x: number; y: number }>;
}

interface CanvasNodeData {
  label?: string | null;
  x: number;
  y: number;
  size: number;
  color: string;
}

interface CanvasSettings {
  labelSize?: number;
  labelFont?: string;
  labelWeight?: string;
}

function seedLayout(state: GraphState): SeedResult {
  const communityIds = [...state.communities.keys()];
  if (communityIds.length === 0) communityIds.push("default");

  const nodesById = new Map(state.nodes.map((n) => [n.id, n]));
  const nodesByCommunity = new Map<string, string[]>();
  for (const node of state.nodes) {
    const group = nodesByCommunity.get(node.community) ?? [];
    group.push(node.id);
    nodesByCommunity.set(node.community, group);
  }

  const communitySizes = new Map<string, number>();
  const branchRadii = new Map<string, number>();
  for (const [id, members] of nodesByCommunity) {
    communitySizes.set(id, members.length);
    const sizeScale = members.length > 1500 ? 0.3 : 0.2;
    branchRadii.set(id, 2 + Math.sqrt(Math.max(1, members.length)) * sizeScale);
  }

  const sorted = [...communityIds].sort(
    (a, b) => (communitySizes.get(b) ?? 0) - (communitySizes.get(a) ?? 0),
  );
  const largestBranchRadius = branchRadii.get(sorted[0]) ?? 0;
  const effectiveRadius = Math.max(4, largestBranchRadius * 0.45);

  const centers: Record<string, { x: number; y: number }> = {};
  if (sorted.length > 0) centers[sorted[0]] = { x: 0, y: 0 };
  const rest = sorted.slice(1);
  rest.forEach((id, i) => {
    const angle = (i / Math.max(1, rest.length)) * Math.PI * 2;
    centers[id] = { x: Math.cos(angle) * effectiveRadius, y: Math.sin(angle) * effectiveRadius };
  });

  const positions: Record<string, { x: number; y: number }> = {};
  for (const communityId of communityIds) {
    const memberIds = nodesByCommunity.get(communityId) ?? [];
    const center = centers[communityId] ?? { x: 0, y: 0 };
    const branchRadius = branchRadii.get(communityId) ?? 3;
    const ordered = [...memberIds].sort(
      (a, b) => (nodesById.get(b)?.degree ?? 0) - (nodesById.get(a)?.degree ?? 0),
    );
    const count = ordered.length;
    ordered.forEach((id, i) => {
      const angle = (i / Math.max(1, count)) * Math.PI * 2 * 3;
      const r = branchRadius * Math.sqrt((i + 0.5) / count);
      positions[id] = {
        x: center.x + r * Math.cos(angle),
        y: center.y + r * Math.sin(angle),
      };
    });
  }

  return { positions, centers };
}

function fingerprint(state: GraphState): string {
  const nodes = state.nodes.map((n) => `${n.id}:${n.community}:${n.degree}`).sort().join("|");
  const edges = state.edges
    .map((e) => { const [s, t] = [e.source, e.target].sort(); return `${e.id}:${s}:${t}`; })
    .sort().join("|");
  let h = 2166136261;
  const str = `${nodes}|${edges}`;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  return String(h >>> 0);
}

function isSeedResult(value: unknown): value is SeedResult {
  if (!value || typeof value !== "object") return false;
  const positions = (value as { positions?: unknown }).positions;
  if (!positions || typeof positions !== "object" || Array.isArray(positions)) return false;
  return Object.values(positions).every((position) => (
    position
    && typeof position === "object"
    && Number.isFinite((position as { x?: unknown }).x)
    && Number.isFinite((position as { y?: unknown }).y)
  ));
}

function loadCached(key: string): SeedResult | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const cached: unknown = JSON.parse(raw);
    if (isSeedResult(cached)) return cached;
  } catch {
    // Treat corrupted browser storage as a cache miss.
  }
  try { localStorage.removeItem(key); } catch { /* storage disabled */ }
  return null;
}

function saveCached(key: string, data: SeedResult): void {
  try { localStorage.setItem(key, JSON.stringify(data)); } catch { /* quota */ }
}

export default function SigmaGraphCanvas({
  state,
  physicsEnabled,
  showLabels,
  activeFilters,
  selectedNodeId,
  onNodeSelect,
  onCameraChange,
  onLayoutProgress,
}: SigmaGraphCanvasProps) {
  const { resolvedTheme } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const [layoutPct, setLayoutPct] = useState(0);
  const [setupError, setSetupError] = useState<Error | null>(null);

  if (setupError) throw setupError;

  const themeRef = useRef(resolvedTheme);
  const filtersRef = useRef(activeFilters);
  const labelsRef = useRef(showLabels);
  const physicsRef = useRef(physicsEnabled);
  const selectRef = useRef(onNodeSelect);
  const cameraRef = useRef(onCameraChange);
  const progressRef = useRef(onLayoutProgress);

  themeRef.current = resolvedTheme;
  filtersRef.current = activeFilters;
  labelsRef.current = showLabels;
  physicsRef.current = physicsEnabled;
  selectRef.current = onNodeSelect;
  cameraRef.current = onCameraChange;
  progressRef.current = onLayoutProgress;

  const sigmaRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const selectedNodeRef = useRef<string | null>(null);
  const highlightedRef = useRef<Set<string>>(new Set());
  const layoutFramesRef = useRef<Set<number>>(new Set());

  selectedNodeRef.current = selectedNodeId;

  const cancelLayoutFrames = () => {
    for (const frame of layoutFramesRef.current) cancelAnimationFrame(frame);
    layoutFramesRef.current.clear();
  };

  const scheduleLayoutFrame = (callback: () => void) => {
    let frame = 0;
    frame = requestAnimationFrame(() => {
      layoutFramesRef.current.delete(frame);
      try {
        callback();
      } catch (error) {
        setSetupError(error instanceof Error ? error : new Error(String(error)));
      }
    });
    layoutFramesRef.current.add(frame);
  };

  // Build graph + sigma on state change
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    setSetupError(null);

    try {
      const graph = new Graph({ multi: true });
    const N = state.nodes.length;
    const dark = themeRef.current === "dark";
    const cacheKey = `${CACHE_PREFIX}:${fingerprint(state)}`;

    // Seed positions
    let seeded = loadCached(cacheKey);
    if (!seeded) {
      seeded = seedLayout(state);
    }

    // Add nodes
    for (const node of state.nodes) {
      const pos = seeded.positions[node.id] ?? { x: 0, y: 0 };
      const neighbors = state.adj.get(node.id) ?? [];
      graph.addNode(node.id, {
        x: pos.x,
        y: pos.y,
        size: 3 + Math.min(neighbors.length * 0.5, 8),
        color: vividNodeColorForCommunity(node.community, dark),
        label: node.label,
        community: node.community,
        isExpired: node.isExpired === true,
      });
    }

    // Add edges
    for (const edge of state.edges) {
      if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) continue;
      const srcComm = state.nodes.find((n) => n.id === edge.source)?.community ?? "";
      const info = state.communities.get(srcComm);
      graph.addEdgeWithKey(edge.id, edge.source, edge.target, {
        color: info?.color ?? "#78716c",
        size: 0.5,
        isExpired: edge.isExpired === true,
      });
    }

    graphRef.current = graph;

    setLayoutPct(20);
    progressRef.current?.(20);

    // Custom High-Contrast Regular Label Renderer
    const drawLabel = (
      context: CanvasRenderingContext2D,
      data: CanvasNodeData,
      settings: CanvasSettings,
      isDark: boolean
    ) => {
      if (!data.label) return;
      const size = settings.labelSize || 12;
      const font = settings.labelFont || "-apple-system, BlinkMacSystemFont, 'Inter', sans-serif";
      const weight = settings.labelWeight || "600";

      context.font = `${weight} ${size}px ${font}`;
      context.fillStyle = isDark ? "#ffffff" : "#0f172a";
      context.fillText(data.label, data.x + data.size + 4, data.y + size / 3);
    };

    // Custom High-Contrast Hover & Selection Card Renderer
    const drawHover = (
      context: CanvasRenderingContext2D,
      data: CanvasNodeData,
      settings: CanvasSettings,
      isDark: boolean
    ) => {
      const size = settings.labelSize || 12;
      const font = settings.labelFont || "-apple-system, BlinkMacSystemFont, 'Inter', sans-serif";
      const weight = settings.labelWeight || "600";

      context.font = `${weight} ${size}px ${font}`;
      const label = data.label;
      if (!label) return;

      const textWidth = context.measureText(label).width;
      const paddingX = 8;
      const paddingY = 4;
      const boxWidth = Math.round(textWidth + paddingX * 2);
      const boxHeight = Math.round(size + paddingY * 2);
      const radius = 6;

      const nodeRadius = data.size || 5;
      const boxX = Math.round(data.x + nodeRadius + 4);
      const boxY = Math.round(data.y - boxHeight / 2);

      // 1. Draw High-Contrast Background Box
      context.save();
      context.beginPath();

      // Dark Mode: Flat GitHub Dark Card (#161b22) with border (#30363d)
      // Light Mode: Pure White Card (#ffffff) with border (#cbd5e1)
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

      // 2. Draw High-Contrast Text (Never matches background!)
      // Dark Mode: Pure White (#ffffff) on Dark Card (#161b22)
      // Light Mode: Deep Slate Black (#0f172a) on White Card (#ffffff)
      context.fillStyle = isDark ? "#ffffff" : "#0f172a";
      context.textBaseline = "middle";
      context.fillText(label, boxX + paddingX, boxY + boxHeight / 2);
      context.restore();
    };

    // Create sigma
    const sigma = new Sigma(graph, container, {
      allowInvalidContainer: true,
      renderLabels: labelsRef.current,
      labelDensity: 1,
      labelRenderedSizeThreshold: 8,
      labelFont: "-apple-system, BlinkMacSystemFont, 'Inter', 'SF Pro Text', sans-serif",
      labelSize: 12,
      labelWeight: "600",
      defaultEdgeColor: dark ? "#38383a" : "#c8c6c0",
      labelColor: { color: dark ? "#ffffff" : "#0f172a" },
      defaultDrawNodeLabel: (context, data, settings) =>
        drawLabel(context, data, settings, themeRef.current === "dark"),
      defaultDrawNodeHover: (context, data, settings) =>
        drawHover(context, data, settings, themeRef.current === "dark"),
      minCameraRatio: 0.05,
      maxCameraRatio: 10,
      nodeReducer: (node, data) => {
        const isDark = themeRef.current === "dark";
        const filters = filtersRef.current;
        const sel = selectedNodeRef.current;
        const highlighted = highlightedRef.current;
        const isExpired = graph.getNodeAttribute(node, "isExpired") as boolean | undefined;

        // When a node is selected: ONLY the selected node and its connected neighbors are displayed!
        if (sel) {
          if (node === sel || highlighted.has(node)) {
            return {
              ...data,
              highlighted: true,
              forceLabel: true,
              hidden: false,
              zIndex: node === sel ? 2 : 1,
            };
          }
          return { ...data, hidden: true, zIndex: 0 };
        }

        // When no node is selected, apply community filters:
        if (filters.size > 0 && !filters.has(data.community as string)) {
          return { ...data, hidden: true, zIndex: 0 };
        }
        if (isExpired) {
          return { ...data, color: isDark ? "#2a2a3a" : "#b8b6b0", zIndex: 0 };
        }
        return data;
      },

      edgeReducer: (edge) => {
        const filters = filtersRef.current;
        const sel = selectedNodeRef.current;
        const src = graph.source(edge);
        const tgt = graph.target(edge);
        const srcComm = graph.getNodeAttribute(src, "community") as string;
        const tgtComm = graph.getNodeAttribute(tgt, "community") as string;
        const edgeData = graph.getEdgeAttributes(edge);
        const isExpired = edgeData.isExpired as boolean | undefined;

        // When a node is selected: ONLY the connected edges are displayed!
        if (sel) {
          if (src === sel || tgt === sel) {
            return {
              hidden: false,
              size: 1.5,
              color: isExpired ? (dark ? "#4a4a5a" : "#94a3b8") : undefined,
            };
          }
          return { hidden: true };
        }

        // When no node is selected, apply community filters:
        if (filters.size > 0 && !filters.has(srcComm) && !filters.has(tgtComm)) {
          return { hidden: true };
        }
        if (isExpired) {
          return { color: dark ? "#1a1a2a" : "#d0cec8", hidden: false };
        }
        return {};
      },
    });

    sigmaRef.current = sigma;
    let disposed = false;

    // Run forceatlas2 if physics enabled or cache miss.
    const shouldRunPhysics = physicsRef.current || !loadCached(cacheKey);
    if (shouldRunPhysics) {
      const baseSettings = forceAtlas2.inferSettings(graph);
      const settings = {
        ...baseSettings,
        gravity: 2.5,
        scalingRatio: 0.3,
        strongGravityMode: true,
        outboundAttractionDistribution: false,
      };
      const totalIter = N > 1500 ? 60 : N > 500 ? 80 : 120;
      let iter = 0;
      const runChunk = () => {
        if (disposed) return;
        const remaining = totalIter - iter;
        if (remaining <= 0) {
          const positions: Record<string, { x: number; y: number }> = {};
          const centers: Record<string, { x: number; y: number }> = {};
          graph.forEachNode((id, attrs) => {
            positions[id] = { x: attrs.x, y: attrs.y };
          });
          const communityCenters = new Map<string, { sx: number; sy: number; count: number }>();
          graph.forEachNode((_id, attrs) => {
            const comm = attrs.community as string;
            const existing = communityCenters.get(comm) ?? { sx: 0, sy: 0, count: 0 };
            existing.sx += attrs.x; existing.sy += attrs.y; existing.count++;
            communityCenters.set(comm, existing);
          });
          for (const [comm, { sx, sy, count }] of communityCenters) centers[comm] = { x: sx / count, y: sy / count };
          saveCached(cacheKey, { positions, centers });
          setLayoutPct(100);
          progressRef.current?.(100);
          return;
        }
        forceAtlas2.assign(graph, { iterations: Math.min(5, remaining), settings });
        iter += Math.min(5, remaining);
        const pct = 20 + Math.floor((iter / totalIter) * 75);
        setLayoutPct(pct);
        progressRef.current?.(pct);
        sigma.refresh();
        scheduleLayoutFrame(runChunk);
      };
      scheduleLayoutFrame(runChunk);
    } else {
      setLayoutPct(100);
      progressRef.current?.(100);
    }

    sigma.on("clickNode", ({ node }) => {
      const graphNode = state.nodes.find((n) => n.id === node);
      if (!graphNode) return;
      selectedNodeRef.current = node;
      const hl = highlightConnected(state, node);
      highlightedRef.current = new Set(hl.nodes);
      sigma.refresh();
      selectRef.current(graphNode);
    });

    sigma.on("clickStage", () => {
      selectedNodeRef.current = null;
      highlightedRef.current = new Set();
      sigma.refresh();
      selectRef.current(null);
    });

    sigma.on("enterNode", () => { container.style.cursor = "pointer"; });
    sigma.on("leaveNode", () => { container.style.cursor = "default"; });

    const cam = sigma.getCamera();
    cam.on("updated", (camState) => {
      cameraRef.current?.(1 / camState.ratio);
    });

    cameraRef.current?.(1 / cam.getState().ratio);

    const fitHandler = () => {
      cam.animatedReset({ duration: 300 });
    };
    const resetHandler = () => {
      cancelLayoutFrames();
      localStorage.removeItem(cacheKey);
      selectedNodeRef.current = null;
      highlightedRef.current = new Set();
      selectRef.current(null);
      setLayoutPct(0);
      progressRef.current?.(0);
      // Re-seed and run physics
      const fresh = seedLayout(state);
      graph.forEachNode((id) => {
        const pos = fresh.positions[id];
        if (pos) graph.setNodeAttribute(id, "x", pos.x);
        if (pos) graph.setNodeAttribute(id, "y", pos.y);
      });
      const settings = forceAtlas2.inferSettings(graph);
      const totalIter = N > 1500 ? 60 : N > 500 ? 80 : 120;
      let iter = 0;
      const runChunk = () => {
        if (disposed) return;
        const remaining = totalIter - iter;
        if (remaining <= 0) {
          setLayoutPct(100);
          progressRef.current?.(100);
          sigma.refresh();
          return;
        }
        forceAtlas2.assign(graph, { iterations: Math.min(5, remaining), settings });
        iter += 5;
        setLayoutPct(20 + Math.floor((iter / totalIter) * 75));
        sigma.refresh();
        scheduleLayoutFrame(runChunk);
      };
      scheduleLayoutFrame(runChunk);
    };

    container.addEventListener("graph:fit", fitHandler);
    container.addEventListener("graph:reset", resetHandler);

    return () => {
      disposed = true;
      cancelLayoutFrames();
      container.removeEventListener("graph:fit", fitHandler);
      container.removeEventListener("graph:reset", resetHandler);
      sigma.kill();
      sigmaRef.current = null;
      graphRef.current = null;
    };
    } catch (error) {
      setSetupError(error instanceof Error ? error : new Error(String(error)));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  // Physics toggle
  const prevPhysicsRef = useRef(physicsEnabled);
  useEffect(() => {
    if (prevPhysicsRef.current === physicsEnabled) return;
    prevPhysicsRef.current = physicsEnabled;
    cancelLayoutFrames();
    const graph = graphRef.current;
    const sigma = sigmaRef.current;
    if (!graph || !sigma) return;

    if (physicsEnabled) {
      // Run physics from current positions
      const settings = forceAtlas2.inferSettings(graph);
      const N = graph.order;
      const totalIter = N > 1500 ? 60 : N > 500 ? 80 : 120;
      let iter = 0;
      let disposed = false;
      const runChunk = () => {
        if (disposed) return;
        const remaining = totalIter - iter;
        if (remaining <= 0 || !physicsRef.current) {
          setLayoutPct(100);
          progressRef.current?.(100);
          return;
        }
        forceAtlas2.assign(graph, { iterations: Math.min(5, remaining), settings });
        iter += 5;
        setLayoutPct(20 + Math.floor((iter / totalIter) * 75));
        progressRef.current?.(20 + Math.floor((iter / totalIter) * 75));
        sigma.refresh();
        scheduleLayoutFrame(runChunk);
      };
      scheduleLayoutFrame(runChunk);
      return () => {
        disposed = true;
        cancelLayoutFrames();
      };
    } else {
      // Restore seed positions
      const fresh = seedLayout(state);
      graph.forEachNode((id) => {
        const pos = fresh.positions[id];
        if (pos) {
          graph.setNodeAttribute(id, "x", pos.x);
          graph.setNodeAttribute(id, "y", pos.y);
        }
      });
      sigma.refresh();
      setLayoutPct(100);
      progressRef.current?.(100);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [physicsEnabled]);

  // Filter changes
  useEffect(() => {
    filtersRef.current = activeFilters;
    sigmaRef.current?.refresh();
  }, [activeFilters]);

  useEffect(() => {
    selectedNodeRef.current = selectedNodeId;
    highlightedRef.current = selectedNodeId
      ? new Set(highlightConnected(state, selectedNodeId).nodes)
      : new Set();
    sigmaRef.current?.refresh();
  }, [selectedNodeId, state]);

  // Label toggle
  useEffect(() => {
    labelsRef.current = showLabels;
    if (sigmaRef.current) {
      sigmaRef.current.setSetting("renderLabels", showLabels);
    }
  }, [showLabels]);

  // Theme changes
  useEffect(() => {
    if (themeRef.current === resolvedTheme) return;
    themeRef.current = resolvedTheme;
    const graph = graphRef.current;
    const sigma = sigmaRef.current;
    if (!graph || !sigma) return;
    const dark = resolvedTheme === "dark";
    graph.forEachNode((id, attrs) => {
      graph.setNodeAttribute(id, "color", vividNodeColorForCommunity(attrs.community as string, dark));
    });
    graph.forEachEdge((_id, _attrs, source, _target) => {
      const srcComm = graph.getNodeAttribute(source, "community") as string;
      const info = state.communities.get(srcComm);
      graph.setEdgeAttribute(_id, "color", info?.color ?? "#78716c");
    });
    sigma.setSetting("defaultEdgeColor", dark ? "#38383a" : "#c8c6c0");
    sigma.setSetting("labelColor", { color: dark ? "#ffffff" : "#0f172a" });
    sigma.refresh();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedTheme]);

  return (
    <div ref={containerRef} id="graph-canvas" data-renderer="sigma" className="absolute inset-0 h-full w-full bg-ui-canvas">
      {layoutPct > 0 && layoutPct < 100 && (
        <div className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center bg-ui-canvas">
          <div className="font-mono text-[11px] text-ui-subdued">Computing layout…</div>
          <div className="mt-2.5 h-0.5 w-40 overflow-hidden rounded bg-ui-border">
            <div className="h-full bg-amber-500 transition-[width] duration-150" style={{ width: `${layoutPct}%` }} />
          </div>
        </div>
      )}
    </div>
  );
}
