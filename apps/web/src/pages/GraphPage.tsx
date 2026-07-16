import { useCallback, useEffect, useMemo, useState } from "react";
import { datasetsApi, graphApi } from "../api/endpoints";
import { ApiError } from "../api/client";
import type { Dataset, ExplorerView } from "../api/types";
import type { GraphState, GraphNode } from "../lib/graphTypes";
import { explorerToGraphState } from "../lib/graphMapping";

import { GraphCanvas } from "../components/GraphCanvas";
import { Inspector } from "../components/Inspector";
import { CommandPalette } from "../components/CommandPalette";

export default function GraphPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [view, setView] = useState<ExplorerView | null>(null);
  const [level, setLevel] = useState(0);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [physicsEnabled, setPhysicsEnabled] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [showLegend, setShowLegend] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set());
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    void datasetsApi.list().then(setDatasets).catch(() => undefined);
  }, []);

  const graphState: GraphState | null = useMemo(() => {
    if (!view) return null;
    return explorerToGraphState(view);
  }, [view]);

  const loadExplorer = useCallback(async (id: string, communityLevel: number) => {
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    try {
      setView(await graphApi.getExplorer(id, { community_level: communityLevel }));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "failed to load graph");
      setView(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (datasetId) void loadExplorer(datasetId, level);
    else setView(null);
  }, [datasetId, level, loadExplorer]);

  const handleRefresh = async () => {
    if (!datasetId) return;
    setRefreshing(true);
    setError(null);
    try {
      await graphApi.refreshAnalytics(datasetId);
      await loadExplorer(datasetId, level);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "analytics refresh failed");
    } finally {
      setRefreshing(false);
    }
  };

  const handleNodeSelect = useCallback((node: GraphNode | null) => {
    setSelectedNode(node);
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (cmdOpen) return;
      if (e.ctrlKey || e.metaKey) {
        if (e.key === "k") {
          e.preventDefault();
          setCmdOpen(true);
        }
      } else {
        if (e.key === "Escape") setSelectedNode(null);
        if (e.key === "l" || e.key === "L") setShowLegend((v) => !v);
        if (e.key === "f" || e.key === "F") setShowFilters((v) => !v);
        if (e.key === " ") {
          e.preventDefault();
          setPhysicsEnabled((v) => !v);
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [cmdOpen]);

  const toggleFilter = (communityId: string) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(communityId)) next.delete(communityId);
      else next.add(communityId);
      return next;
    });
  };

  const triggerCanvasEvent = (type: string) => {
    const canvas = document.getElementById("graph-canvas");
    canvas?.dispatchEvent(new Event(type));
  };

  if (!graphState) {
    return (
      <div className="px-8 py-6">
        <h2 className="text-xl font-semibold text-stone-900">Knowledge</h2>
        <div className="mt-4 flex flex-wrap items-center gap-4">
          <select
            value={datasetId}
            onChange={(e) => setDatasetId(e.target.value)}
            className="rounded-md border border-stone-300 px-3 py-1.5 text-sm"
          >
            <option value="">Select dataset…</option>
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </div>
        {error && (
          <div className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
        )}
        <div className="mt-4 flex flex-1 items-center justify-center rounded-lg border border-dashed border-stone-300 p-12 text-sm text-stone-400">
          {loading ? "Loading…" : "Select a dataset to explore its knowledge graph."}
        </div>
      </div>
    );
  }

  const stats = view?.stats;

  return (
    <div className="relative h-screen bg-stone-50">
      <GraphCanvas
        state={graphState}
        physicsEnabled={physicsEnabled}
        showLabels={showLabels}
        activeFilters={activeFilters}
        onNodeSelect={handleNodeSelect}
        onCameraChange={setZoom}
      />

      {/* Top toolbar */}
      <div className="absolute left-3 right-3 top-3 z-10 flex items-center gap-2 rounded-lg border border-stone-200 bg-white/95 px-3 py-2 shadow-sm backdrop-blur">
        <span className="text-sm font-semibold text-stone-900">Knowledge</span>
        <select
          value={datasetId}
          onChange={(e) => setDatasetId(e.target.value)}
          className="rounded-md border border-stone-300 px-2 py-1 text-sm"
        >
          <option value="">Dataset…</option>
          {datasets.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        {view && view.available_levels.length > 0 && (
          <select
            value={level}
            onChange={(e) => setLevel(Number(e.target.value))}
            className="rounded-md border border-stone-300 px-2 py-1 text-sm"
          >
            {view.available_levels.map((l) => (
              <option key={l} value={l}>
                L{l}
              </option>
            ))}
          </select>
        )}
        <button
          onClick={() => setCmdOpen(true)}
          className="ml-auto flex items-center gap-2 rounded-md border border-stone-200 px-3 py-1 text-xs text-stone-500 hover:bg-stone-50"
        >
          Search…
          <kbd className="rounded border border-stone-200 bg-stone-100 px-1 text-[10px]">Ctrl+K</kbd>
        </button>
        <button
          onClick={() => setShowFilters((v) => !v)}
          className={`rounded-md border px-2 py-1 text-xs ${
            showFilters
              ? "border-stone-900 bg-stone-900 text-white"
              : "border-stone-200 text-stone-600 hover:bg-stone-50"
          }`}
        >
          Filters
        </button>
        <button
          onClick={() => setShowLegend((v) => !v)}
          className={`rounded-md border px-2 py-1 text-xs ${
            showLegend
              ? "border-stone-900 bg-stone-900 text-white"
              : "border-stone-200 text-stone-600 hover:bg-stone-50"
          }`}
        >
          Legend
        </button>
        <button
          onClick={handleRefresh}
          disabled={!datasetId || refreshing}
          className="rounded-md border border-stone-200 px-2 py-1 text-xs text-stone-600 hover:bg-stone-50 disabled:opacity-50"
        >
          {refreshing ? "…" : "↻"}
        </button>
      </div>

      {/* Left toolbar */}
      <div className="absolute left-3 top-1/2 z-10 flex -translate-y-1/2 flex-col gap-1 rounded-lg border border-stone-200 bg-white/95 p-1.5 shadow-sm backdrop-blur">
        <button
          className="flex h-8 w-8 items-center justify-center rounded text-stone-600 hover:bg-stone-100"
          onClick={() => triggerCanvasEvent("graph:fit")}
          title="Fit All"
        >
          ⛶
        </button>
        <button
          className="flex h-8 w-8 items-center justify-center rounded text-stone-600 hover:bg-stone-100"
          onClick={() => triggerCanvasEvent("graph:reset")}
          title="Reset"
        >
          ⟲
        </button>
        <div className="my-1 h-px bg-stone-200" />
        <button
          className={`flex h-8 w-8 items-center justify-center rounded ${
            physicsEnabled ? "bg-stone-900 text-white" : "text-stone-600 hover:bg-stone-100"
          }`}
          onClick={() => setPhysicsEnabled((v) => !v)}
          title="Physics"
        >
          ◉
        </button>
        <button
          className={`flex h-8 w-8 items-center justify-center rounded ${
            showLabels ? "bg-stone-900 text-white" : "text-stone-600 hover:bg-stone-100"
          }`}
          onClick={() => setShowLabels((v) => !v)}
          title="Labels"
        >
          A
        </button>
      </div>

      {/* Stats bar */}
      <div className="absolute bottom-3 left-3 z-10 flex gap-1 rounded-lg border border-stone-200 bg-white/95 p-1.5 shadow-sm backdrop-blur">
        <span className="flex items-center gap-1.5 px-2.5 py-1 font-mono text-[10px] text-stone-500">
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: "#d4a056" }} />
          {graphState.nodes.length} nodes
        </span>
        <span className="flex items-center gap-1.5 px-2.5 py-1 font-mono text-[10px] text-stone-500">
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: "#c4944a" }} />
          {graphState.edges.length} edges
        </span>
        <span className="flex items-center gap-1.5 px-2.5 py-1 font-mono text-[10px] text-stone-500">
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: "#6fa89a" }} />
          {graphState.communities.size} communities
        </span>
        <span className="px-2.5 py-1 font-mono text-[10px] text-stone-500">{zoom.toFixed(1)}x</span>
        {stats && (
          <span className="px-2.5 py-1 font-mono text-[10px] text-stone-500">
            density {stats.density.toFixed(3)}
          </span>
        )}
      </div>

      {/* Legend */}
      {showLegend && (
        <div className="absolute bottom-3 right-3 z-10 min-w-[180px] rounded-lg border border-stone-200 bg-white p-3 shadow-sm">
          <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-stone-400">
            Communities
          </div>
          {[...graphState.communities.values()].map((c) => (
            <div key={c.id} className="flex items-center gap-2 py-0.5 font-mono text-[10px] text-stone-600">
              <span className="h-2 w-2 rounded-full" style={{ background: c.color }} />
              {c.name}
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      {showFilters && (
        <div className="absolute right-3 top-16 z-10 flex flex-col gap-1">
          {[...graphState.communities.values()].map((c) => (
            <button
              key={c.id}
              onClick={() => toggleFilter(c.id)}
              className={`flex items-center gap-2 rounded-full border px-3 py-1 font-mono text-[10px] ${
                activeFilters.has(c.id)
                  ? "border-stone-900 bg-stone-900 text-white"
                  : "border-stone-200 bg-white text-stone-500 hover:border-stone-400"
              }`}
            >
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: c.color }} />
              {c.name}
            </button>
          ))}
        </div>
      )}

      {/* Inspector */}
      <Inspector
        node={selectedNode}
        state={graphState}
        onSelectNode={(n) => void handleNodeSelect(n)}
        onClose={() => setSelectedNode(null)}
      />

      {/* Command palette */}
      {cmdOpen && (
        <CommandPalette
          state={graphState}
          onSelectNode={(n) => void handleNodeSelect(n)}
          onClose={() => setCmdOpen(false)}
        />
      )}
    </div>
  );
}
